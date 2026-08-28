from extract.pull_data import pull_data
from load.bronze import load_bronze
from transform.silver_pipeline import bronze_to_silver
from load.silver import load_silver


def run_pipeline():

    # Extract
    raw_df = pull_data()

    # Bronze
    load_bronze(raw_df)

    # Transform Bronze → Silver
    silver_df = bronze_to_silver(raw_df)

    # Silver
    load_silver(silver_df)


if __name__ == "__main__":
    run_pipeline()