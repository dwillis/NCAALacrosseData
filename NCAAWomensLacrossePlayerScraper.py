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


def minutes_to_decimal(val):
    """Convert MM:SS or MMMM:SS format to decimal minutes."""
    val = str(val).strip().replace(",", "")
    if ":" in val:
        parts = val.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except (ValueError, IndexError):
            return None
    try:
        return float(val)
    except ValueError:
        return None


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


def process_team(page, match_url, season):
    """Navigate to match page, find team stats link, scrape player stats."""

    # Extract org_id from match URL
    parsed = urlparse(match_url)
    params = parse_qs(parsed.query)
    org_id = params.get("org_id", [None])[0]

    # Load the match stats page first (this URL format works)
    try:
        page.goto(match_url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading match page: {e}")
        return None

    # Find the "Team Statistics" link to get the working team stats URL
    team_stats_link = page.query_selector('a:text("Team Statistics")')
    if not team_stats_link:
        print(f"  No 'Team Statistics' link found")
        return None

    team_stats_href = team_stats_link.get_attribute("href")
    if not team_stats_href:
        print(f"  Team Statistics link has no href")
        return None

    team_stats_url = ROOT_URL + team_stats_href
    try:
        page.goto(team_stats_url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading team stats page: {e}")
        return None

    # Extract team name from card-header
    team_name = "Unknown"
    card = page.query_selector(".card-header")
    if card:
        card_text = card.inner_text().strip()
        match = re.match(r"(.*?)\s*\(\d+-\d+-?\d*\)", card_text)
        if match:
            team_name = match.group(1).strip()

    # Extract team_id from ranking_summary link
    team_id = org_id  # fallback to org_id from URL
    ranking_link = page.query_selector('a[href*="ranking_summary"]')
    if ranking_link:
        href = ranking_link.get_attribute("href") or ""
        id_match = re.search(r"org_id=(\d+)", href)
        if id_match:
            team_id = id_match.group(1)

    # Parse stat_grid table
    stat_grid = page.query_selector("#stat_grid")
    if not stat_grid:
        print(f"  No stat_grid table found for {team_name}")
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
        "shatt": "sh_att",
        "sog": "so_g",
        "f/os_won": "f_os_won",
        "f/os_taken": "f_os_taken",
        "freepos_shots": "freepos_shots",
        "freepos_goals": "freepos_goals",
    }
    headers = [col_map.get(h, h) for h in headers]

    # Get body rows
    body_rows = stat_grid.query_selector_all("tbody tr")
    players = []

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

        # Get data-order attribute for name parsing
        name_cell = cells[headers.index("roster_name")] if "roster_name" in headers else None
        data_order = name_cell.get_attribute("data-order") if name_cell else None

        record["full_name"] = name

        if data_order and "," in data_order:
            parts = data_order.split(",", 1)
            record["last_name"] = parts[0].strip()
            record["first_name"] = parts[1].strip()
        else:
            # Fallback: first word / last word
            name_parts = name.split()
            record["first_name"] = name_parts[0] if name_parts else ""
            record["last_name"] = name_parts[-1] if name_parts else ""

        record["team"] = team_name
        record["team_id"] = team_id
        record["season"] = int(season)

        players.append(record)

    if not players:
        print(f"  No players found for {team_name}")
        return None

    df = pd.DataFrame(players)

    # Convert minutes
    if "minutes" in df.columns:
        df["minutes"] = df["minutes"].apply(minutes_to_decimal)
    if "g_min" in df.columns:
        df["g_min"] = df["g_min"].apply(minutes_to_decimal)

    # Convert numeric columns (lacrosse-specific)
    numeric_cols = [
        "number", "gp", "gs", "goals", "assists", "points",
        "shots", "sog", "ground_balls", "turnovers", "ct",
        "f_os_won", "f_os_taken", "goals_allowed", "saves",
        "freepos_shots", "freepos_goals", "rc", "yc",
        "draw_controls", "clears", "clr_att", "fouls",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(to_numeric)

    # Reorder columns to match expected format
    output_cols = [
        "season", "team", "team_id", "full_name", "roster_name",
        "first_name", "last_name", "yr", "pos", "number",
        "gp", "gs", "goals", "assists", "points",
        "shots", "sog", "ground_balls", "turnovers", "ct",
        "f_os_won", "f_os_taken", "g_min", "goals_allowed", "saves",
        "freepos_shots", "freepos_goals", "rc", "yc",
        "draw_controls", "clears", "clr_att", "fouls",
    ]
    # Only include columns that exist
    output_cols = [c for c in output_cols if c in df.columns]
    df = df[output_cols]

    return df


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else "2022"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    urls_file = f"url_csvs/ncaa_womens_lacrosse_teamurls_{season}.csv"
    output_file = f"data/ncaa_womens_lacrosse_playerstats_{season}.csv"

    print(f"Reading URLs from {urls_file}")
    urls_df = pd.read_csv(urls_file)
    # Use matchstatsurl (column 3) since playerstatsurl format may not work
    match_urls = urls_df.iloc[:, 2].tolist()
    if limit:
        match_urls = match_urls[:limit]
    print(f"Processing {len(match_urls)} teams")

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

        for i, url in enumerate(match_urls):
            print(f"[{i+1}/{len(match_urls)}] Processing {url}")
            try:
                result = process_team(page, url, season)
                if result is not None and not result.empty:
                    all_players.append(result)
                    team_name = result["team"].iloc[0]
                    print(f"  Fetching {team_name} ({len(result)} players)")
                else:
                    print(f"  Skipped (no data)")
            except Exception as e:
                print(f"  Error: {e}")

            time.sleep(1)

        browser.close()

    if all_players:
        final = pd.concat(all_players, ignore_index=True)
        final = final.dropna(how="all").dropna(subset=["full_name"])
        final.to_csv(output_file, index=False)
        print(f"\nWrote {len(final)} players to {output_file}")
    else:
        print("\nNo data collected!")


if __name__ == "__main__":
    main()
