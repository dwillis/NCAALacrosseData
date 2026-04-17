# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pandas",
#     "playwright",
# ]
# ///
"""Women's NCAA lacrosse player stats scraper.

Reads URLs from url_csvs/ncaa_womens_lacrosse_teamurls_{season}.csv and
writes data/ncaa_womens_lacrosse_playerstats_{season}.csv. Navigates the
matchstatsurl, follows the 'Team Statistics' link, and parses #stat_grid.

Women's NCAA player cells often render as "Last, First". When the cell
has a data-order attribute we prefer that for splitting; otherwise we
fall back to whatever comma / whitespace split is available.

Usage:
    python NCAAWomensLacrossePlayerScraper.py [season] [limit]
"""
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT_URL = "https://stats.ncaa.org"


def clean_value(val: str | None) -> str:
    if val is None:
        return ""
    val = val.strip()
    if val.endswith("/"):
        val = val[:-1].strip()
    return val


def to_numeric(val: object) -> float:
    if val is None:
        return float("nan")
    s = str(val).strip().replace(",", "").replace("-", "")
    if s == "":
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def minutes_to_decimal(val: object) -> float | None:
    s = str(val).strip().replace(",", "")
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except (ValueError, IndexError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def split_name(display: str, data_order: str | None) -> tuple[str, str, str]:
    """Return (full_name, first_name, last_name).

    Preferred source is data-order (Last, First). If that's missing, try
    commas in the display value, then fall back to whitespace splitting.
    """
    source = data_order if data_order and "," in data_order else display
    if "," in source:
        last, first = source.split(",", 1)
        last, first = last.strip(), first.strip()
        full = f"{first} {last}" if data_order else display.strip()
        return full, first, last
    parts = display.split()
    first = parts[0] if parts else ""
    last = parts[-1] if parts else ""
    return display.strip(), first, last


def process_team(page, match_url: str, season: str) -> pd.DataFrame | None:
    parsed = urlparse(match_url)
    org_id = parse_qs(parsed.query).get("org_id", [None])[0]

    try:
        page.goto(match_url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading match page: {e}")
        return None

    team_stats_link = page.query_selector('a:text("Team Statistics")')
    if not team_stats_link:
        print("  No 'Team Statistics' link found")
        return None
    href = team_stats_link.get_attribute("href")
    if not href:
        print("  Team Statistics link has no href")
        return None

    try:
        page.goto(ROOT_URL + href, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading team stats page: {e}")
        return None

    team_name = ""
    logo = page.query_selector(
        "xpath=/html/body/div[2]/div/div/div/div/div/div[1]/img"
    )
    if logo:
        team_name = (logo.get_attribute("alt") or "").strip()
    if not team_name:
        card = page.query_selector(".card-header")
        if card:
            m = re.match(r"(.*?)\s*\(\d+-\d+-?\d*\)", card.inner_text().strip())
            if m:
                team_name = m.group(1).strip()
    if not team_name:
        team_name = "Unknown"

    team_id = org_id
    ranking_link = page.query_selector('a[href*="ranking_summary"]')
    if ranking_link:
        rhref = ranking_link.get_attribute("href") or ""
        m = re.search(r"org_id=(\d+)", rhref)
        if m:
            team_id = m.group(1)

    grid = page.query_selector("#stat_grid")
    if not grid:
        print(f"  No stat_grid table found for {team_name}")
        return None

    header_row = grid.query_selector("thead tr") or grid.query_selector("tr")
    if not header_row:
        return None
    header_cells = header_row.query_selector_all("th")
    headers = [
        c.inner_text().strip().lower().replace(" ", "_").replace("%", "_pct")
        for c in header_cells
    ]
    col_map = {"#": "jersey", "player": "roster_name"}
    headers = [col_map.get(h, h) for h in headers]

    body_rows = grid.query_selector_all("tbody tr")
    players: list[dict] = []
    for row in body_rows:
        cells = row.query_selector_all("td")
        if len(cells) != len(headers):
            continue
        values = [clean_value(c.inner_text()) for c in cells]
        record = dict(zip(headers, values))

        display = record.get("roster_name", "")
        if display in ("Totals", "Opponent Totals", "TEAM", ""):
            continue

        ncaa_id = ""
        data_order = None
        if "roster_name" in headers:
            cell = cells[headers.index("roster_name")]
            data_order = cell.get_attribute("data-order")
            link = cell.query_selector("a")
            if link:
                lhref = link.get_attribute("href") or ""
                m = re.search(r"(\d+)", lhref)
                if m:
                    ncaa_id = m.group(1)

        full, first, last = split_name(display, data_order)
        record["full_name"] = full
        record["first_name"] = first
        record["last_name"] = last
        record["team"] = team_name
        record["team_id"] = team_id
        record["season"] = int(season)
        record["ncaa_id"] = ncaa_id

        players.append(record)

    if not players:
        print(f"  No players found for {team_name}")
        return None

    df = pd.DataFrame(players)

    for col in ("minutes", "g_min", "goalie_min_plyd"):
        if col in df.columns:
            df[col] = df[col].apply(minutes_to_decimal)

    non_numeric = {
        "season", "team", "team_id", "full_name", "roster_name",
        "first_name", "last_name", "yr", "pos", "ncaa_id", "ht",
        "goal_app", "ggs",
    } | {c for c in ("minutes", "g_min", "goalie_min_plyd") if c in df.columns}
    for col in df.columns:
        if col not in non_numeric:
            df[col] = df[col].apply(to_numeric)

    preferred = [
        "season", "team", "team_id", "jersey", "full_name", "roster_name",
        "first_name", "last_name", "yr", "pos",
        "gp", "gs", "goals", "assists", "points", "shots", "sog",
        "gb", "to", "ct", "fo_won", "f_os_taken",
        "g_min", "goals_allowed", "saves",
        "ncaa_id",
    ]
    ordered = [c for c in preferred if c in df.columns]
    extras = [c for c in df.columns if c not in ordered]
    return df[ordered + extras]


def main() -> None:
    season = sys.argv[1] if len(sys.argv) > 1 else "2025"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    urls_file = f"url_csvs/ncaa_womens_lacrosse_teamurls_{season}.csv"
    output_file = f"data/ncaa_womens_lacrosse_playerstats_{season}.csv"

    print(f"Reading URLs from {urls_file}")
    urls_df = pd.read_csv(urls_file)
    match_urls = urls_df.iloc[:, 2].tolist()
    if limit:
        match_urls = match_urls[:limit]
    print(f"Processing {len(match_urls)} teams")

    all_players: list[pd.DataFrame] = []
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
                    print(f"  Fetching {result['team'].iloc[0]} ({len(result)} players)")
                else:
                    print("  Skipped (no data)")
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
