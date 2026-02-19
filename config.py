import os

# Email
# Use Environment Variables for production, fallback to hardcoded for local dev
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "d88368817@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "fiar jkpm grfb ogsp")

# Admin
ADMIN_ID = os.getenv("ADMIN_ID", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ntwbvipfmhyokvremmal.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Q_EPiRVPU9_IWt2R0w4jHA_SCROH2JC")