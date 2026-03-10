import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from supabase import create_client, Client
from dotenv import load_dotenv
import asyncio
import hashlib
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import requests
import io

# Initialize logging and FastApi
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the .env file from the root folder (one directory up)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

# Initialize Supabase Admin Client 
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
else:
    logger.warning("Supabase URL or Service Key missing. Database operations will fail.")

# Static files for reputation cards
REPUTATION_CARDS_DIR = os.path.join(os.path.dirname(__file__), "static", "reputation_cards")
os.makedirs(REPUTATION_CARDS_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

# Jupiter Protocol IDs (Solana Mainnet)
JUPITER_DCA_PROGRAM_ID = "DCA265Vj8a9CEuX1eb1LWRnDT7uK6q1xVuB4AQvnE1v"
JUPITER_LIMIT_PROGRAM_ID = "jupoNjMqk6VgczD9zTCkphN9P1K6Fq1YjK9R3p1bMv"
JUPITER_PERPS_PROGRAM_ID = "PERPHjGBqRHhARyq18vTQ1zqiEQx5y8qzhhkCRvPgBEX" 
JUPITER_LEND_PROGRAM_ID = "KLend2g3cPENn5A45zq6ARpLHR2c4R1E1oP8Q4E3Cg31"

@app.post("/webhook/helius")
async def helius_webhook(request: Request):
    """
    Endpoint for Helius Enhanced Webhooks to POST parsed Solana transaction data.
    """
    payload = await request.json()
    for tx in payload:
        signature = tx.get("signature", "Unknown")
        account_data = tx.get("accountData", [])
        fee_payer = tx.get("feePayer", "")
        involved_programs = [acc.get("account", "") for acc in account_data]
        
        is_dca = JUPITER_DCA_PROGRAM_ID in involved_programs
        is_limit = JUPITER_LIMIT_PROGRAM_ID in involved_programs
        is_perps = JUPITER_PERPS_PROGRAM_ID in involved_programs
        is_lend = JUPITER_LEND_PROGRAM_ID in involved_programs
        
        if is_dca or is_limit or is_perps or is_lend:
            if is_dca: metric_type = 'DCA'
            elif is_limit: metric_type = 'Limit_Orders'
            elif is_perps: metric_type = 'Perps'
            else: metric_type = 'Jup_Lend'
            
            token_transfers = tx.get("tokenTransfers", [])
            native_transfers = tx.get("nativeTransfers", [])
            total_usd_volume_detected = 0.0
            
            for transfer in token_transfers:
                if transfer.get("fromUserAccount") == fee_payer:
                    total_usd_volume_detected += transfer.get("tokenAmount", 0)
            for native in native_transfers:
                if native.get("fromUserAccount") == fee_payer:
                    total_usd_volume_detected += (native.get("amount", 0) / 1e9) * 145.0
            
            if total_usd_volume_detected == 0: total_usd_volume_detected = 100.0
            aura_points_earned = int(total_usd_volume_detected / 10) 
            
            if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                try:
                    supabase.table("user_metrics").upsert({
                        "wallet_address": fee_payer,
                        "metric_type": metric_type,
                        "metric_value": round(total_usd_volume_detected, 2),
                        "calculated_aura_points": aura_points_earned
                    }, on_conflict="wallet_address,metric_type").execute()
                except Exception as e:
                    logger.error(f"Error updating Supabase: {e}")

    return {"status": "success"}

# Professional API Key Suite
DUNE_API_KEY = os.getenv("DUNE_API_KEY", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
PPP_MINT_ADDRESS = os.getenv("PPP_MINT_ADDRESS", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

async def run_dune_query(query_sql: str):
    """Executes a Dune SQL query and waits for results."""
    if not DUNE_API_KEY:
        return None
    headers = {"X-Dune-API-Key": DUNE_API_KEY}
    try:
        execute_res = requests.post("https://api.dune.com/api/v1/query/execute", headers=headers, json={"query_sql": query_sql})
        execution_id = execute_res.json().get("execution_id")
        if not execution_id: return None
        for _ in range(15):
            await asyncio.sleep(2)
            status_res = requests.get(f"https://api.dune.com/api/v1/execution/{execution_id}/results", headers=headers)
            data = status_res.json()
            if data.get("state") == "QUERY_STATE_COMPLETED": return data.get("result", {}).get("rows", [])
            if data.get("state") in ["QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"]: return None
    except Exception as e: logger.error(f"Dune API Error: {e}")
    return None

async def is_ppp_holder(wallet_address: str) -> bool:
    """Checks if the user holds $PPP tokens using Helius DAS API."""
    if not HELIUS_API_KEY: return False
    url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    try:
        response = requests.post(url, json={
            "jsonrpc": "2.0",
            "id": "my-id",
            "method": "getTokenAccounts",
            "params": {
                "owner": wallet_address,
                "mint": PPP_MINT_ADDRESS,
            }
        })
        data = response.json()
        accounts = data.get("result", {}).get("token_accounts", [])
        for acc in accounts:
            if float(acc.get("amount", 0)) > 0:
                return True
    except Exception as e:
        logger.error(f"Error checking holder status: {e}")
    return False

@app.post("/api/sync-history/{wallet_address}")
async def sync_historical_data(wallet_address: str):
    """Deep Scan: Tries Dune (Lifetime) -> Fallback to Helius (Recent) + Holder Check"""
    logger.info(f"Starting Multi-Layer Sync for {wallet_address}...")
    
    # 1. Dune Query (Comprehensive History - Total Ecosystem Volume)
    dune_sql = f"""
    WITH swaps AS (
        SELECT 'PPP_Volume' as metric, SUM(amount_usd) as val
        FROM jupiter_solana.aggregator_swaps
        WHERE trader_id = '{wallet_address}'
    ),
    perps AS (
        SELECT 'Perps' as metric, SUM(amount_usd) as val
        FROM jupiter_perps_solana.trades
        WHERE trader = '{wallet_address}'
    ),
    dca AS (
        SELECT 'DCA' as metric, SUM(amount_usd) as val
        FROM jupiter_solana.aggregator_swaps
        WHERE trader_id = '{wallet_address}'
        AND (description LIKE '%DCA%' OR lower(source) LIKE '%dca%')
    ),
    staking AS (
        SELECT 'Jup_Staked' as metric, SUM(amount) / 1e6 as val
        FROM jupiter_solana.voting_locker_deposits
        WHERE owner = '{wallet_address}'
    ),
    lend AS (
        SELECT 'Jup_Lend' as metric, SUM(amount_usd) as val
        FROM kamino_solana.deposits
        WHERE owner = '{wallet_address}'
    )
    SELECT * FROM swaps 
    UNION ALL SELECT * FROM perps 
    UNION ALL SELECT * FROM dca
    UNION ALL SELECT * FROM staking
    UNION ALL SELECT * FROM lend
    """
    
    dune_results = await run_dune_query(dune_sql)
    
    real_metrics = {"DCA": 0.0, "Perps": 0.0, "Jup_Lend": 0.0, "Limit_Orders": 0.0, "PPP_Volume": 0.0, "Jup_Staked": 0.0}

    if dune_results:
        for row in dune_results:
            m_type, m_val = row.get("metric"), float(row.get("val") or 0.0)
            if m_type in real_metrics: real_metrics[m_type] = m_val
        logger.info(f"Dune Scan Successful: {real_metrics}")
    else:
        logger.warning("Dune unavailable. Running Helius Early-Response Scan.")
        return await sync_via_helius(wallet_address)

    is_holder = await is_ppp_holder(wallet_address)
    multiplier = 1.5 if is_holder else 1.0
    
    # Update Supabase
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        total_base_points = 0
        for m_type, m_val in real_metrics.items():
            metric_points = int(m_val / 10)
            total_base_points += metric_points
            try:
                supabase.table("user_metrics").upsert({
                    "wallet_address": wallet_address,
                    "metric_type": m_type,
                    "metric_value": round(m_val, 2),
                    "calculated_aura_points": metric_points
                }, on_conflict="wallet_address,metric_type").execute()
            except Exception as e: logger.error(f"Supabase Error: {e}")

        # Final Aura Aggregation
        try:
            supabase.table("user_aura_points").upsert({
                "wallet_address": wallet_address,
                "base_points": total_base_points,
                "multipliers": multiplier,
                "total_points": int(total_base_points * multiplier)
            }, on_conflict="wallet_address").execute()
        except Exception as e: logger.error(f"Aura Upsert Error: {e}")

    return {"status": "success", "source": "Dune", "metrics": real_metrics, "is_holder": is_holder}

async def sync_via_helius(wallet_address: str):
    """Fallback: Scans last 100 enriched transactions via Helius + Holder Check"""
    if not HELIUS_API_KEY: return await basic_rpc_scan(wallet_address)
    
    url = f"https://api.helius.xyz/v0/addresses/{wallet_address}/transactions?api-key={HELIUS_API_KEY}"
    try:
        txs = requests.get(url).json()
        metrics = {"DCA": 0.0, "Perps": 0.0, "Jup_Lend": 0.0, "Limit_Orders": 0.0, "PPP_Volume": 0.0, "Jup_Staked": 0.0}
        for tx in txs:
            desc = tx.get("description", "").lower()
            if "dca" in desc: metrics["DCA"] += 100.0
            elif "perpetual" in desc: metrics["Perps"] += 500.0
            elif "lend" in desc: metrics["Jup_Lend"] += 50.0
            elif "swap" in desc:
                for t in tx.get("tokenTransfers", []):
                    if t.get("fromUserAccount") == wallet_address: metrics["PPP_Volume"] += t.get("tokenAmount", 0)
        
        is_holder = await is_ppp_holder(wallet_address)
        multiplier = 1.5 if is_holder else 1.0
        
        total_base_points = 0
        for m_type, m_val in metrics.items():
            if m_val > 0:
                metric_points = int(m_val / 10)
                total_base_points += metric_points
                supabase.table("user_metrics").upsert({
                    "wallet_address": wallet_address, "metric_type": m_type,
                    "metric_value": round(m_val, 2), "calculated_aura_points": metric_points
                }, on_conflict="wallet_address,metric_type").execute()
        
        supabase.table("user_aura_points").upsert({
            "wallet_address": wallet_address, "base_points": total_base_points,
            "multipliers": multiplier, "total_points": int(total_base_points * multiplier)
        }, on_conflict="wallet_address").execute()
        
        return {"status": "success", "source": "Helius Fallback", "metrics": metrics, "is_holder": is_holder}
    except Exception as e:
        logger.error(f"Helius Fallback Error: {e}")
        return {"status": "error", "message": "Deep scan sources exhausted"}

async def basic_rpc_scan(wallet_address: str):
    """Fallback if Helius key is missing"""
    RPC_URL = "https://api.mainnet-beta.solana.com"
    try:
        sig_res = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [wallet_address, {"limit": 20}]
        })
        signatures = sig_res.json().get("result", [])
    except: signatures = []
    return {"status": "success", "message": f"Basic scan found {len(signatures)} transactions."}

@app.post("/api/admin/distribute-rewards")
async def distribute_weekly_rewards(pool_amount: float = 1000.0):
    """
    Weekly Reward Pool Calculation and Title Reset.
    User Reward = (User Effective Aura Points / Total Effective Aura Points of Top 100) × Weekly Reward Pool
    """
    logger.info(f"Distributing ${pool_amount} to top 100 users...")
    
    # 1. Fetch top 100 users by aura points
    top_users = supabase.table("user_aura_points").select("*").order("total_points", desc=True).limit(100).execute().data
    
    if not top_users:
        return {"status": "error", "message": "No users found in leaderboard"}
    
    total_effective_points = sum([u["total_points"] for u in top_users])
    
    if total_effective_points == 0:
        return {"status": "error", "message": "Total points across top 100 is zero"}
    
    period_start = datetime.utcnow() - timedelta(days=7)
    period_end = datetime.utcnow()
    
    rewards_to_insert = []
    
    for rank_idx, user in enumerate(top_users):
        wallet = user["wallet_address"]
        points = user["total_points"]
        
        # Calculate Share
        reward_amount = (points / total_effective_points) * pool_amount
        
        rewards_to_insert.append({
            "wallet_address": wallet,
            "reward_token": "$JUPUSD",
            "reward_amount": round(reward_amount, 4),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "claimed": False
        })
        
        # Assign Titles for Seasonal Competition
        rank = rank_idx + 1
        title = "Elite"
        if rank <= 10: title = "Jupiter Titan"
        elif rank <= 50: title = "Solana Navigator"
        elif rank <= 100: title = "PPP Elite"
        
        try:
            supabase.table("users").update({"user_title": title}).eq("wallet_address", wallet).execute()
        except Exception as e:
            logger.error(f"Failed to update title for {wallet}: {e}")

    # Insert rewards
    try:
        supabase.table("user_rewards").insert(rewards_to_insert).execute()
        logger.info(f"Successfully distributed rewards to {len(top_users)} users.")
        return {"status": "success", "distributed_to": len(top_users), "pool": pool_amount}
    except Exception as e:
        logger.error(f"Failed to insert rewards: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reputation-card/{wallet_address}")
async def get_reputation_card(wallet_address: str):
    """
    Generate shareable reputation visual card.
    """
    # 1. Fetch User Data
    user_data = supabase.table("users").select("username, user_title").eq("wallet_address", wallet_address).maybe_single().execute().data
    points_data = supabase.table("user_aura_points").select("*").eq("wallet_address", wallet_address).maybe_single().execute().data
    metrics_data = supabase.table("user_metrics").select("*").eq("wallet_address", wallet_address).execute().data
    
    if not points_data or not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    username = user_data.get("username", "Unknown Explorer")
    title = user_data.get("user_title", "Explorer")
    aura = points_data.get("total_points", 0)
    boost = points_data.get("multipliers", 1.0)
    
    # Extract specific metrics
    ppp_vol = next((m["metric_value"] for m in metrics_data if m["metric_type"] == "PPP_Volume"), 0)
    jup_staked = next((m["metric_value"] for m in metrics_data if m["metric_type"] == "Jup_Staked"), 0)
    perps_vol = next((m["metric_value"] for m in metrics_data if m["metric_type"] == "Perps"), 0)

    # 2. CREATE IMAGE (Pillow)
    img = Image.new("RGB", (1200, 630), color=(10, 10, 15)) # Dark space background
    draw = ImageDraw.Draw(img)
    
    # Try to load a font (fallback to default)
    try:
        font_large = ImageFont.truetype("arial.ttf", 60)
        font_med = ImageFont.truetype("arial.ttf", 40)
        font_small = ImageFont.truetype("arial.ttf", 25)
    except:
        font_large = ImageFont.load_default()
        font_med = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw Design Elements
    draw.rectangle([20, 20, 1180, 610], outline=(199, 242, 132), width=5) # Border
    draw.text((60, 60), f"PPP PROTOCOL REPUTATION", fill=(199, 242, 132), font=font_small)
    
    draw.text((60, 100), username, fill=(255, 255, 255), font=font_large)
    draw.text((60, 175), f"RANK: {title}", fill=(250, 204, 21), font=font_med)

    # Stats Grid
    stats = [
        ("AURA POINTS", f"{aura:,}"),
        ("BOOST", f"{boost}x"),
        ("STAKED JUP", f"{jup_staked:,} $JUP"),
        ("PPP VOLUME", f"${ppp_vol:,}"),
        ("PERPS VOLUME", f"${perps_vol:,}")
    ]
    
    for i, (label, val) in enumerate(stats):
        x = 60
        y = 250 + (i * 60)
        draw.text((x, y), label, fill=(148, 163, 184), font=font_small)
        draw.text((x + 300, y), val, fill=(255, 255, 255), font=font_small)

    # Branding
    draw.text((900, 540), "PPP STATION", fill=(199, 242, 132), font=font_med)

    filename = f"card_{wallet_address}_{int(datetime.now().timestamp())}.png"
    filepath = os.path.join(REPUTATION_CARDS_DIR, filename)
    img.save(filepath)
    
    card_url = f"/static/reputation_cards/{filename}"
    supabase.table("reputation_cards").upsert({
        "wallet_address": wallet_address,
        "card_url": card_url,
        "last_generated": datetime.utcnow().isoformat()
    }).execute()

    return {"status": "success", "card_url": card_url}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
