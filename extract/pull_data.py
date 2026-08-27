import os
import dotenv
import requests
import pandas as pd

dotenv.load_dotenv()

API_KEY = os.getenv("eia_api_key")
URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"


def pull_raw(start=None):
    params = {
        "api_key": API_KEY,
        "frequency": "hourly",
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
        "offset": 0,
    }

    if start:
        params["start"] = start

    response = requests.get(
        URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    records = response.json()["response"]["data"]

    return pd.DataFrame(records)