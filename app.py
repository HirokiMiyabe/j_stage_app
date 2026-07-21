# app.py
import hmac
import io
import datetime as dt
import json
import os

import altair as alt
import numpy as np
import polars as pl
import streamlit as st

from jstage_fetcher import fetch_jstage_data

try:
    from reference_fetcher import get_references_batch
    REFERENCE_FETCHER_IMPORT_ERROR = None
except Exception as exc:
    get_references_batch = None
    REFERENCE_FETCHER_IMPORT_ERROR = exc

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
                J-STAGE利用規約・ポリシー
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
st.title("J-STAGET: J-STAGE Search API with GUI")


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


def sort_df_by_pubyear_default(df: pl.DataFrame) -> pl.DataFrame:
    """Sort by pubyear ascending when the column is available."""
    if df.is_empty() or "pubyear" not in df.columns:
        return df
    return df.sort(pl.col("pubyear").cast(pl.Int32, strict=False), nulls_last=True)


REFERENCE_FEATURE_PASSWORD_SECRET = "reference_feature_password"
REFERENCE_FEATURE_PASSWORD_ENV = "REFERENCE_FEATURE_PASSWORD"
REFERENCE_URL_LIMIT = 2000
REFERENCE_WAIT_SECONDS = 20
REFERENCE_SLEEP_SECONDS = 1.0
REFERENCE_RESULT_STATE_KEYS = (
    "reference_results",
    "reference_results_base_name",
    "reference_processed_url_count",
    "reference_truncated_url_count",
    "reference_empty_url_count",
)


def get_reference_feature_password() -> str | None:
    """Read the owner-configured password from Streamlit secrets or env vars."""
    configured_password = None
    try:
        configured_password = st.secrets.get(REFERENCE_FEATURE_PASSWORD_SECRET)
    except Exception:
        configured_password = None

    if not configured_password:
        configured_password = os.getenv(REFERENCE_FEATURE_PASSWORD_ENV)

    if isinstance(configured_password, str):
        configured_password = configured_password.strip()
    return configured_password or None


def clear_reference_results() -> None:
    for key in REFERENCE_RESULT_STATE_KEYS:
        st.session_state.pop(key, None)


def collect_reference_urls(
    df: pl.DataFrame,
    limit: int = REFERENCE_URL_LIMIT,
) -> tuple[list[str], int, int]:
    """Collect unique url_doi values in row order, capped by limit."""
    if df.is_empty() or "url_doi" not in df.columns:
        return [], 0, 0

    seen: set[str] = set()
    urls: list[str] = []
    raw_urls = (
        df.with_columns(pl.col("url_doi").cast(pl.Utf8, strict=False))
        .get_column("url_doi")
        .to_list()
    )

    for raw_url in raw_urls:
        if raw_url is None:
            continue
        url = raw_url.strip()
        if not url or not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        if len(urls) < limit:
            urls.append(url)

    truncated_count = max(len(seen) - len(urls), 0)
    return urls, truncated_count, len(seen)


CSV_DOWNLOAD_ENCODINGS = {
    "UTF-8（推奨）": {
        "encoding": "utf-8-sig",
        "charset": "utf-8",
        "label": "UTF-8",
    },
    "CP932（Windows版Excel向け）": {
        "encoding": "cp932",
        "charset": "shift_jis",
        "label": "CP932",
    },
}


# ===== sidebar =====
with st.sidebar:
    st.header("検索条件")
    target_word = st.text_input(
        "検索語",
        help="半角スペースで区切るとAND検索になります。")
    
    material = st.text_input(
        "雑誌名（material）",
        help="完全一致のため、正確に入力してください。(j-stage上の表記の貼り付け推奨）"
    )
    author = st.text_input(
        "著者名（author）",
        help="first nameとlast nameの間は半角スペースで区切ってください。"
    )
    affil = st.text_input("所属（affil）")
    
    issn = st.text_input(
        "ISSN",
        placeholder="例: 1234-5678",
        help="print版でもonline版のどちらか"
    )
    
    cdjournal = st.text_input("cdjournal（J-STAGE内部コード）",
        help="J-STAGEがジャーナルに割り当てているコード。APIの検索結果から確認可能です。")
    st.divider()
    
    
    year = st.number_input("開始年 (pubyearfrom)", min_value=0, max_value=3000, value=1950, step=1)
    field = st.selectbox("検索範囲", ["article", "abst", "text"], index=0)
    st.caption("※ 検索語がどこに含まれるかを指定します。article:タイトル内検索, abst: アブストラクト内検索, text: 全文検索")
    
    max_records = st.number_input(
        "最大取得件数（暴走防止策）",
        min_value=1,
        max_value=100000,
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
        clear_reference_results()
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
    df = sort_df_by_pubyear_default(df)

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
        "year": int(year),
        "material": q_material,
        "author": q_author,
        "affil": q_affil,
        "issn": q_issn,
        "cdjournal": q_cdjournal,
        "field": field,
        "max_records": int(max_records),
        "sleep": float(sleep),
    }
    clear_reference_results()

    st.rerun()


# ===== ここから “保存済み結果の表示” =====
if "df" not in st.session_state:
    st.info("「取得する」を押すと結果が表示されます。  \n*スマホの方はまず画面左上の>>>をクリック")
    st.stop()

