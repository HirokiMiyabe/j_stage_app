# app.py
import io
import datetime as dt

import altair as alt
import numpy as np
import polars as pl
import streamlit as st

from jstage_fetcher import fetch_jstage_data

# ===== 利用規約 同意ゲート =====
if "agreed" not in st.session_state:
    st.session_state.agreed = False

if not st.session_state.agreed:
    st.markdown(
        """
        <div style="max-width: 720px; margin: 2rem auto; padding: 1.5rem;
                    border: 2px solid #f0ad4e; border-radius: 14px;
                    background: rgba(240,173,78,0.08);">
          <h2 style="margin-top: 0;">⚠ 利用前の重要な確認</h2>

          <p style="font-size: 1.05rem;">
            必ず下記の規約・説明ページをよく読んだうえで、各自の責任においてご利用ください。
            本アプリの作成者は、本アプリの利用によって生じたいかなる損害についても責任を負いません。
          </p>

          <ul style="line-height: 1.8;">
            <li>
              <a href="https://www.jstage.jst.go.jp/static/pages/TermsAndPolicies/ForIndividuals/-char/ja"
                 target="_blank" rel="noopener noreferrer">
                j-stage利用規約・ポリシー
              </a>
            </li>
            <li>
              <a href="https://www.jstage.jst.go.jp/static/pages/WebAPI/-char/ja"
                 target="_blank" rel="noopener noreferrer">
                J-STAGE WebAPI 利用規約
              </a>
            </li>
            <li>
              <a href="https://www.jstage.jst.go.jp/static/pages/JstageServices/TAB3/-char/ja"
                 target="_blank" rel="noopener noreferrer">
                J-STAGE WebAPI 利用規約について
              </a>
            </li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    agree_read = st.checkbox("上記リンクから規約・説明を読みました")
    agree_responsibility = st.checkbox(
        "本アプリの利用により生じたいかなる損害についても、アプリ作成者ではなく使用者が責任を負うことに同意します"
    )

    if st.button("同意して利用開始", type="primary"):
        if agree_read and agree_responsibility:
            st.session_state.agreed = True
            st.rerun()
        else:
            st.error("すべての項目にチェックを入れてください。")

    # ★ ここで止める：同意するまで先に進めない
    st.stop()

# ===== ページ設定 =====
st.set_page_config(page_title="J-STAGE Search GUI", layout="wide")
st.title("J-STAGE Search API GUI（service=3）")


def to_csv_ready(df: pl.DataFrame, sep: str = ";") -> pl.DataFrame:
    """author(List[str]) -> author(str) へ変換（CSV向け / list[null]対策込み）"""
    if df.is_empty():
        return df
    if "author" not in df.columns:
        return df
    return df.with_columns(
        pl.coalesce([pl.col("author"), pl.lit([])])
        .cast(pl.List(pl.Utf8), strict=False)
        .list.join(sep)
        .alias("author")
    )


# ===== sidebar =====
with st.sidebar:
    st.header("検索条件(AND条件)")
    target_word = st.text_input(
        "検索語",
        help="半角スペースで区切るとAND検索になります。")
    
    material = st.text_input(
        "雑誌名（material）",
        help="完全一致のため、正確に入力してください。(j-stage上の表記の貼り付け推奨）"
    )
    author = st.text_input(
        "著者名（author）",
        help="first nameとlast nameの両方は半角スペースで区切ってください。"
    )
    affil = st.text_input("所属（affil）")
    
    issn = st.text_input(
        "ISSN",
        placeholder="例: 1234-5678",
        help="print版でもonline版のどちらか"
    )
    
    cdjournal = st.text_input("cdjournal（J-STAGE内部コード）")
    st.divider()
    
    
    year = st.number_input("開始年 (pubyearfrom)", min_value=0, max_value=3000, value=1950, step=1)
    field = st.selectbox("検索フィールド", ["article", "abst", "text"], index=0)
    max_records = st.number_input(
        "最大取得件数（暴走防止策）",
        min_value=1,
        max_value=500000,
        value=20000,
        step=1000,
    )

    st.caption("※J-STAGE閲覧規約上、登載データの大量ダウンロードは認められていません。")

    sleep = st.slider(
        "リクエスト間隔（秒）",
        min_value=2.0,
        max_value=8.0,
        value=2.0,
        step=0.5,
    )
    st.caption("※ J-STAGE APIへの負荷軽減のため、2秒以上を推奨します")

    st.divider()

    run = st.button("取得する", type="primary")

    # ★ 追加：結果をクリア（rerunしても消えない結果を手動で消す）
    if st.button("結果をクリア", type="secondary"):
        for k in ["df", "total", "base_name", "params"]:
            st.session_state.pop(k, None)
        st.rerun()

# ===== fetch -> session_state に保存 =====
if run:
    # 空文字→None（Streamlitは空欄だと "" を返すため）
    q_target = target_word.strip() or None
    q_material = material.strip() or None
    q_author = author.strip() or None
    q_affil = affil.strip() or None
    q_issn = issn.strip() or None
    q_cdjournal = cdjournal.strip() or None

    # 全条件が空はNG（yearだけ等の暴走防止）
    if all(v is None for v in [q_target, q_material, q_author, q_affil, q_issn, q_cdjournal]):
        st.error("検索条件が空です。検索語・雑誌名・著者名・所属・ISSN・cdjournal のいずれかを入力してください。")
        st.stop()

    # 表示用メッセージ（検索語が無い場合に備える）
    label = q_target if q_target is not None else "(no keyword)"
    st.info(f"取得開始：{label} / from={int(year)} / field={field}")

    df, total = fetch_jstage_data(
        target_word=q_target,          # ← None でもOK
        year=year,
        field=field,
        max_records=max_records,
        sleep=float(sleep),            
        material=q_material,
        author=q_author,
        affil=q_affil,
        issn=q_issn,
        cdjournal=q_cdjournal,
    )

    if df.is_empty():
        st.warning("0件でした。条件を変えて試してください。m(・v・)m")
        st.stop()

    # ファイル名ベース（検索語が空でもOKにする）
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_word = "".join(ch if ch.isalnum() else "_" for ch in (q_target or "no_keyword"))
    base_name = f"jstage_{safe_word}_{field}_{int(year)}_{ts}"

    # 保存（slider操作などで rerun しても結果が残る）
    st.session_state.df = df
    st.session_state.total = total
    st.session_state.base_name = base_name
    st.session_state.params = {
        "target_word": q_target,
        "material": q_material,
        "author": q_author,
        "affil": q_affil,
        "issn": q_issn,
        "cdjournal": q_cdjournal,
        "year": int(year),
        "field": field,
        "max_records": int(max_records),
        "sleep": float(sleep),
    }

    st.rerun()


# ===== ここから “保存済み結果の表示” =====
if "df" not in st.session_state:
    st.info("左の「取得する」を押すと結果が表示されます。")
    st.stop()

df: pl.DataFrame = st.session_state.df
total = st.session_state.get("total", None)
base_name = st.session_state.get("base_name", "jstage_result")

# 取得条件（直近）
with st.expander("取得条件（直近）", expanded=False):
    st.json(st.session_state.get("params", {}))

# メトリクス
c1, c2, c3 = st.columns(3)
c1.metric("取得件数", df.height)
c2.metric("総件数（API）", total if total is not None else "不明")
c3.metric("ユニークDOI", df.select(pl.col("doi").n_unique()).item() if "doi" in df.columns else 0)

st.caption("表示は author をリストのまま保持（JSON/Parquet向け）。CSVはダウンロード時に結合します。")
st.dataframe(df, width="stretch", height=520)

# =========================
# DataFrame ダウンロード
# =========================
st.subheader("DataFrame ダウンロード")

with st.expander("CSVオプション（任意）", expanded=False):
    csv_sep = st.text_input(
        "著者区切り文字",
        value=";",
        help="author が list の場合、この文字で結合されます",
        key="csv_sep",
    )

# CSV（authorを結合）
df_csv = to_csv_ready(df, sep=csv_sep)
csv_bytes = df_csv.write_csv().encode("utf-8")
st.download_button(
    "CSVをダウンロード（author結合）",
    data=csv_bytes,
    file_name=f"{base_name}.csv",
    mime="text/csv",
)

# JSON（authorはlistのまま）
json_str = df.write_json()
st.download_button(
    "JSONをダウンロード（authorはlist）",
    data=json_str.encode("utf-8"),
    file_name=f"{base_name}.json",
    mime="application/json",
)

# Parquet（authorはlistのまま）
buf = io.BytesIO()
df.write_parquet(buf)
st.download_button(
    "Parquetをダウンロード",
    data=buf.getvalue(),
    file_name=f"{base_name}.parquet",
    mime="application/octet-stream",
)

# =========================
# 上位ジャーナルの分布
# =========================
st.divider()
st.subheader("上位ジャーナル（件数）")

col_left, col_right = st.columns(2)

# ---------- material_title ----------
with col_left:
    st.markdown("### material_title（誌名）上位")

    if "material_title" not in df.columns:
        st.warning("material_title 列がありません。")
    else:
        top_material = (
            df.filter(pl.col("material_title").is_not_null())
            .group_by("material_title")
            .agg(pl.len().alias("n"))
            .sort("n", descending=True)
            .head(15)
        )
        if top_material.is_empty():
            st.warning("material_title がすべて欠損です。")
        else:
            st.dataframe(top_material, width="stretch", height=300)
            st.bar_chart(top_material.to_pandas(), x="material_title", y="n")

# ---------- cdjournal ----------
with col_right:
    st.markdown("### cdjournal（誌名コード）上位")

    if "cdjournal" not in df.columns:
        st.warning("cdjournal 列がありません。")
    else:
        top_cdjournal = (
            df.with_columns(pl.col("cdjournal").cast(pl.Utf8, strict=False))
            .filter(pl.col("cdjournal").is_not_null() & (pl.col("cdjournal").str.len_chars() > 0))
            .group_by("cdjournal")
            .agg(pl.len().alias("n"))
            .sort("n", descending=True)
            .head(15)
        )
        if top_cdjournal.is_empty():
            st.warning("cdjournal がすべて欠損です。")
        else:
            st.dataframe(top_cdjournal, width="stretch", height=300)
            st.bar_chart(top_cdjournal.to_pandas(), x="cdjournal", y="n")

# =========================
# 年別件数の推移
# =========================
st.divider()
st.subheader("年別件数の推移（pubyear別の行数）")

if "pubyear" not in df.columns:
    st.warning("pubyear 列がないため、年推移グラフを作れません。")
else:
    yearly = (
        df.with_columns(pl.col("pubyear").cast(pl.Int32, strict=False))
        .filter(pl.col("pubyear").is_not_null())
        .group_by("pubyear")
        .agg(pl.len().alias("n"))
        .sort("pubyear")
    )

    if yearly.is_empty():
        st.warning("pubyear が全て欠損のため、年推移グラフを作れません。")
    else:
        st.dataframe(yearly, width="stretch", height=240)
        yearly_pd = yearly.to_pandas()
        st.line_chart(yearly_pd, x="pubyear", y="n")
        st.bar_chart(yearly_pd, x="pubyear", y="n")

# =========================
# 年 × ジャーナル（material_title）折れ線（上位N）
# =========================
st.divider()
st.subheader("上位ジャーナル（年別件数推移）")

if ("pubyear" not in df.columns) or ("material_title" not in df.columns):
    st.warning("pubyear または material_title 列がないため、グラフを作れません。")
else:
    top_k = st.slider(
        "表示する上位ジャーナル数（material_title）",
        5,
        15,
        10,
        1,
        key="topk_material_title",
    )

    df_l = (
        df.with_columns(
            [
                pl.col("pubyear").cast(pl.Int32, strict=False),
                pl.col("material_title").cast(pl.Utf8, strict=False),
            ]
        )
        .filter(
            pl.col("pubyear").is_not_null()
            & pl.col("material_title").is_not_null()
            & (pl.col("material_title").str.len_chars() > 0)
        )
    )

    if df_l.is_empty():
        st.warning("pubyear/material_title が有効な行がありません。")
    else:
        y_min = int(df_l.select(pl.col("pubyear").min()).item())
        y_max = int(df_l.select(pl.col("pubyear").max()).item())

        top_journals = (
            df_l.group_by("material_title")
            .agg(pl.len().alias("n"))
            .sort("n", descending=True)
            .head(int(top_k))
            .select("material_title")
            .to_series()
            .to_list()
        )

        line = (
            df_l.filter(pl.col("material_title").is_in(top_journals))
            .group_by(["pubyear", "material_title"])
            .agg(pl.len().alias("n"))
            .sort(["pubyear", "material_title"])
        )

        years = list(range(y_min, y_max + 1))
        grid = pl.DataFrame(
            {
                "pubyear": np.repeat(years, len(top_journals)),
                "material_title": top_journals * len(years),
            }
        )

        line_full = (
            grid.join(line, on=["pubyear", "material_title"], how="left")
            .with_columns(pl.col("n").fill_null(0))
            .sort(["pubyear", "material_title"])
        )

        st.caption(
            f"年は {y_min}〜{y_max} に固定。表示は上位 {len(top_journals)} material_title（全期間合計の多い順）。欠損年は 0 埋め。"
        )
        st.dataframe(line_full, width="stretch", height=260)

        line_pd = line_full.to_pandas()

        # 10番目を黒にしたカスタム配色（tableau系 + black）
        CUSTOM_COLORS = [
            "#4E79A7",  # blue
            "#F28E2B",  # orange
            "#E15759",  # red
            "#76B7B2",  # teal
            "#59A14F",  # green
            "#EDC948",  # yellow
            "#B07AA1",  # purple
            "#FF9DA7",  # pink
            "#9C755F",  # brown
            "#000000",  # ★ black（10番目）
            "#BAB0AC",  # gray（予備）
            "#1F77B4",  # 予備
            "#FF7F0E",  # 予備
            "#2CA02C",  # 予備
            "#D62728",  # 予備
        ]

        st.caption("※ 凡例クリックで系列を強調。Shift を押しながらクリックすると複数系列を同時に強調できます。")

        sel = alt.selection_point(
            name=f"legendSel_{int(top_k)}",
            fields=["material_title"],
            bind="legend",
            empty="all",
            toggle="event.shiftKey",
        )

        chart = (
            alt.Chart(line_pd)
            .mark_line()
            .encode(
                x=alt.X("pubyear:Q", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y("n:Q", title="Count"),
                color=alt.Color(
                    "material_title:N",
                    title="material_title",
                    scale=alt.Scale(range=CUSTOM_COLORS),
                ),
                opacity=alt.condition(sel, alt.value(1.0), alt.value(0.08)),
                tooltip=["pubyear:Q", "material_title:N", "n:Q"],
            )
            .add_params(sel)
            .properties(height=420)
        )

        st.altair_chart(chart, width="stretch")

# =========================
# クレジット表示
# =========================
st.markdown(
    """
<div style="font-size: 0.9rem; color: #666; margin-top: 2rem;">
  <div>表示情報提供元：<a href="https://www.jstage.jst.go.jp/browse/-char/ja" target="_blank" rel="noopener noreferrer">J-STAGE</a></div>
  <div>Powered by <a href="https://www.jstage.jst.go.jp/browse/-char/ja" target="_blank" rel="noopener noreferrer">J-STAGE</a></div>
</div>
""",
    unsafe_allow_html=True,
)
