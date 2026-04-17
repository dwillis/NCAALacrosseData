# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pandas",
#     "playwright",
# ]
# ///
"""Men's NCAA lacrosse match stats scraper.

Reads URLs from url_csvs/ncaa_mens_lacrosse_teamurls_{season}.csv and
writes data/ncaa_mens_lacrosse_matchstats_{season}.csv. The matchstatsurl
column from the teamurls CSV is used as the per-team landing page.

The men's page has separate category tables for "offense/defense" and
"goalies"; goalie stats are loaded via the year_stat_category_id=15650
variant of the URL and merged back onto the offense/defense rows.

Usage:
    python NCAAMensLacrosseMatchScraper.py [season] [limit]
"""
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

import pandas as pd
from playwright.sync_api import sync_playwright

GOALIE_STAT_ID = 15650


def extract_team_id(url: str) -> str | None:
    return parse_qs(urlparse(url).query).get("org_id", [None])[0]


def clean_value(val: str | None) -> str:
    if val is None:
        return ""
    val = val.strip()
    if val.endswith("/"):
        val = val[:-1].strip()
    return val


def parse_breakdown(page) -> pd.DataFrame | None:
    table = page.query_selector("#game_breakdown_div table")
    if not table:
        return None
    rows = table.query_selector_all("tr")

    headers: list[str] = []
    data_start = 0
    for i, row in enumerate(rows):
        th_cells = row.query_selector_all("th")
        td_cells = row.query_selector_all("td")
        if th_cells and not td_cells:
            texts = [c.inner_text().strip() for c in th_cells]
            if "Date" in texts and "Opponent" in texts:
                headers = [
                    t.lower().replace(" ", "_").replace("/", "").replace("%", "_pct")
                    for t in texts
                ]
                data_start = i + 1
                break
    if not headers:
        return None

    col_map = {"sog": "sog", "fos_taken": "f_os_taken", "fos_won": "f_os_won"}
    headers = [col_map.get(h, h) for h in headers]

    all_rows = []
    for row in rows[data_start:]:
        cells = row.query_selector_all("td")
        if len(cells) != len(headers):
            continue
        values = [clean_value(c.inner_text()) for c in cells]
        all_rows.append(dict(zip(headers, values)))
    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    df["date"] = df["date"].replace("", pd.NA).ffill()
    df["result"] = df["result"].replace("", pd.NA).ffill()
    return df


def parse_result(result: str) -> tuple[str, str, object]:
    if not result:
        return "", "", pd.NA
    result = result.strip()
    overtime: object = pd.NA
    m = re.match(r"(.+?)\s*\((\d+)\)", result)
    if m:
        score_part = m.group(1).strip()
        overtime = m.group(2)
    else:
        score_part = result
    score_part = re.sub(r"^[WLT]\s+", "", score_part)
    parts = score_part.split("-")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip(), overtime
    return "", "", overtime


