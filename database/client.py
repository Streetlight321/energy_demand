import os

from dotenv import load_dotenv
from supabase import Client, ClientOptions, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# PostgREST's own default is 120s; state it explicitly so it is visible and
# tunable. A longer timeout is not the fix for a stalled connection - see
# database/retry.py - it just stops a slow-but-alive request being abandoned.
DEFAULT_TIMEOUT_SECONDS = 120


def _timeout_seconds():
    raw = os.getenv("SUPABASE_TIMEOUT_SECONDS")

    if not raw:
        return DEFAULT_TIMEOUT_SECONDS

    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"SUPABASE_TIMEOUT_SECONDS must be a number, got {raw!r}"
        )


if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL not found")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY not found")


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(postgrest_client_timeout=_timeout_seconds()),
)
