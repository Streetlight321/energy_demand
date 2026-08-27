from extract.pull_data import pull_raw

def bronze_to_silver(df):
    df = pull_raw()
    print(df)