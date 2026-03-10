# Solana Backend API
Backend for tracking $PPP and Jupiter volume. Uses Helius and Dune Analytics APIs.

## Local Setup
1. `uvicorn main:app --reload`
2. Uses `.env` variables:
- `VITE_SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `HELIUS_API_KEY`
- `DUNE_API_KEY`
- `PPP_MINT_ADDRESS`
