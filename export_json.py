# export_json.py
from jstage_fetcher import fetch_jstage_data

if __name__ == "__main__":
    df, total = fetch_jstage_data(
        target_word="学際",
        year=1950,
        field="article",
        max_records=20000,
        sleep=0.1,
    )

    # author(List[str]) のまま JSON 化
    df.write_json("jstage_results.json")
    print("saved: jstage_results.json")
    print("rows:", df.height, "totalResults:", total)
