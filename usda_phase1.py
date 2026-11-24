"""County coverage and acreage-weighted USDA yield analysis."""
from pathlib import Path
import json

import pandas as pd
import requests


STATE_CODES = {"ILLINOIS": "17", "IOWA": "19"}
UTILIZATION = {"CORN": "GRAIN", "SOYBEANS": "ALL UTILIZATION PRACTICES"}
KEYS = ["STATE_ANSI", "COUNTY_ANSI", "COMMODITY_DESC", "YEAR"]
GROUP = ["STATE_NAME", "COMMODITY_DESC", "YEAR"]


def geographic_counties(config):
    """Read geographic county identifiers from the project's Census boundaries."""
    data = json.loads(Path("data/geographic/counties_5digit.geojson").read_text(encoding="utf-8"))
    names = {code: name for name, code in STATE_CODES.items() if name in config["states"]}
    rows = [{"STATE_NAME": names[p["STATE"]], "STATE_ANSI": p["STATE"],
             "COUNTY_ANSI": p["COUNTY"], "COUNTY_NAME": p["NAME"]}
            for feature in data["features"] for p in [feature["properties"]]
            if p["STATE"] in names]
    geo = pd.DataFrame(rows)
    if geo.duplicated(["STATE_ANSI", "COUNTY_ANSI"]).any():
        raise ValueError("Duplicate geographic county identifiers.")
    expected = {"IOWA": 99, "ILLINOIS": 102}
    for state, group in geo.groupby("STATE_NAME"):
        if len(group) != expected[state]:
            raise ValueError(f"Unexpected geographic county count for {state}: {len(group)}")
    if set(geo["STATE_NAME"]) != set(config["states"]):
        raise ValueError("Phase 1 supports configured Iowa and Illinois states only.")
    return geo


def load_usda_measure(config, api_key, statistic, level, unit, cache_path_fn, force_refresh=False):
    """Retrieve one comparable measure, using the notebook's configuration-keyed cache."""
    query_config = {**config, "statistic": statistic, "aggregation_level": level,
                    "yield_unit": unit, "phase1_query_version": 2}
    path = cache_path_fn(query_config, crop_utilization=UTILIZATION)
    if path.exists() and not force_refresh:
        print(f"Loading cached {level} {statistic}: {path}")
        return pd.read_pickle(path)
    frames = []
    for state in config["states"]:
        for crop in config["crops"]:
            params = {"key": api_key, "source_desc": "SURVEY", "sector_desc": "CROPS",
                      "commodity_desc": crop, "util_practice_desc": UTILIZATION[crop],
                      "statisticcat_desc": statistic, "agg_level_desc": level,
                      "state_name": state, "year__GE": config["start_year"],
                      "year__LE": config["end_year"], "unit_desc": unit,
                      "domain_desc": "TOTAL", "prodn_practice_desc": "ALL PRODUCTION PRACTICES",
                      "freq_desc": "ANNUAL", "reference_period_desc": "YEAR"}
            try:
                counts = requests.get("https://quickstats.nass.usda.gov/api/get_counts/", params=params, timeout=60)
                counts.raise_for_status()
                count = counts.json().get("count")
                if not isinstance(count, int) or count < 0 or count > 50000:
                    raise ValueError("Invalid USDA count or request exceeds 50,000 records.")
                if count == 0:
                    print(f"No USDA records: {state}, {crop}, {level}, {statistic}")
                    continue
                response = requests.get("https://quickstats.nass.usda.gov/api/api_GET/", params=params, timeout=60)
                response.raise_for_status()
                records = response.json().get("data")
            except requests.RequestException as exc:
                raise RuntimeError(f"USDA request failed for {state}, {crop}, {level}, {statistic} ({type(exc).__name__}).") from None
            if not isinstance(records, list) or len(records) != count:
                raise ValueError("USDA data response does not match its reported count.")
            frame = pd.DataFrame(records)
            frame.columns = ["CV_%" if c == "CV (%)" else c.upper() for c in frame.columns]
            checks = {"STATE_NAME": state, "COMMODITY_DESC": crop, "UTIL_PRACTICE_DESC": UTILIZATION[crop],
                      "STATISTICCAT_DESC": statistic, "AGG_LEVEL_DESC": level, "UNIT_DESC": unit,
                      "DOMAIN_DESC": "TOTAL", "PRODN_PRACTICE_DESC": "ALL PRODUCTION PRACTICES",
                      "SOURCE_DESC": "SURVEY", "FREQ_DESC": "ANNUAL", "REFERENCE_PERIOD_DESC": "YEAR"}
            for col, value in checks.items():
                if col not in frame or not frame[col].eq(value).all():
                    raise ValueError(f"Unexpected USDA response field: {col}")
            years = pd.to_numeric(frame["YEAR"], errors="coerce")
            if years.isna().any():
                raise ValueError("USDA response contains invalid years.")
            # Quick Stats can ignore one bound when both year operators are sent.
            frame = frame.loc[years.between(config["start_year"], config["end_year"])].copy()
            frames.append(frame)
    if not frames:
        raise ValueError(f"No USDA {level} {statistic} records were returned.")
    result = pd.concat(frames, ignore_index=True)
    result.to_pickle(path)
    print(f"Cached {level} {statistic}: {len(result):,} records at {path}")
    return result


