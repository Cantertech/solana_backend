import os
from supabase import create_client, Client
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    # Delete all generated dummy user_metrics
    supabase.table("user_metrics").delete().neq('wallet_address', 'thisisnotreal123').execute()
    # Delete all generated aura_points
    supabase.table("user_aura_points").delete().neq('wallet_address', 'thisisnotreal123').execute()
    supabase.table("wallet_stats").update({'total_volume': 0, 'aura_points': 0}).neq('wallet_address', 'thisisnotreal123').execute()
    print("Database purged of all legacy dummy data! Everything is True 0.")
else:
    print("Supabase credentials missing.")
