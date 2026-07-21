# app.py
import io
import datetime as dt
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import altair as alt
try:
    from janome.tokenizer import Tokenizer
except ImportError:
    Tokenizer = None
try:
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
except ImportError:
    plt = None
    font_manager = None
try:
    import networkx as nx
except ImportError:
    nx = None
import numpy as np
import polars as pl
import streamlit as st
try:
    from wordcloud import WordCloud
except ImportError:
    WordCloud = None

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


TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "approach",
    "based",
    "by",
    "case",
    "development",
    "effect",
    "effects",
    "evaluation",
    "for",
    "in",
    "method",
    "methods",
    "new",
    "of",
    "on",
    "report",
    "results",
    "review",
    "study",
    "the",
    "to",
    "using",
    "with",
    "こと",
    "その",
    "ため",
    "について",
    "による",
    "における",
    "もの",
    "および",
    "一例",
    "事例",
    "作成",
    "分析",
    "可能性",
    "変化",
    "影響",
    "方法",
    "日本",
    "有用性",
    "構築",
    "比較",
    "検討",
    "症例",
    "発症",
    "研究",
    "結果",
    "考察",
    "評価",
    "調査",
    "試み",
    "関係",
}
TITLE_POS_TO_KEEP = {"名詞", "動詞", "形容詞"}
TITLE_CJK_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\msgothic.ttc"),
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


@st.cache_resource(show_spinner=False)
def get_title_tokenizer():
    return Tokenizer() if Tokenizer is not None else None


@st.cache_data(show_spinner=False)
def find_title_font_path():
    for candidate in TITLE_CJK_FONT_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


@st.cache_resource(show_spinner=False)
def get_title_font_properties():
    if font_manager is None:
        return None
    font_path = find_title_font_path()
    if font_path is None:
        return None
    try:
        font_manager.fontManager.addfont(font_path)
        return font_manager.FontProperties(fname=font_path)
    except Exception:
        return None


def normalize_title_token(token: str) -> str:
    normalized = token.strip().lower()
    normalized = normalized.replace("−", "-").replace("–", "-").replace("—", "-")
    normalized = re.sub(r"^[\W_]+|[\W_]+$", "", normalized)
    return normalized


def is_valid_title_token(token: str) -> bool:
    if not token:
        return False
    if token in TITLE_STOPWORDS:
        return False
    if len(token) < 2:
        return False
    if token.isdigit():
        return False
    if not re.search(r"[A-Za-z一-龥ぁ-んァ-ヶー]", token):
        return False
    return True


def fallback_tokenize_title(text: str) -> list[str]:
    tokens = []
    for raw in re.split(r"[^0-9A-Za-z一-龥ぁ-んァ-ヶー]+", text):
        token = normalize_title_token(raw)
        if is_valid_title_token(token):
            tokens.append(token)
    return tokens


def tokenize_article_title(text: str) -> list[str]:
    tokenizer = get_title_tokenizer()
    if tokenizer is None:
        return fallback_tokenize_title(text)

    tokens = []
    for token in tokenizer.tokenize(text):
        pos = token.part_of_speech.split(",")[0]
        if pos not in TITLE_POS_TO_KEEP:
            continue
        base = token.base_form if token.base_form != "*" else token.surface
        normalized = normalize_title_token(base)
        if is_valid_title_token(normalized):
            tokens.append(normalized)
    return tokens


@st.cache_data(show_spinner=False)
def build_article_title_tokens(texts: tuple[str, ...]) -> list[list[str]]:
    token_lists = []
    for text in texts:
        tokens = tokenize_article_title(text)
        if tokens:
            token_lists.append(tokens)
    return token_lists


def build_word_frequencies(token_lists: list[list[str]]) -> Counter:
    return Counter(token for tokens in token_lists for token in tokens)


