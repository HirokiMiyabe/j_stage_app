## Setup

この Streamlit アプリは、取得ロジックを **独立パッケージ `j_staget`** に切り出して利用します。

### 推奨ディレクトリ配置（開発時）

`j_stage_app` と `j_staget` を **隣同士**に置く想定です（requirements.txt の `-e ../j_staget` が効きます）。

```
your-workspace/
  j_staget/
  j_stage_app/
```

### 仮想環境の作成 & インストール

```bash
cd j_stage_app

python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 起動
streamlit run app.py
```

### `j_staget` を別の方法で入れたい場合

- **PyPI に公開している**なら：requirements.txt の `-e ../j_staget` を削除して `pip install j_staget`
- **GitHub から入れる**なら：`pip install "j_staget @ git+https://..."`
