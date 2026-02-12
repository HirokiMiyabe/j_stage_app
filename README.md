# J-STAGE Search API GUI (service=3)

A Streamlit-based GUI application for searching and analyzing articles
using the J-STAGE Search API (service=3).

🔗 Deployed App\
Coming Soon

------------------------------------------------------------------------


## ⚠ Terms of Use

> ⚠️ **Important Notice (J-STAGE Terms of Use)**  
>  
> This package is an **unofficial client** for the J-STAGE Search API (service=3).  
> Before using this package, **you must read and agree to** the following documents:
>  
> - J-STAGE Terms And Policies:  
>   https://www.jstage.jst.go.jp/static/pages/TermsAndPolicies/ForIndividuals/-char/ja"
> - J-STAGE WebAPI Terms And Policies:  
>   https://www.jstage.jst.go.jp/static/pages/WebAPI/-char/ja
> - About J-STAGE Web API:  
>   https://www.jstage.jst.go.jp/static/pages/JstageServices/TAB3/-char/ja
>  
> By using this package, **you acknowledge that you are solely responsible for complying with these terms**.  
> The author of this package assumes **no responsibility or liability** for any damages, losses, or violations arising from its use.

------------------------------------------------------------------------
## 📌 Overview

This application provides a graphical user interface (GUI) for querying
the J-STAGE Search API (service=3) and performing exploratory analysis.

Users can:

-   Search articles with multiple AND conditions
-   Filter by:
    -   keyword
    -   journal (material)
    -   author
    -   affiliation
    -   ISSN
    -   cdjournal (internal journal code)
-   Set start year
-   Limit maximum records
-   Adjust request interval (API load control)
-   Download results as:
    -   CSV
    -   JSON
    -   Parquet
-   Visualize:
    -   Journal distribution
    -   Yearly publication trends
    -   Top journal time series

------------------------------------------------------------------------



## 🚀 Deployment (Streamlit Cloud)

This repository is designed to run directly on Streamlit Community
Cloud.

### Python Version

Specified in:

runtime.txt
(python 3.12)
### Dependencies

Defined in:

requirements.txt

Including:

-   streamlit
-   polars
-   altair
-   requests
-   lxml
-   j_staget (installed from GitHub)

------------------------------------------------------------------------

## 🖥 Local Development

Clone the repository:

``` bash
git clone https://github.com/<YOUR_NAME>/J_STAGE_APP.git
cd J_STAGE_APP
```

Create virtual environment:

``` bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

Install dependencies:

``` bash
pip install -r requirements.txt
```

Run:

``` bash
streamlit run app.py
```

------------------------------------------------------------------------

## 🧠 Architecture

app.py \# Streamlit GUI\
jstage_fetcher.py \# API fetch logic\
requirements.txt\
runtime.txt

The API logic is separated from the UI for maintainability and
reproducibility.

------------------------------------------------------------------------

## 📊 Research Purpose

This tool is intended for:

-   Bibliometric exploration
-   Journal-level analysis
-   Longitudinal trend analysis
-   Academic research support

It is not intended for bulk data harvesting.

------------------------------------------------------------------------

## 📜 License

This project is licensed under the MIT License.
See the [LICENSE file](https://github.com/HirokiMiyabe/j_stage_app/blob/main/LICENSE) for details.

------------------------------------------------------------------------

## 👤 Author

- Name: Hiroki Miyabe\
- Affiliation: The Univeysity of Tokyo((2026– ))
- CV: [researchmap] (https://researchmap.jp/mybhrk_ut_wsd)

## Credits

- Data source: [J-STAGE](https://www.jstage.jst.go.jp/browse/-char/ja)
- Powered by [J-STAGE](https://www.jstage.jst.go.jp/browse/-char/ja)