def split_team_def(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    teamside = df[df["opponent"] != "Defensive Totals"].copy()
    defside = df[df["opponent"] == "Defensive Totals"].copy()
    return teamside, defside


def school_name(page) -> str:
    el = page.query_selector(
        "xpath=/html/body/div[2]/div/div/div/div/div/div[1]/img"
    )
    if el:
        alt = el.get_attribute("alt")
        if alt:
            return alt.strip()
    card = page.query_selector(".card-header")
    if card:
        card_text = card.inner_text().strip()
        m = re.match(r"(.*?)\s*\(\d+-\d+-?\d*\)", card_text)
        if m:
            return m.group(1).strip()
    return ""


def goto(page, url: str) -> bool:
    try:
        page.goto(url, timeout=30000)
        time.sleep(2)
        return True
    except Exception as e:
        print(f"  Error loading {url}: {e}")
        return False


def process_team(page, url: str) -> pd.DataFrame | None:
    team_id = extract_team_id(url)
    if not goto(page, url):
        return None

    school = school_name(page)
    # Hobart special-case (team_id 282) — sometimes missing alt text
    if not school and team_id == "282":
        school = "Hobart Statesmen"
    if not school:
        print(f"  Could not find team name for {url}")
        return None

    base = parse_breakdown(page)
    if base is None or base.empty:
        print(f"  No match data found for {school}")
        return None

    teamside, defside = split_team_def(base)
    if teamside.empty:
        print(f"  No team rows for {school}")
        return None

    teamside["home_away"] = teamside["opponent"].apply(
        lambda x: "Away" if x.startswith("@") else "Home"
    )
    teamside["opponent"] = teamside["opponent"].apply(
        lambda x: re.sub(r"^@\s*", "", x).split("\n")[0].strip()
    )

    scores = teamside["result"].apply(parse_result)
    teamside["home_score"] = scores.apply(lambda x: x[0])
    teamside["visitor_score"] = scores.apply(lambda x: x[1])
    teamside["overtime"] = scores.apply(lambda x: x[2])

    def outcome(row):
        try:
            hs, vs = int(row["home_score"]), int(row["visitor_score"])
        except (ValueError, TypeError):
            return ""
        if row["home_away"] == "Home":
            return "W" if hs > vs else ("L" if hs < vs else "T")
        return "W" if vs > hs else ("L" if vs < hs else "T")

    teamside["result"] = teamside.apply(outcome, axis=1)
    teamside["team"] = school
    teamside["date"] = pd.to_datetime(teamside["date"], format="%m/%d/%Y", errors="coerce")

    # Offense/defense columns for men's lax
    stat_cols = [c for c in teamside.columns if c not in (
        "date", "team", "opponent", "home_away", "result",
        "home_score", "visitor_score", "overtime"
    )]

    team_out = teamside[[
        "date", "team", "opponent", "home_away", "result",
        "home_score", "visitor_score", "overtime", *stat_cols,
    ]].copy()

    if defside.empty:
        print(f"  No defensive totals for {school}")
        return None

    defside["date"] = pd.to_datetime(defside["date"], format="%m/%d/%Y", errors="coerce")
    def_scores = defside["result"].apply(parse_result)
    defside["home_score"] = def_scores.apply(lambda x: x[0])
    defside["visitor_score"] = def_scores.apply(lambda x: x[1])
    defside["overtime"] = def_scores.apply(lambda x: x[2])
    defside["team"] = school
    def_stat_cols = [c for c in stat_cols if c in defside.columns]
    def_out = defside[[
        "date", "team", "home_score", "visitor_score", "overtime", *def_stat_cols,
    ]].rename(columns={c: f"defensive_{c}" for c in def_stat_cols})

    joined = team_out.merge(
        def_out,
        on=["date", "team", "home_score", "visitor_score", "overtime"],
        how="inner",
    )

    # Fetch goalie stats
    goalie_url = url + f"&year_stat_category_id={GOALIE_STAT_ID}"
    if goto(page, goalie_url):
        g = parse_breakdown(page)
        if g is not None and not g.empty:
            g_team, g_def = split_team_def(g)
            if not g_team.empty:
                g_team["home_away"] = g_team["opponent"].apply(
                    lambda x: "Away" if x.startswith("@") else "Home"
                )
                g_team["opponent"] = g_team["opponent"].apply(
                    lambda x: re.sub(r"^@\s*", "", x).split("\n")[0].strip()
                )
                gs = g_team["result"].apply(parse_result)
                g_team["home_score"] = gs.apply(lambda x: x[0])
                g_team["visitor_score"] = gs.apply(lambda x: x[1])
                g_team["overtime"] = gs.apply(lambda x: x[2])
                g_team["team"] = school
                g_team["date"] = pd.to_datetime(g_team["date"], format="%m/%d/%Y", errors="coerce")

                goalie_keep = [c for c in ("goals_allowed", "saves") if c in g_team.columns]
                g_team_out = g_team[[
                    "date", "team", "opponent", "home_away",
                    "home_score", "visitor_score", "overtime", *goalie_keep,
                ]]

                if not g_def.empty:
                    g_def["date"] = pd.to_datetime(g_def["date"], format="%m/%d/%Y", errors="coerce")
                    gds = g_def["result"].apply(parse_result)
                    g_def["home_score"] = gds.apply(lambda x: x[0])
                    g_def["visitor_score"] = gds.apply(lambda x: x[1])
                    g_def["overtime"] = gds.apply(lambda x: x[2])
                    g_def["team"] = school
                    g_def_keep = [c for c in goalie_keep if c in g_def.columns]
                    g_def_out = g_def[[
                        "date", "team", "home_score", "visitor_score", "overtime",
                        *g_def_keep,
                    ]].rename(columns={c: f"defensive_{c}" for c in g_def_keep})
                    g_team_out = g_team_out.merge(
                        g_def_out,
                        on=["date", "team", "home_score", "visitor_score", "overtime"],
                        how="left",
                    )

                joined = joined.merge(
                    g_team_out,
                    on=["date", "team", "opponent", "home_away",
                        "home_score", "visitor_score", "overtime"],
                    how="left",
                )

    joined["team_id"] = team_id

    numeric_cols = [c for c in joined.columns if c not in (
        "date", "team", "opponent", "home_away", "result", "overtime", "team_id",
    )]
    for col in numeric_cols:
        joined[col] = pd.to_numeric(joined[col], errors="coerce")

    return joined


def main() -> None:
    season = sys.argv[1] if len(sys.argv) > 1 else "2025"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    urls_file = f"url_csvs/ncaa_mens_lacrosse_teamurls_{season}.csv"
    output_file = f"data/ncaa_mens_lacrosse_matchstats_{season}.csv"

    print(f"Reading URLs from {urls_file}")
    urls_df = pd.read_csv(urls_file)
    urls = urls_df.iloc[:, 2].tolist()  # matchstatsurl is 3rd column
    if limit:
        urls = urls[:limit]
    print(f"Processing {len(urls)} teams")

    all_matches: list[pd.DataFrame] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        for i, url in enumerate(urls):
            print(f"[{i+1}/{len(urls)}] Processing {url}")
            try:
                result = process_team(page, url)
                if result is not None and not result.empty:
                    all_matches.append(result)
                    print(f"  Adding {result['team'].iloc[0]} ({len(result)} matches)")
                else:
                    print("  Skipped (no data)")
            except Exception as e:
                print(f"  Error: {e}")
            time.sleep(1)

        browser.close()

    if all_matches:
        final = pd.concat(all_matches, ignore_index=True).drop_duplicates()
        final.to_csv(output_file, index=False)
        print(f"\nWrote {len(final)} matches to {output_file}")
    else:
        print("\nNo data collected!")


if __name__ == "__main__":
    main()