df: pl.DataFrame = sort_df_by_pubyear_default(st.session_state.df)
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
    csv_encoding_label = st.selectbox(
        "CSVの文字コード",
        options=list(CSV_DOWNLOAD_ENCODINGS),
        index=0,
        help=(
            "OS名ではなく、CSV を開くアプリに合わせて選んでください。"
            " UTF-8 は BOM 付きで出力されます。"
            " Windows 版 Excel で開く場合は CP932 を選ぶと文字化けしにくくなります。"
        ),
        key="csv_encoding",
    )

# CSV（authorを結合）
df_csv = to_csv_ready(df, sep=csv_sep)
csv_text = df_csv.write_csv()
csv_encoding = CSV_DOWNLOAD_ENCODINGS[csv_encoding_label]

try:
    csv_bytes = csv_text.encode(csv_encoding["encoding"])
except UnicodeEncodeError:
    st.warning(
        f"{csv_encoding['label']} では保存できない文字が含まれています。"
        " UTF-8 を選んでダウンロードしてください。"
    )
else:
    st.download_button(
        f"CSVをダウンロード（author結合・{csv_encoding['label']}）",
        data=csv_bytes,
        file_name=f"{base_name}.csv",
        mime=f"text/csv; charset={csv_encoding['charset']}",
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
# 追加データ取得
# =========================
if st.session_state.get("reference_results_base_name") != base_name:
    clear_reference_results()

st.divider()
st.subheader("追加データ取得")

reference_feature_password = get_reference_feature_password()
reference_feature_unlocked = st.session_state.get("reference_feature_unlocked", False)

if not reference_feature_unlocked:
    access_code = st.text_input(
        "アクセスコード",
        type="password",
        key="reference_feature_access_code",
    )
    if st.button("追加機能を開く", key="reference_feature_unlock_button"):
        if not reference_feature_password:
            st.error(
                f"この機能はまだ設定されていません。"
                f" {REFERENCE_FEATURE_PASSWORD_SECRET} を secrets に設定してください。"
            )
        elif hmac.compare_digest(access_code, reference_feature_password):
            st.session_state.reference_feature_unlocked = True
            st.session_state.pop("reference_feature_access_code", None)
            st.rerun()
        else:
            st.error("アクセスコードが正しくありません。")
else:
    st.caption(
        f"url_doi をもとに追加データを取得します。"
        f" 対象は重複除去後の先頭 {REFERENCE_URL_LIMIT} URL までです。"
    )

    if get_references_batch is None:
        st.error(
            "追加データ取得モジュールを読み込めませんでした。"
            f" {REFERENCE_FETCHER_IMPORT_ERROR}"
        )
    elif "url_doi" not in df.columns:
        st.warning("url_doi 列がないため、この機能は利用できません。")
    else:
        reference_urls, truncated_url_count, unique_url_total = collect_reference_urls(df)
        if unique_url_total == 0:
            st.warning("有効な url_doi が見つかりませんでした。")
        else:
            if truncated_url_count > 0:
                st.warning(
                    f"url_doi はユニークで {unique_url_total} 件ありました。"
                    f" この機能では先頭 {REFERENCE_URL_LIMIT} 件だけを処理します。"
                )

            if st.button("get_reference", type="primary", key="get_reference_button"):
                with st.spinner("追加データを取得中..."):
                    try:
                        reference_results = get_references_batch(
                            reference_urls,
                            wait_sec=REFERENCE_WAIT_SECONDS,
                            sleep_sec=REFERENCE_SLEEP_SECONDS,
                        )
                    except Exception as exc:
                        st.error(f"get_reference を実行できませんでした: {exc}")
                    else:
                        st.session_state.reference_results = reference_results
                        st.session_state.reference_results_base_name = base_name
                        st.session_state.reference_processed_url_count = len(reference_urls)
                        st.session_state.reference_truncated_url_count = truncated_url_count
                        st.session_state.reference_empty_url_count = sum(
                            1 for refs in reference_results.values() if not refs
                        )

            reference_results = st.session_state.get("reference_results")
            if (
                reference_results is not None
                and st.session_state.get("reference_results_base_name") == base_name
            ):
                total_reference_count = sum(len(refs) for refs in reference_results.values())
                empty_url_count = st.session_state.get("reference_empty_url_count", 0)
                processed_url_count = st.session_state.get("reference_processed_url_count", 0)

                ref_c1, ref_c2, ref_c3 = st.columns(3)
                ref_c1.metric("処理URL数", processed_url_count)
                ref_c2.metric("空リストURL数", empty_url_count)
                ref_c3.metric("参考文献総数", total_reference_count)

                st.caption("取得できなかった URL は [] で保持しています。")
                st.json(reference_results)

                reference_json = json.dumps(
                    reference_results,
                    ensure_ascii=False,
                    indent=2,
                )
                st.download_button(
                    "reference JSONをダウンロード",
                    data=reference_json.encode("utf-8"),
                    file_name=f"{base_name}_references.json",
                    mime="application/json",
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
            "#000000",  # black（10番目）デフォだと灰色で見にくい
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
