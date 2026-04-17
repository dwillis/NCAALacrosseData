# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "ncaa-stats-py",
#     "pandas",
#     "playwright",
# ]
# ///

"""
Generate a teamurls CSV for a given sport and season.

Usage:
    python generate_team_urls.py <sport> <season>

    sport: "mens" or "womens"
    season: year (e.g. 2026)

Examples:
    python generate_team_urls.py mens 2026
    python generate_team_urls.py womens 2025
"""

import asyncio
import sys
import os
import re
import pandas as pd
from playwright.async_api import async_playwright


def ensure_helpers():
    """Create stub helpers for ncaa_stats_py if missing."""
    try:
        import ncaa_stats_py.helpers  # noqa: F401
    except ModuleNotFoundError:
        import ncaa_stats_py
        pkg_dir = os.path.dirname(ncaa_stats_py.__file__)
        helpers_dir = os.path.join(pkg_dir, "helpers")
        os.makedirs(helpers_dir, exist_ok=True)
        with open(os.path.join(helpers_dir, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(helpers_dir, "football.py"), "w") as f:
            f.write(
                "def _get_yardline(*a, **kw): pass\n"
                "def _football_pbp_helper(*a, **kw): pass\n"
            )
        with open(os.path.join(helpers_dir, "volleyball.py"), "w") as f:
            f.write("def _volleyball_pbp_helper(*a, **kw): pass\n")


def get_teams(sport, season):
    """Get D1 lacrosse teams from ncaa_stats_py."""
    ensure_helpers()
    from ncaa_stats_py.lacrosse import get_lacrosse_teams

    womens = sport == "womens"
    teams = get_lacrosse_teams(
        season=season, level="I", get_womens_lacrosse_data=womens
    )
    print(f"Found {len(teams)} teams")
    return teams


async def find_ctl_id(school_id):
    """Scrape game_sport_year_ctl_id from a team page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        # Use the teams/{team_id} page which contains game_sport_year_ctl_id
        # We need the ncaa_stats_py team_id, not school_id, for this URL
        # Instead, use a known working URL pattern with the school_id
        # and a recent ctl_id to find the current one
        await page.goto(
            f"https://stats.ncaa.org/teams/{school_id}",
            timeout=30000,
        )
        await page.wait_for_timeout(5000)

        html = await page.content()
        ctl_ids = set(re.findall(r"game_sport_year_ctl_id=(\d+)", html))
        await browser.close()

    if not ctl_ids:
        return None

    # Return the highest (most recent) ctl_id
    return max(ctl_ids, key=int)


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_team_urls.py <sport> <season>")
        print("  sport: mens or womens")
        print("  season: year (e.g. 2026)")
        sys.exit(1)

    sport = sys.argv[1].lower()
    season = int(sys.argv[2])

    if sport not in ("mens", "womens"):
        print("sport must be 'mens' or 'womens'")
        sys.exit(1)

    sport_prefix = "mens" if sport == "mens" else "womens"
    output_file = f"url_csvs/ncaa_{sport_prefix}_lacrosse_teamurls_{season}.csv"

    print(f"Fetching {sport} lacrosse teams for {season}...")
    teams = get_teams(sport, season)

    if teams.empty:
        print("No teams found!")
        sys.exit(1)

    # Use first team's ncaa_stats_py team_id to find the ctl_id
    first_team_id = int(teams.iloc[0]["team_id"])
    print(f"Finding game_sport_year_ctl_id from team page {first_team_id}...")
    ctl_id = asyncio.run(find_ctl_id(first_team_id))

    if not ctl_id:
        print("Could not find game_sport_year_ctl_id!")
        sys.exit(1)

    print(f"Using game_sport_year_ctl_id={ctl_id}")

    # Build the CSV
    rows = []
    for _, row in teams.iterrows():
        school_name = row["school_name"]
        school_id = int(row["school_id"])
        playerstatsurl = (
            f"https://stats.ncaa.org/team/{school_id}/stats/{ctl_id}"
        )
        matchstatsurl = (
            f"https://stats.ncaa.org/player/game_by_game?"
            f"game_sport_year_ctl_id={ctl_id}"
            f"&org_id={school_id}&stats_player_seq=-100"
        )
        rows.append({
            "school": school_name,
            "playerstatsurl": playerstatsurl,
            "matchstatsurl": matchstatsurl,
        })

    df = pd.DataFrame(rows).sort_values("school").reset_index(drop=True)
    df.to_csv(output_file, index=False)
    print(f"Wrote {len(df)} teams to {output_file}")


if __name__ == "__main__":
    main()
