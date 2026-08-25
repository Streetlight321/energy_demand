import dotenv
import os
import requests
import pandas as pd

dotenv.load_dotenv()

def pull_data(start = None, end= None):
    
    api_key = os.getenv('eia_api_key')
    if not api_key:
        raise ValueError("EIA_API_KEY not found in environment")

    url = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": 0,
        "length": 5000,
    }
    response = requests.get(url, params=params)
    print(response.status_code)
    data = response.json()
    records = data['response']['data']
    df = pd.DataFrame(records)
    
    return df

data = pull_data()