def build_cooccurrence_graph(
    token_lists: list[list[str]],
    top_words: int = 30,
    max_edges: int = 60,
):
    if nx is None:
        return None, Counter(), 0

    word_counts = Counter()
    for tokens in token_lists:
        word_counts.update(set(tokens))

    if len(word_counts) < 2:
        return None, word_counts, 0

    network_words = {word for word, _ in word_counts.most_common(top_words)}
    pair_counts = Counter()
    for tokens in token_lists:
        unique_tokens = sorted({token for token in tokens if token in network_words})
        if len(unique_tokens) < 2:
            continue
        pair_counts.update(combinations(unique_tokens, 2))

    if not pair_counts:
        return None, word_counts, 0

    min_edge_weight = 2 if len(token_lists) >= 20 else 1
    selected_edges = [
        (left, right, weight)
        for (left, right), weight in pair_counts.items()
        if weight >= min_edge_weight
    ]
    if not selected_edges:
        min_edge_weight = 1
        selected_edges = [
            (left, right, weight)
            for (left, right), weight in pair_counts.items()
            if weight >= min_edge_weight
        ]

    selected_edges.sort(key=lambda item: (-item[2], item[0], item[1]))
    selected_edges = selected_edges[:max_edges]
    if not selected_edges:
        return None, word_counts, min_edge_weight

    graph = nx.Graph()
    used_words = {left for left, _, _ in selected_edges} | {right for _, right, _ in selected_edges}
    for word in sorted(used_words, key=lambda item: (-word_counts[item], item)):
        graph.add_node(word, weight=word_counts[word])
    for left, right, weight in selected_edges:
        graph.add_edge(left, right, weight=weight)

    return graph, word_counts, min_edge_weight


def render_title_wordcloud(word_counts: Counter):
    if plt is None or not word_counts:
        return None

    if WordCloud is not None:
        font_path = find_title_font_path()
        wordcloud_kwargs = {
            "width": 1400,
            "height": 800,
            "background_color": "white",
            "colormap": "tab20c",
            "max_words": 80,
            "prefer_horizontal": 0.9,
        }
        if font_path is not None:
            wordcloud_kwargs["font_path"] = font_path

        cloud = WordCloud(**wordcloud_kwargs).generate_from_frequencies(dict(word_counts.most_common(200)))
        fig, ax = plt.subplots(figsize=(14, 8))
        ax.imshow(cloud, interpolation="bilinear")
        ax.axis("off")
        fig.tight_layout(pad=0)
        return fig

    top_words = word_counts.most_common(36)
    if not top_words:
        return None

    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    font_props = get_title_font_properties()
    max_count = top_words[0][1]
    cols = 6
    rows = int(np.ceil(len(top_words) / cols))

    for index, (word, count) in enumerate(top_words):
        row = index // cols
        col = index % cols
        x_pos = (col + 0.5) / cols
        y_pos = 1 - ((row + 0.5) / max(rows, 1))
        font_size = 12 + 24 * (count / max_count)
        text_kwargs = {
            "ha": "center",
            "va": "center",
            "fontsize": font_size,
            "color": plt.cm.tab20c(index % 20),
            "rotation": 0 if index % 3 else 12,
            "transform": ax.transAxes,
            "alpha": 0.92,
        }
        if font_props is not None:
            text_kwargs["fontproperties"] = font_props
        ax.text(x_pos, y_pos, word, **text_kwargs)

    fig.tight_layout(pad=0.5)
    return fig


def render_cooccurrence_network(graph, word_counts: Counter):
    if nx is None or plt is None or graph is None or graph.number_of_nodes() == 0:
        return None

    node_order = list(graph.nodes())
    edge_order = list(graph.edges())
    max_node_weight = max(word_counts[node] for node in node_order)
    max_edge_weight = max(graph[left][right]["weight"] for left, right in edge_order)
    positions = nx.spring_layout(
        graph,
        seed=42,
        k=max(0.7, 2.4 / np.sqrt(max(graph.number_of_nodes(), 1))),
    )

    fig, ax = plt.subplots(figsize=(10.5, 8.5))
    nx.draw_networkx_edges(
        graph,
        positions,
        ax=ax,
        width=[1.0 + 4.0 * (graph[left][right]["weight"] / max_edge_weight) for left, right in edge_order],
        edge_color="#8fa3b8",
        alpha=0.45,
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        ax=ax,
        node_size=[900 + 3200 * (word_counts[node] / max_node_weight) for node in node_order],
        node_color=[word_counts[node] for node in node_order],
        cmap=plt.cm.YlGnBu,
        linewidths=1.0,
        edgecolors="white",
        alpha=0.96,
    )

    font_props = get_title_font_properties()
    for node, (x_pos, y_pos) in positions.items():
        font_size = 8 + 10 * (word_counts[node] / max_node_weight)
        text_kwargs = {
            "ha": "center",
            "va": "center",
            "fontsize": font_size,
            "bbox": {
                "boxstyle": "round,pad=0.15",
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.78,
            },
        }
        if font_props is not None:
            text_kwargs["fontproperties"] = font_props
        ax.text(x_pos, y_pos, node, **text_kwargs)

    ax.set_axis_off()
    fig.tight_layout()
    return fig


