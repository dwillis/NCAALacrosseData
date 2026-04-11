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


def parse_matches(page):
    """Parse the game_breakdown_div table into team and defensive rows."""
    table = page.query_selector("#game_breakdown_div table")
    if not table:
        return None

    rows = table.query_selector_all("tr")

    # Find header row: must be a row with ONLY th elements containing "Date" and "Opponent"
    headers = []
    data_start = 0
    for i, row in enumerate(rows):
        th_cells = row.query_selector_all("th")
        td_cells = row.query_selector_all("td")
        # Header row has th elements and no td elements
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
        "shatt": "sh_att",
        "sog": "so_g",
        "f/os_won": "f_os_won",
        "f/os_taken": "f_os_taken",
        "g_min": "g_min",
        "clr_att": "clr_att",
        "freepos_shots": "freepos_shots",
        "freepos_goals": "freepos_goals",
    }
    headers = [col_map.get(h, h) for h in headers]

    # Parse data rows (td-only rows with correct column count)
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

    # Fill down date and result for Defensive Totals rows
    df["date"] = df["date"].replace("", pd.NA).ffill()
    df["result"] = df["result"].replace("", pd.NA).ffill()

    return df


def process_team(page, url):
    """Process a single team page and return a DataFrame of match stats."""
    team_id = extract_team_id(url)

    try:
        page.goto(url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading page: {e}")
        return None

    # Extract team name
    school = ""
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

    if not school:
        print(f"  Could not find team name for {url}")
        return None

    # Parse match table
    df = parse_matches(page)
    if df is None or df.empty:
        print(f"  No match data found for {school}")
        return None

    # Split into team rows and defensive totals
    teamside = df[df["opponent"] != "Defensive Totals"].copy()
    defside = df[df["opponent"] == "Defensive Totals"].copy()

    if teamside.empty:
        print(f"  No team rows for {school}")
        return None

    # Process team side
    teamside["home_away"] = teamside["opponent"].apply(
        lambda x: "Away" if x.startswith("@") else "Home"
    )
    teamside["opponent"] = teamside["opponent"].apply(
        lambda x: re.sub(r"^@\s*", "", x).split("\n")[0].strip()
    )

    # Parse result into score and overtime
    def parse_result(result):
        if not result:
            return "", "", ""
        result = result.strip()
        overtime = pd.NA
        match = re.match(r"(.+?)\s*\((\d+)\)", result)
        if match:
            score_part = match.group(1).strip()
            overtime = match.group(2)
        else:
            score_part = result

        # Remove W/L/T prefix if present
        score_part = re.sub(r"^[WLT]\s+", "", score_part)

        parts = score_part.split("-")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip(), overtime
        return "", "", overtime

    scores = teamside["result"].apply(parse_result)
    teamside["team_score"] = scores.apply(lambda x: x[0])
    teamside["opponent_score"] = scores.apply(lambda x: x[1])
    teamside["overtime"] = scores.apply(lambda x: x[2])

    # Determine outcome
    def get_outcome(row):
        try:
            ts = int(row["team_score"])
            os_ = int(row["opponent_score"])
            if ts > os_:
                return "Win"
            elif ts < os_:
                return "Loss"
            else:
                return "Draw"
        except (ValueError, TypeError):
            return ""

    teamside["outcome"] = teamside.apply(get_outcome, axis=1)
    teamside["team"] = school

    # Parse date
    teamside["date"] = pd.to_datetime(teamside["date"], format="%m/%d/%Y", errors="coerce")

    # Define stat columns (lacrosse-specific)
    stat_cols = [
        "fouls", "gs", "goals", "assists", "points", "shots", "sog",
        "ground_balls", "turnovers", "ct", "f_os_won", "f_os_taken",
        "g_min", "goals_allowed", "saves", "w", "l",
        "freepos_shots", "freepos_goals", "rc", "yc",
        "draw_controls", "clears", "clr_att",
    ]

    # Reorder team side columns
    team_cols = ["date", "team", "opponent", "home_away", "outcome",
                 "team_score", "opponent_score", "overtime"]
    team_stat_cols = [c for c in stat_cols if c in teamside.columns]
    teamside = teamside[team_cols + team_stat_cols].copy()

    # Process defensive side
    if defside.empty:
        print(f"  No defensive totals for {school}")
        return None

    defside["date"] = pd.to_datetime(defside["date"], format="%m/%d/%Y", errors="coerce")

    # Parse result for defensive side too (needed for join)
    def_scores = defside["result"].apply(parse_result)
    defside["team_score"] = def_scores.apply(lambda x: x[0])
    defside["opponent_score"] = def_scores.apply(lambda x: x[1])
    defside["outcome"] = ""
    defside["team"] = school
    for idx in defside.index:
        try:
            ts = int(defside.at[idx, "team_score"])
            os_ = int(defside.at[idx, "opponent_score"])
            defside.at[idx, "outcome"] = "Win" if ts > os_ else ("Loss" if ts < os_ else "Draw")
        except (ValueError, TypeError):
            pass

    # Select and rename defensive columns
    def_keep = ["date", "team", "outcome", "team_score", "opponent_score"]
    def_stat_cols = [c for c in stat_cols if c in defside.columns]
    defside = defside[def_keep + def_stat_cols].copy()
    defside = defside.rename(columns={c: f"defensive_{c}" for c in def_stat_cols})

    # Join team and defensive sides
    joined = teamside.merge(
        defside,
        on=["date", "team", "outcome", "team_score", "opponent_score"],
        how="inner",
    )

    joined["team_id"] = team_id

    # Convert numeric columns
    numeric_cols = [c for c in joined.columns
                    if c not in ("date", "team", "opponent", "home_away", "outcome",
                                 "overtime", "g_min", "defensive_g_min")]
    for col in numeric_cols:
        joined[col] = pd.to_numeric(joined[col], errors="coerce")

    return joined


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else "2026"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    urls_file = f"url_csvs/ncaa_womens_lacrosse_teamurls_{season}.csv"
    output_file = f"data/ncaa_womens_lacrosse_matchstats_{season}.csv"

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
                    team_name = result["team"].iloc[0]
                    print(f"  Adding {team_name} ({len(result)} matches)")
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
