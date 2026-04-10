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
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright


ROOT_URL = "https://stats.ncaa.org"


def clean_value(val):
    """Strip trailing slashes and whitespace."""
    if val is None:
        return ""
    val = val.strip()
    if val.endswith("/"):
        val = val[:-1].strip()
    return val


def to_numeric(val):
    """Convert string to numeric, stripping commas and dashes."""
    if val is None:
        return float("nan")
    val = str(val).strip().replace(",", "").replace("-", "")
    if val == "":
        return float("nan")
    try:
        return float(val)
    except ValueError:
        return float("nan")


def get_school_name(page, url):
    """Extract team name, with special case for Hobart."""
    parsed = urlparse(url)
    # Check for Hobart by path (playerstatsurl format: /team/282/stats/...)
    if "/team/282/" in parsed.path:
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


def process_team(page, stats_url, season):
    """Scrape player stats from team stats page."""

    try:
        page.goto(stats_url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading page: {e}")
        return None

    school = get_school_name(page, stats_url)
    if not school:
        print(f"  Could not find team name for {stats_url}")
        return None

    # Parse stat_grid table
    stat_grid = page.query_selector("#stat_grid")
    if not stat_grid:
        print(f"  No stat_grid table found for {school}")
        return None

    # Get headers
    header_row = stat_grid.query_selector("thead tr") or stat_grid.query_selector("tr")
    if not header_row:
        return None

    header_cells = header_row.query_selector_all("th")
    headers = [c.inner_text().strip().lower().replace(" ", "_") for c in header_cells]

    col_map = {
        "#": "number",
        "player": "roster_name",
        "f/os_taken": "f_os_taken",
    }
    headers = [col_map.get(h, h) for h in headers]

    # Extract ncaa_ids from player links
    player_links = stat_grid.query_selector_all('a[href*="/player/index"]')
    ncaa_ids = []
    for link in player_links:
        href = link.get_attribute("href") or ""
        id_match = re.search(r"/player/index/(\d+)", href)
        if id_match:
            ncaa_ids.append(id_match.group(1))
        else:
            # Try alternate pattern
            id_match = re.search(r"stats_player_seq=(\d+)", href)
            ncaa_ids.append(id_match.group(1) if id_match else "")

    # Get body rows
    body_rows = stat_grid.query_selector_all("tbody tr")
    players = []
    ncaa_idx = 0

    for row in body_rows:
        cells = row.query_selector_all("td")
        if len(cells) != len(headers):
            continue

        values = [clean_value(c.inner_text()) for c in cells]
        record = dict(zip(headers, values))

        # Skip totals rows
        name = record.get("roster_name", "")
        if name in ("Totals", "Opponent Totals", "TEAM", ""):
            continue

        record["full_name"] = name

        # Split name on space (men's format: "First Last")
        name_parts = name.split()
        record["first_name"] = name_parts[0] if name_parts else ""
        record["last_name"] = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        record["team"] = school
        record["season"] = int(season)

        # Assign ncaa_id from links
        if ncaa_idx < len(ncaa_ids):
            record["ncaa_id"] = ncaa_ids[ncaa_idx]
            ncaa_idx += 1
        else:
            record["ncaa_id"] = ""

        players.append(record)

    if not players:
        print(f"  No players found for {school}")
        return None

    df = pd.DataFrame(players)

    # Convert numeric columns
    numeric_cols = [
        "number", "gp", "gs", "goals", "assists", "points",
        "shots", "sog", "gb", "to", "ct",
        "fo_won", "f_os_taken",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(to_numeric)

    # Replace NaN with 0 to match R behavior
    for col in df.columns:
        if col not in ("season", "team", "full_name", "roster_name",
                       "first_name", "last_name", "yr", "pos", "jersey"):
            if col in df.columns:
                df[col] = df[col].fillna(0)

    # Rename columns to match existing output format
    rename_map = {
        "season": "Season",
        "team": "Team",
        "full_name": "Full Name",
        "roster_name": "Roster Name",
        "first_name": "First Name",
        "last_name": "Last Name",
        "yr": "Year",
        "pos": "Position",
        "number": "Jersey Number",
        "gp": "Games Played",
        "gs": "Games Started",
        "goals": "Goals",
        "assists": "Assists",
        "points": "Points",
        "shots": "Shots",
        "sog": "Shots on Goal",
        "gb": "Ground Balls",
        "to": "Turnovers",
        "ct": "Caused Turnovers",
        "fo_won": "Faceoffs Won",
        "f_os_taken": "Faceoffs Taken",
        "ncaa_id": "NCAA id",
    }

    # Reorder columns to match expected format
    output_cols = [
        "season", "team", "jersey", "full_name", "roster_name",
        "first_name", "last_name", "yr", "pos", "number",
        "gp", "gs", "goals", "assists", "points",
        "shots", "sog", "gb", "to", "ct",
        "fo_won", "f_os_taken", "ncaa_id",
    ]
    output_cols = [c for c in output_cols if c in df.columns]
    df = df[output_cols]

    df = df.rename(columns=rename_map)

    return df


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else "2025"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    urls_file = f"url_csvs/ncaa_mens_lacrosse_teamurls_{season}.csv"
    output_file = f"data/ncaa_mens_lacrosse_playerstats_{season}.csv"

    print(f"Reading URLs from {urls_file}")
    urls_df = pd.read_csv(urls_file)
    # Use playerstatsurl (column 2) for player scraper
    stats_urls = urls_df.iloc[:, 1].tolist()
    if limit:
        stats_urls = stats_urls[:limit]
    print(f"Processing {len(stats_urls)} teams")

    all_players = []

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

        for i, url in enumerate(stats_urls):
            print(f"[{i+1}/{len(stats_urls)}] Processing {url}")
            try:
                result = process_team(page, url, season)
                if result is not None and not result.empty:
                    all_players.append(result)
                    team_name = result["Team"].iloc[0]
                    print(f"  Fetching {team_name} ({len(result)} players)")
                else:
                    print(f"  Skipped (no data)")
            except Exception as e:
                print(f"  Error: {e}")

            time.sleep(1)

        browser.close()

    if all_players:
        final = pd.concat(all_players, ignore_index=True)
        final = final.dropna(how="all")
        final.to_csv(output_file, index=False)
        print(f"\nWrote {len(final)} players to {output_file}")
    else:
        print("\nNo data collected!")


if __name__ == "__main__":
    main()