CSV_DOWNLOAD_ENCODINGS = {
    "utf-8-sig（デフォルト / BOM付き）": {
        "encoding": "utf-8-sig",
        "charset": "utf-8",
        "label": "utf-8-sig",
    },
    "utf-8": {
        "encoding": "utf-8",
        "charset": "utf-8",
        "label": "utf-8",
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
            "デフォルトは utf-8-sig（BOM付き）です。"
            " 必要な場合のみ utf-8 を選んでください。"
        ),
        key="csv_encoding",
    )

# CSV（authorを結合）
df_csv = to_csv_ready(df, sep=csv_sep)
csv_text = df_csv.write_csv()
csv_encoding = CSV_DOWNLOAD_ENCODINGS[csv_encoding_label]
csv_bytes = csv_text.encode(csv_encoding["encoding"])
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
# article_title テキスト分析
# =========================
st.divider()
st.subheader("article_title テキスト分析")

if st.session_state.get("article_title_analysis_base_name") != base_name:
    st.session_state.article_title_analysis_base_name = base_name
    st.session_state.show_article_title_wordcloud = False
    st.session_state.show_article_title_cooccurrence = False

if "article_title" not in df.columns:
    st.warning("article_title 列がないため、Word Cloud と共起語ネットワークを作れません。")
else:
    title_texts = (
        df.with_columns(pl.col("article_title").cast(pl.Utf8, strict=False))
        .filter(pl.col("article_title").is_not_null() & (pl.col("article_title").str.len_chars() > 0))
        .get_column("article_title")
        .to_list()
    )

    if not title_texts:
        st.warning("article_title がすべて欠損のため、テキスト分析を作れません。")
    else:
        st.caption(
            "article_title から主要語を抽出して可視化します。"
            " Word Cloud は頻出語、共起語ネットワークは同一タイトル内で一緒に出る語のつながりです。"
        )
        if Tokenizer is None:
            st.info("Janome が未インストールの環境では、簡易分かち書きで代替します。")

        wordcloud_disabled = plt is None
        cooccurrence_disabled = nx is None or plt is None

        button_col1, button_col2 = st.columns(2)
        with button_col1:
            if st.button("Word Cloud を作成", use_container_width=True, disabled=wordcloud_disabled):
                st.session_state.show_article_title_wordcloud = True
        with button_col2:
            if st.button(
                "共起語ネットワークを作成",
                use_container_width=True,
                disabled=cooccurrence_disabled,
            ):
                st.session_state.show_article_title_cooccurrence = True

        if plt is None:
            st.warning("Word Cloud と共起語ネットワークの描画には `matplotlib` が必要です。")
        elif nx is None:
            st.warning("共起語ネットワークの描画には `networkx` が必要です。")

        if (
            st.session_state.get("show_article_title_wordcloud")
            or st.session_state.get("show_article_title_cooccurrence")
        ):
            with st.spinner("article_title を解析中..."):
                token_lists = build_article_title_tokens(tuple(title_texts))

            if not token_lists:
                st.warning("可視化に使える語を article_title から抽出できませんでした。")
            else:
                word_counts = build_word_frequencies(token_lists)

                if st.session_state.get("show_article_title_wordcloud") and not wordcloud_disabled:
                    st.markdown("### Word Cloud")
                    if WordCloud is None:
                        st.info("`wordcloud` 未インストールのため、簡易 Word Cloud 表示に切り替えています。")
                    wordcloud_fig = render_title_wordcloud(word_counts)
                    if wordcloud_fig is None:
                        st.warning("Word Cloud を描画できませんでした。")
                    else:
                        st.pyplot(wordcloud_fig, clear_figure=True, use_container_width=True)

                if st.session_state.get("show_article_title_cooccurrence") and not cooccurrence_disabled:
                    st.markdown("### 共起語ネットワーク")
                    cooccurrence_graph, network_word_counts, min_edge_weight = build_cooccurrence_graph(
                        token_lists
                    )
                    if cooccurrence_graph is None or cooccurrence_graph.number_of_edges() == 0:
                        st.info(
                            "共起関係を十分に抽出できませんでした。"
                            " 取得件数を増やすとネットワークが表示されやすくなります。"
                        )
                    else:
                        st.caption(
                            f"同一タイトル内で {min_edge_weight} 回以上共起した語を中心に表示しています。"
                        )
                        cooccurrence_fig = render_cooccurrence_network(
                            cooccurrence_graph,
                            network_word_counts,
                        )
                        if cooccurrence_fig is None:
                            st.warning("共起語ネットワークを描画できませんでした。")
                        else:
                            st.pyplot(cooccurrence_fig, clear_figure=True, use_container_width=True)

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
