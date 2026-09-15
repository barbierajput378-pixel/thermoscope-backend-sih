import os
from dotenv import load_dotenv

load_dotenv()

FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# min_lon,min_lat,max_lon,max_lat
REGION_BBOX = os.environ.get("REGION_BBOX", "85.5,22.0,87.0,23.5")

# Classification thresholds - tune these once you have real data
FACILITY_PROXIMITY_METERS = 1000
HIGH_CONFIDENCE_THRESHOLD = 0.8
PERSISTENCE_DAYS_FOR_KNOWN_SOURCE = 14
