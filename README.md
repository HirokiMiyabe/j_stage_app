# J-STAGE Search API GUI (service=3)

J-STAGE Search API (service=3) を用いて、論文の検索と分析を行うための Streamlit ベースの GUI アプリケーションです。

## 🔗 公開アプリ

近日公開

------------------------------------------------------------------------

## ⚠ 利用規約

> ⚠️ **重要事項（J-STAGE 利用規約）**  
>  
> このパッケージは、J-STAGE Search API (service=3) の **非公式クライアント** です。  
> このパッケージを利用する前に、以下の文書を **必ず読み、同意してください**。  
>  
> - J-STAGE 利用規約・ポリシー:  
>   https://www.jstage.jst.go.jp/static/pages/TermsAndPolicies/ForIndividuals/-char/ja
> - J-STAGE WebAPI 利用規約・ポリシー:  
>   https://www.jstage.jst.go.jp/static/pages/WebAPI/-char/ja
> - J-STAGE Web API について:  
>   https://www.jstage.jst.go.jp/static/pages/JstageServices/TAB3/-char/ja
>  
> このパッケージを利用することで、**これらの規約を遵守する責任が利用者自身にあることを認めたものとみなされます**。  
> このパッケージの作者は、その利用によって生じたいかなる損害、損失、違反についても **責任を負いません**。

------------------------------------------------------------------------

## 📌 概要

このアプリケーションは、J-STAGE Search API (service=3) にクエリを送信し、探索的分析を行うためのグラフィカルユーザーインターフェース（GUI）を提供します。

できること:

- 複数の AND 条件による論文検索
- 以下の条件による絞り込み
  - keyword
  - journal (material)
  - author
  - affiliation
  - ISSN
  - cdjournal (internal journal code)
- 開始年の指定
- 最大取得件数の制限
- リクエスト間隔の調整（API 負荷制御）
- 結果のダウンロード
  - CSV
  - JSON
  - Parquet
- 可視化
  - ジャーナル分布
  - 年ごとの出版動向
  - 上位ジャーナルの時系列

------------------------------------------------------------------------

## 🚀 デプロイ（Streamlit Cloud）

このリポジトリは、Streamlit Community Cloud 上でそのまま実行できるように設計されています。

### Python バージョン

以下で指定しています:

`runtime.txt`  
(`python 3.12`)

### 依存関係

以下で定義しています:

`requirements.txt`

含まれる主なパッケージ:

- `streamlit`
- `polars`
- `altair`
- `requests`
- `lxml`
- `j_staget`（GitHub からインストール）

------------------------------------------------------------------------

## 🖥 ローカル開発

リポジトリをクローンします:

```bash
git clone https://github.com/<YOUR_NAME>/J_STAGE_APP.git
cd J_STAGE_APP
```

仮想環境を作成します:

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

依存関係をインストールします:

```bash
pip install -r requirements.txt
```

起動します:

```bash
streamlit run app.py
```

------------------------------------------------------------------------

## アーキテクチャ

`app.py` # Streamlit GUI  
`jstage_fetcher.py` # API 取得ロジック  
`requirements.txt`  
`runtime.txt`

保守性と再現性を高めるため、API のロジックは UI から分離されています。

------------------------------------------------------------------------

## 📊 研究目的

このツールは、以下の用途を想定しています。

- 書誌情報の探索
- ジャーナル単位の分析
- 長期的なトレンド分析
- 学術研究の支援

大量データの収集を目的としたものではありません。

------------------------------------------------------------------------

## 📜 ライセンス

このプロジェクトは MIT License の下で提供されています。  
詳細は [LICENSE ファイル](https://github.com/HirokiMiyabe/j_stage_app/blob/main/LICENSE) を参照してください。  

------------------------------------------------------------------------

## 👤 作者

- 名前: Hiroki Miyabe
- 所属: 東京大学（2026-）
- CV: [researchmap](https://researchmap.jp/mybhrk_ut_wsd)

## クレジット

- 情報提供: [J-STAGE](https://www.jstage.jst.go.jp/browse/-char/ja)
- 提供: [J-STAGE](https://www.jstage.jst.go.jp/browse/-char/ja)
