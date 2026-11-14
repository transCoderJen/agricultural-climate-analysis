# USDA County-Level Crop Yield Analysis

A Python/Jupyter Notebook project for downloading, validating, exploring, and visualizing county-level **corn and soybean yields** from the USDA National Agricultural Statistics Service (NASS) Quick Stats API. The analysis is designed to support configurable U.S. states and study years, with optional interactive county-level visualizations.

## Data source

- **USDA NASS Quick Stats:** https://quickstats.nass.usda.gov/
- **Quick Stats API documentation and key registration:** https://quickstats.nass.usda.gov/api

The project currently focuses on county-level **corn (grain)** and **soybeans** measured in **bushels per acre**. The original study period is **2015–2025**.

## 1. Prerequisites

- Python 3 and Jupyter Notebook or JupyterLab (a Conda environment is also fine)
- Internet access for the initial USDA download
- A personal USDA NASS Quick Stats API key

Install the Python dependencies in a notebook cell:

```python
%pip install matplotlib seaborn pandas requests python-dotenv geopandas plotly ipywidgets
```

If using interactive Plotly maps, ensure your Jupyter environment supports Plotly output and widgets. Restart the notebook kernel after installing packages if necessary.

## 2. Get your own USDA NASS API key

1. Open the [USDA Quick Stats API page](https://quickstats.nass.usda.gov/api).
2. Follow the instructions to **request an API key** and enter your email address.
3. Check your email for the key sent by USDA NASS.
4. In the **project root folder** (the folder containing your notebook), create a plain-text file named **`.env`**.
5. Add your key on one line:

   ```dotenv
   NASS_API_KEY=YOUR_PERSONAL_API_KEY_HERE
   ```

   Replace `YOUR_PERSONAL_API_KEY_HERE` with the key you received. Do not include angle brackets or extra spaces.

6. Save the file. In running the notebook automatically locates the key in the .env file.

**Important:** Keep `.env` private. Do not paste your key into the notebook, commit it to GitHub, or share screenshots showing the key. Add the following to `.gitignore`:

```gitignore
.env
.env.*
!.env.example
__pycache__/
.ipynb_checkpoints/
```

If you use a different environment variable name in your notebook, the name in `.env` must match it exactly. You can optionally create a safe `.env.example` file containing only `NASS_API_KEY=`, with no real key.

## 3. Configure the study

Find the `STUDY_CONFIG` section in the notebook. Choose the states and years you want to analyze. For example:

```python
STUDY_CONFIG = {
    'states': ['IOWA', 'ILLINOIS'],
    'crops': ['CORN', 'SOYBEANS'],
    'start_year': 2015,
    'end_year': 2025,
}
```

**Note:** This is an illustrative configuration. Preserve the actual keys and additional settings used by your notebook, such as statistic, geographic aggregation, and units. Change only the desired configuration values.

The crop-specific USDA utilization settings are:

```python
if crop_utilization is None:
    crop_utilization = {
        'CORN': ['GRAIN'],
        'SOYBEANS': ['ALL UTILIZATION PRACTICES'],
    }
```

The project is intended to handle one or multiple selected states. Availability and reporting completeness can vary by state, county, crop, and year.

## 4. Run the notebook

1. Open the project notebook in Jupyter.
2. Confirm the `.env` file is accessible from the notebook's working directory.
3. Run the setup/import and configuration cells.
4. Run the USDA data-loading cell. The notebook uses the API key to retrieve the configured yield observations.
5. Continue through cleaning, validation, and exploratory analysis cells.
6. Explore the plots and interactive controls, including state, county, crop, and year selections where provided.

Example loading call:

```python
crop_df = load_usda_crop_yields(
    config=STUDY_CONFIG,
    api_key=NASS_API_KEY,
)
```

## 5. Caching and refreshing data

The loader caches downloaded data under `data/cache` to avoid unnecessary repeated API requests. Changing the configuration should produce a corresponding cache entry. To explicitly request fresh data, use:

```python
crop_df = load_usda_crop_yields(
    config=STUDY_CONFIG,
    api_key=NASS_API_KEY,
    force_refresh=True,
)
```

A forced refresh makes new USDA requests, so use it only when needed. Cache behavior depends on the loader implementation and its version.

## 6. Understanding the outputs

The notebook may include:

- Data cleaning and checks for numeric yields, duplicates, and combined-county records
- County reporting coverage and longitudinal completeness checks
- Boxplots of county-year yield distributions by state and crop
- Annual average county yields and trends
- Interactive geographic maps and county-level yield comparisons

**Interpretation notes:** County-year observations are not individual farm records. An average of county yields gives each reporting county equal weight and is **not** the official acreage-weighted statewide yield. Missing county-year observations should not be interpreted as zero yield. Corn and soybean yields are both reported in bushels per acre, but a bushel represents different crop-specific weights.

## 7. Troubleshooting

| Issue | What to check |
|---|---|
| `NASS_API_KEY not found` | Confirm `.env` is named correctly, is in the expected folder, and uses `NASS_API_KEY=`. |
| HTTP 400 `invalid query` | Check the crop-specific utilization practice, state, year, unit, and other USDA API filters. |
| HTTP 401/403 | Verify the API key and consult USDA's API guidance. |
| `ModuleNotFoundError` | Install dependencies with `%pip` in the active notebook kernel, then restart it. |
| Map has missing counties | Check county FIPS identifiers, boundary joins, combined-county records, and reporting coverage. |
| Unexpected cached results | Verify the study configuration and, if necessary, run with `force_refresh=True`. |

## 8. Planned climate integration

The USDA yield analysis can later be joined to NASA POWER climate observations by geographic unit and year to explore associations between crop yields, temperature, and precipitation. This notebook's yield data alone cannot establish that climate or crop rotation caused changes in yield.

## Security reminder

**Never share your personal NASS API key.** Each user should request their own key and save it locally in a `.env` file excluded from version control.
