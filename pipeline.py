from extract.pull_data import pull_raw
from load.load_bronze import load_bronze


def run_pipeline():
    print("Extracting EIA data...")
    df = pull_raw()
    print(f"Extracted {len(df)} rows")
    print("Loading Bronze table...")
    load_bronze(df)
    print("Pipeline complete")
if __name__ == "__main__":
    run_pipeline()