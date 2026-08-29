import os
import sys
from pathlib import Path

# Tests import the pipeline packages the same way `uv run pipeline.py` does.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Placeholder credentials so importing the Supabase client works offline.
# `load_dotenv()` does not override values that are already set, so real
# credentials are never used by the test suite.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key-not-real")
os.environ.setdefault("EIA_API_KEY", "test-key-not-real")
