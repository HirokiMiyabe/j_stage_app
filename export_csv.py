# export_csv.py
import polars as pl
from jstage_fetcher import fetch_jstage_data

def to_csv_ready(df: pl.DataFrame, sep: str = "; ") -> pl.DataFrame:
    # author(List[str]) -> author(str)
    if df.is_empty():
        return df
    return df.with_columns(
        pl.when(pl.col("author").is_null())
          .then(None)
          .otherwise(pl.col("author").list.join(sep))
          .alias("author")
    )

if __name__ == "__main__":
    df, total = fetch_jstage_data(
        target_word="学際",
        year=1950,
        field="article",
        max_records=20000,
        sleep=0.1,
    )

    df_csv = to_csv_ready(df, sep="; ")
    df_csv.write_csv("jstage_results.csv")
    print("saved: jstage_results.csv")
    print("rows:", df_csv.height, "totalResults:", total)