def prepare_measure(data, geo, level, value_name):
    """Normalize identifiers and values; retain invalid published values for auditing."""
    frame = data.copy()
    frame["STATE_ANSI"] = frame["STATE_ANSI"].astype("string").str.zfill(2)
    frame["YEAR"] = pd.to_numeric(frame["YEAR"], errors="coerce")
    frame[value_name] = pd.to_numeric(frame["VALUE"].astype("string").str.replace(",", "", regex=False).str.strip(), errors="coerce")
    frame.loc[frame[value_name] < 0, value_name] = float("nan")
    if level == "COUNTY":
        frame["COUNTY_ANSI"] = frame["COUNTY_ANSI"].astype("string").str.zfill(3)
        frame = frame.merge(geo[["STATE_ANSI", "COUNTY_ANSI"]], on=["STATE_ANSI", "COUNTY_ANSI"], how="inner", validate="many_to_one")
        keys = KEYS
    else:
        keys = ["STATE_ANSI", "COMMODITY_DESC", "YEAR"]
    dup = frame.duplicated(keys, keep=False)
    if dup.any():
        raise ValueError(f"{level} {value_name}: {dup.sum()} records have duplicate keys; inspect classifications before joining.")
    return frame


def build_analysis(config, geo, yield_raw, acreage_raw, state_acres_raw, state_yield_raw):
    """Build a complete county grid and calculate comparable coverage and yields."""
    y = prepare_measure(yield_raw, geo, "COUNTY", "YIELD_NUM")
    a = prepare_measure(acreage_raw, geo, "COUNTY", "ACRES")
    sa = prepare_measure(state_acres_raw, geo, "STATE", "STATE_ACRES")
    sy = prepare_measure(state_yield_raw, geo, "STATE", "STATE_YIELD")
    grid = geo.merge(pd.DataFrame({"COMMODITY_DESC": config["crops"]}), how="cross").merge(
        pd.DataFrame({"YEAR": range(config["start_year"], config["end_year"] + 1)}), how="cross")
    for data, value, flag in [(y, "YIELD_NUM", "YIELD_REPORTED"), (a, "ACRES", "ACRES_REPORTED")]:
        fields = data[KEYS + [value, "VALUE"]].rename(columns={"VALUE": flag + "_VALUE"})
        fields[flag] = True
        grid = grid.merge(fields, on=KEYS, how="left", validate="one_to_one")
        grid[flag] = grid[flag].fillna(False).astype(bool)
    grid["PAIRED"] = grid["YIELD_NUM"].notna() & grid["ACRES"].gt(0)
    grid["PAIRED_YIELD"] = grid["YIELD_NUM"].where(grid["PAIRED"])
    grid["PAIRED_ACRES"] = grid["ACRES"].where(grid["PAIRED"])
    grid["YIELD_TIMES_ACRES"] = grid["PAIRED_YIELD"] * grid["PAIRED_ACRES"]
    annual = grid.groupby(GROUP, as_index=False).agg(
        total_counties=("COUNTY_ANSI", "size"), reporting_counties=("YIELD_NUM", "count"),
        matched_counties=("PAIRED", "sum"), unweighted_yield=("YIELD_NUM", "mean"),
        matched_unweighted_yield=("PAIRED_YIELD", "mean"), matched_acres=("PAIRED_ACRES", lambda s: s.sum(min_count=1)),
        weighted_numerator=("YIELD_TIMES_ACRES", lambda s: s.sum(min_count=1)))
    annual["coverage_pct"] = 100 * annual["reporting_counties"] / annual["total_counties"]
    annual["weighted_yield"] = annual["weighted_numerator"] / annual["matched_acres"].where(annual["matched_acres"].gt(0))
    for frame, name in [(sa, "STATE_ACRES"), (sy, "STATE_YIELD")]:
        annual = annual.merge(frame[["STATE_NAME", "COMMODITY_DESC", "YEAR", name]], on=GROUP, how="left", validate="one_to_one")
    annual["acreage_coverage_pct"] = 100 * annual["matched_acres"] / annual["STATE_ACRES"].where(annual["STATE_ACRES"].gt(0))
    annual["acreage_over_100"] = annual["acreage_coverage_pct"].gt(100)
    annual["unweighted_difference"] = annual["unweighted_yield"] - annual["STATE_YIELD"]
    annual["weighted_difference"] = annual["weighted_yield"] - annual["STATE_YIELD"]
    return grid, annual, y, a, sa, sy
