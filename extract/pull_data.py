"""EIA API access only: authenticated, retrying, paginated requests.

Nothing in here touches Supabase or transforms data.
"""

import os

import dotenv
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

dotenv.load_dotenv()

URL = (
    "https://api.eia.gov/v2/"
    "electricity/rto/region-data/data/"
)

PAGE_SIZE = 5000

# The workflow provides EIA_API_KEY; local .env files may use the lowercase
# spelling. Never log the value itself.
API_KEY_ENV_VARS = ("EIA_API_KEY", "eia_api_key")

RETRY_STATUSES = (429, 500, 502, 503, 504)

BASE_PARAMS = {
    "frequency": "hourly",
    "data[0]": "value",
    "sort[0][column]": "period",
    "sort[0][direction]": "asc",
}


def get_api_key():
    """Return the EIA API key, or fail loudly before any request is built.

    A missing key used to be sent as `api_key=None`, which the EIA answers
    with 403 Forbidden.
    """
    for name in API_KEY_ENV_VARS:
        key = os.getenv(name)

        if key and key.strip():
            return key.strip()

    raise RuntimeError(
        "EIA_API_KEY is not set. Add it to .env for local runs or to the "
        "repository secrets for GitHub Actions."
    )


def build_session():
    """A requests session that retries transient EIA failures."""
    retry = Retry(
        total=5,
        connect=3,
        read=3,
        backoff_factor=1.5,
        status_forcelist=list(RETRY_STATUSES),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )

    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def redact(text, secret):
    """Keep the API key out of exception messages and logs."""
    if secret and secret in text:
        return text.replace(secret, "***")

    return text


def pull_raw(start=None, end=None, session=None, page_size=PAGE_SIZE):
    """Fetch every EIA row for the window, paging until the set is exhausted.

    `start` / `end` are EIA period strings such as "2026-08-27T12" and are
    omitted from the request when None.
    """
    api_key = get_api_key()

    owns_session = session is None
    session = session or build_session()

    all_rows = []
    offset = 0

    try:
        while True:
            params = dict(BASE_PARAMS)
            params["api_key"] = api_key
            params["length"] = page_size
            params["offset"] = offset

            if start:
                params["start"] = start

            if end:
                params["end"] = end

            response = session.get(
                URL,
                params=params,
                timeout=30,
            )

            # Permanent errors still fail the run, but without leaking the key
            # (requests puts the full URL in the error message).
            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                raise requests.HTTPError(
                    redact(str(error), api_key)
                ) from None

            rows = _extract_rows(response.json())

            if not rows:
                break

            all_rows.extend(rows)

            print(f"Fetched {len(all_rows)} rows...")

            if len(rows) < page_size:
                break

            offset += page_size

    finally:
        if owns_session:
            session.close()

    return pd.DataFrame(all_rows)


def _extract_rows(payload):
    rows = payload.get("response", {}).get("data")

    if rows is None:
        raise RuntimeError(
            f"Unexpected EIA response shape, top-level keys: "
            f"{sorted(payload)}"
        )

    return rows
