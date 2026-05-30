# NCAA Lacrosse Data

Match and player statistics for NCAA Division I men's and women's lacrosse, scraped from [stats.ncaa.org](https://stats.ncaa.org). Includes four Python scrapers and pre-collected CSV files going back to 2018 (women's) and 2020 (men's).

## Repository Structure

```
├── NCAAMensLacrosseMatchScraper.py    # Scrapes men's per-game match stats
├── NCAAMensLacrossePlayerScraper.py   # Scrapes men's per-player season stats
├── NCAAWomensLacrosseMatchScraper.py  # Scrapes women's per-game match stats
├── NCAAWomensLacrossePlayerScraper.py # Scrapes women's per-player season stats
├── generate_team_urls.py              # Builds url_csvs/ for a given sport/season
├── build_lacrosse_urls.py             # Bulk-builds url_csvs/ using ncaa_stats_py
├── data/                              # Collected CSVs (match stats + player stats)
├── url_csvs/                          # Per-season team URL lists used by scrapers
└── archive/                           # Legacy Flask app and SQLite DB
```

## Data Coverage

| Gender  | Seasons   | Match stats | Player stats  |
|---------|-----------|-------------|---------------|
| Men's   | 2020–2026 | ✓           | ✓ (2020–2025) |
| Women's | 2018–2026 | ✓           | ✓             |

Files follow the naming convention:
- `data/ncaa_{mens,womens}_lacrosse_matchstats_{season}.csv`
- `data/ncaa_{mens,womens}_lacrosse_playerstats_{season}.csv`

## Setup

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
playwright install chromium
```

## Running the Scrapers

Each scraper accepts an optional season year (default: **2026**) and an optional team limit for testing:

```bash
# Scrape the current season
python NCAAMensLacrosseMatchScraper.py
python NCAAMensLacrossePlayerScraper.py
python NCAAWomensLacrosseMatchScraper.py
python NCAAWomensLacrossePlayerScraper.py

# Scrape a specific season
python NCAAMensLacrosseMatchScraper.py 2025

# Limit to the first N teams (useful for testing)
python NCAAMensLacrosseMatchScraper.py 2026 5

# Show help
python NCAAMensLacrosseMatchScraper.py --help
```

The scrapers read team URLs from `url_csvs/ncaa_{mens,womens}_lacrosse_teamurls_{season}.csv` and write results to `data/`.

## Updating Team URLs

Team URL CSVs must exist before running the scrapers. To generate them for a new season:

```bash
python generate_team_urls.py mens 2026
python generate_team_urls.py womens 2026
```

This uses [ncaa_stats_py](https://github.com/Sports-Roster-Data/ncaa_stats_py) and Playwright to derive the correct `game_sport_year_ctl_id` for each team and writes the three-column CSV (`school`, `playerstatsurl`, `matchstatsurl`) to `url_csvs/`.

## URL Format

The scrapers rely on two predictable NCAA stats URL patterns:

- **Player stats:** `https://stats.ncaa.org/team/{org_id}/stats/{ctl_id}`
- **Match stats:** `https://stats.ncaa.org/player/game_by_game?org_id={org_id}&game_sport_year_ctl_id={ctl_id}&stats_player_seq=-100`

Where `org_id` is the NCAA team ID and `ctl_id` is the sport-and-season code (unique per sport per year).

## Contributing

Pull requests welcome. See the Issues tab for ideas.
