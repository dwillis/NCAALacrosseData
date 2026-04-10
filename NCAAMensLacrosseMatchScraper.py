# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pandas",
#     "playwright",
# ]
# ///

import sys
import time
import re
import pandas as pd
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright


def extract_team_id(url):
    """Extract org_id from the URL query parameters."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return params.get("org_id", [None])[0]


def clean_value(val):
    """Strip trailing slashes and whitespace from cell values."""
    if val is None:
        return ""
    val = val.strip()
    if val.endswith("/"):
        val = val[:-1].strip()
    return val


def get_school_name(page, url):
    """Extract team name, with special case for Hobart."""
    if "org_id=282" in url:
        return "Hobart Statesmen"

    school = ""
    try:
        el = page.query_selector(
            "xpath=/html/body/div[2]/div/div/div/div/div/div[1]/img"
        )
        if el:
            school = el.get_attribute("alt") or ""
            school = school.strip()
    except Exception:
        pass

    if not school:
        try:
            el = page.query_selector(
                "xpath=/html/body/div[2]/div/div/div/div/div/div[1]/a"
            )
            if el:
                school = el.inner_text().strip()
        except Exception:
            pass

    if not school:
        try:
            card = page.query_selector(".card-header")
            if card:
                card_text = card.inner_text().strip()
                match = re.match(r"(.*?)\s*\(\d+-\d+-?\d*\)", card_text)
                if match:
                    school = match.group(1).strip()
        except Exception:
            pass

    return school


def parse_table(page):
    """Parse the game_breakdown_div table into rows."""
    table = page.query_selector("#game_breakdown_div table")
    if not table:
        return None

    rows = table.query_selector_all("tr")

    # Find header row
    headers = []
    data_start = 0
    for i, row in enumerate(rows):
        th_cells = row.query_selector_all("th")
        td_cells = row.query_selector_all("td")
        if len(th_cells) > 0 and len(td_cells) == 0:
            texts = [c.inner_text().strip() for c in th_cells]
            if "Date" in texts and "Opponent" in texts:
                headers = [t.lower().replace(" ", "_") for t in texts]
                data_start = i + 1
                break

    if not headers:
        return None

    # Column name mapping
    col_map = {
        "f/os_taken": "f_os_taken",
    }
    headers = [col_map.get(h, h) for h in headers]

    # Parse data rows
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


def split_and_join(df, stat_cols, school):
    """Split team/defensive rows, parse results, and join."""
    teamside = df[df["opponent"] != "Defensive Totals"].copy()
    defside = df[df["opponent"] == "Defensive Totals"].copy()

    if teamside.empty:
        return None

    # Home/away
    teamside["home_away"] = teamside["opponent"].apply(
        lambda x: "Away" if x.startswith("@") else "Home"
    )
    teamside["opponent"] = teamside["opponent"].apply(
        lambda x: re.sub(r"^@\s*", "", x).split("\n")[0].strip()
    )

    # Parse result into scores and overtime
    def parse_result(result):
        if not result:
            return "", "", pd.NA
        result = result.strip()
        overtime = pd.NA
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

    scores = teamside["result"].apply(parse_result)
    teamside["home_score"] = scores.apply(lambda x: x[0])
    teamside["visitor_score"] = scores.apply(lambda x: x[1])
    teamside["overtime"] = scores.apply(lambda x: x[2])

    # Determine W/L based on home/away and scores
    def get_result(row):
        try:
            hs = int(row["home_score"])
            vs = int(row["visitor_score"])
            if row["home_away"] == "Home":
                return "W" if hs > vs else ("L" if hs < vs else "T")
            else:
                return "W" if vs > hs else ("L" if vs < hs else "T")
        except (ValueError, TypeError):
            return ""

    teamside["result"] = teamside.apply(get_result, axis=1)
    teamside["team"] = school
    teamside["date"] = pd.to_datetime(teamside["date"], format="%m/%d/%Y", errors="coerce")

    # Reorder team side columns
    team_cols = ["date", "team", "opponent", "home_away", "result",
                 "home_score", "visitor_score", "overtime"]
    team_stat_cols = [c for c in stat_cols if c in teamside.columns]
    teamside = teamside[team_cols + team_stat_cols].copy()

    if defside.empty:
        return teamside, None

    # Process defensive side
    defside["date"] = pd.to_datetime(defside["date"], format="%m/%d/%Y", errors="coerce")
    def_scores = defside["result"].apply(parse_result)
    defside["home_score"] = def_scores.apply(lambda x: x[0])
    defside["visitor_score"] = def_scores.apply(lambda x: x[1])
    defside["overtime"] = def_scores.apply(lambda x: x[2])
    defside["team"] = school

    def_keep = ["date", "team", "home_score", "visitor_score", "overtime"]
    def_stat_cols = [c for c in stat_cols if c in defside.columns]
    defside = defside[def_keep + def_stat_cols].copy()
    defside = defside.rename(columns={c: f"defensive_{c}" for c in def_stat_cols})

    joined = teamside.merge(
        defside,
        on=["date", "team", "home_score", "visitor_score", "overtime"],
        how="inner",
    )
    return joined, None


def process_team(page, url):
    """Process a single team page and return a DataFrame of match stats."""
    try:
        page.goto(url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading page: {e}")
        return None

    school = get_school_name(page, url)
    if not school:
        print(f"  Could not find team name for {url}")
        return None

    print(f"  Adding {school}")

    # Parse main match table
    df = parse_table(page)
    if df is None or df.empty:
        print(f"  No match data found for {school}")
        return None

    main_stat_cols = [
        "goals", "assists", "points", "shots", "sog",
        "gb", "to", "ct", "fo_won", "f_os_taken",
    ]

    result = split_and_join(df, main_stat_cols, school)
    if result is None:
        return None
    joinedmatches = result[0]

    # Scrape goalie stats from separate URL
    goalie_url = url + "&year_stat_category_id=15650"
    try:
        page.goto(goalie_url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading goalie page: {e}")
        return joinedmatches

    g_df = parse_table(page)
    if g_df is None or g_df.empty:
        print(f"  No goalie data for {school}")
        return joinedmatches

    goalie_stat_cols = ["goals_allowed", "saves"]

    g_teamside = g_df[g_df["opponent"] != "Defensive Totals"].copy()
    g_defside = g_df[g_df["opponent"] == "Defensive Totals"].copy()

    if g_teamside.empty:
        return joinedmatches

    # Parse goalie team side
    g_teamside["home_away"] = g_teamside["opponent"].apply(
        lambda x: "Away" if x.startswith("@") else "Home"
    )
    g_teamside["opponent"] = g_teamside["opponent"].apply(
        lambda x: re.sub(r"^@\s*", "", x).split("\n")[0].strip()
    )

    def parse_result(result):
        if not result:
            return "", "", pd.NA
        result = result.strip()
        overtime = pd.NA
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

    scores = g_teamside["result"].apply(parse_result)
    g_teamside["home_score"] = scores.apply(lambda x: x[0])
    g_teamside["visitor_score"] = scores.apply(lambda x: x[1])
    g_teamside["overtime"] = scores.apply(lambda x: x[2])
    g_teamside["team"] = school
    g_teamside["date"] = pd.to_datetime(g_teamside["date"], format="%m/%d/%Y", errors="coerce")

    # Clean slash from goalie stat values
    for col in ["g_min", "goals_allowed", "saves"]:
        if col in g_teamside.columns:
            g_teamside[col] = g_teamside[col].apply(
                lambda x: str(x).replace("/", "").strip() if pd.notna(x) else x
            )
        if col in g_defside.columns:
            g_defside[col] = g_defside[col].apply(
                lambda x: str(x).replace("/", "").strip() if pd.notna(x) else x
            )

    g_team_cols = ["date", "team", "opponent", "home_away", "home_score",
                   "visitor_score", "overtime"]
    g_team_stat_cols = [c for c in goalie_stat_cols if c in g_teamside.columns]
    g_teamside = g_teamside[g_team_cols + g_team_stat_cols].copy()

    # Process goalie defensive side
    if not g_defside.empty:
        g_defside["date"] = pd.to_datetime(g_defside["date"], format="%m/%d/%Y", errors="coerce")
        g_def_scores = g_defside["result"].apply(parse_result)
        g_defside["home_score"] = g_def_scores.apply(lambda x: x[0])
        g_defside["visitor_score"] = g_def_scores.apply(lambda x: x[1])
        g_defside["overtime"] = g_def_scores.apply(lambda x: x[2])
        g_defside["team"] = school

        g_def_keep = ["date", "team", "home_score", "visitor_score", "overtime"]
        g_def_stat_cols = [c for c in goalie_stat_cols if c in g_defside.columns]
        g_defside = g_defside[g_def_keep + g_def_stat_cols].copy()
        g_defside = g_defside.rename(columns={c: f"defensive_{c}" for c in g_def_stat_cols})

        g_joined = g_teamside.merge(
            g_defside,
            on=["date", "team", "home_score", "visitor_score", "overtime"],
            how="inner",
        )
    else:
        g_joined = g_teamside

    # Join goalie stats with main match stats
    all_joined = joinedmatches.merge(
        g_joined,
        on=["date", "team", "opponent", "home_away", "home_score",
            "visitor_score", "overtime"],
        how="inner",
    )

    # Convert numeric columns
    numeric_cols = [c for c in all_joined.columns
                    if c not in ("date", "team", "opponent", "home_away",
                                 "result", "overtime")]
    for col in numeric_cols:
        all_joined[col] = pd.to_numeric(all_joined[col], errors="coerce")

    return all_joined


def main():
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

    all_matches = []

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
                    print(f"  ({len(result)} matches)")
                else:
                    print(f"  Skipped (no data)")
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
