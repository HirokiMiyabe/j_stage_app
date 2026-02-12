"""jstage_fetcher.py

Streamlit アプリ（j_stage_app）から呼ぶための薄いラッパー。

取得ロジックは j_staget（独立パッケージ）側に集約し、ここは
アプリの既存I/F（df, total_results を返す）を維持するだけにする。
"""

from __future__ import annotations

import polars as pl

from j_staget import fetch



def fetch_jstage_data(
    *,
    target_word: str | None,
    year: int,
    field: str,
    max_records: int,
    sleep: float = 2.0,
    material: str | None = None,
    author: str | None = None,
    affil: str | None = None,
    issn: str | None = None,
    cdjournal: str | None = None,
):
    
    """
    J-STAGE Search API (service=3) からデータを取得して (df, total) を返す。

    Notes
    -----
    - 実処理は j_staget.fetch を利用する。
    - 返り値はアプリ互換のため tuple を維持。
    """

    res = fetch(
        target_word=target_word,
        year=int(year),
        field=str(field),
        max_records=int(max_records),
        sleep=float(sleep),
        material=material,
        author=author,
        affil=affil,
        issn=issn,
        cdjournal=cdjournal,
    )

    return (
        res.df if isinstance(res.df, pl.DataFrame) else pl.DataFrame(res.df),
        res.total_results,
    )