"""Build ncaa_{mens,womens}_lacrosse_teamurls_{year}.csv files.

Uses the github install of ncaa_stats_py (Sports-Roster-Data/ncaa_stats_py)
to retrieve D1 lacrosse teams, derives each season's
game_sport_year_ctl_id by fetching one team's page, and writes the
same three-column format already used for the existing CSVs:
    school, playerstatsurl, matchstatsurl

Usage:
    python build_lacrosse_urls.py                 # build both M/W for default seasons
    python build_lacrosse_urls.py mens 2024 2025  # build men's for listed seasons
    python build_lacrosse_urls.py womens 2024     # build women's for one season
"""
import importlib.util
import re
import sys
import types
from pathlib import Path

import pandas as pd

# The installed package may have a broken __init__.py import path; load the
# lacrosse + utls modules directly without executing the package __init__.
_PKG_DIR = Path(__file__).resolve().parent / ".venv" / "lib"
_candidates = list(_PKG_DIR.glob("python*/site-packages/ncaa_stats_py"))
if _candidates:
    _PKG_DIR = _candidates[0]
    _pkg = types.ModuleType("ncaa_stats_py")
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules["ncaa_stats_py"] = _pkg
    for _name in ("utls", "lacrosse"):
        _spec = importlib.util.spec_from_file_location(
            f"ncaa_stats_py.{_name}", str(_PKG_DIR / f"{_name}.py")
        )
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[f"ncaa_stats_py.{_name}"] = _mod
        _spec.loader.exec_module(_mod)

from ncaa_stats_py.lacrosse import get_lacrosse_teams  # noqa: E402
from ncaa_stats_py.utls import _safe_get_webpage  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "url_csvs"
DEFAULT_MENS_SEASONS = range(2020, 2026)
DEFAULT_WOMENS_SEASONS = range(2022, 2026)


def ctl_for_team(team_id: int) -> int:
    """Scrape the season-specific game_sport_year_ctl_id from a team page."""
    resp = _safe_get_webpage(f"https://stats.ncaa.org/teams/{team_id}")
    m = re.search(r"game_sport_year_ctl_id[=:]?\s*(\d+)", resp.text)
    if not m:
        raise RuntimeError(f"No ctl found for team_id={team_id}")
    return int(m.group(1))


def build_season(season: int, womens: bool) -> None:
    gender = "womens" if womens else "mens"
    teams = get_lacrosse_teams(season, 1, get_womens_lacrosse_data=womens)
    teams = teams.dropna(subset=["school_id"]).copy()
    teams["school_id"] = teams["school_id"].astype(int)
    teams = teams.drop_duplicates(subset=["school_id"]).sort_values("school_name")

    ctl = ctl_for_team(int(teams.iloc[0]["team_id"]))
    print(f"{gender} {season}: {len(teams)} teams, ctl={ctl}")

    rows = []
    for _, row in teams.iterrows():
        org = int(row["school_id"])
        rows.append(
            {
                "school": row["school_name"],
                "playerstatsurl": f"https://stats.ncaa.org/team/{org}/stats/{ctl}",
                "matchstatsurl": (
                    "https://stats.ncaa.org/player/game_by_game?"
                    f"org_id={org}&game_sport_year_ctl_id={ctl}"
                    "&stats_player_seq=-100"
                ),
            }
        )
    out = OUT_DIR / f"ncaa_{gender}_lacrosse_teamurls_{season}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  wrote {out}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        targets = [("mens", s) for s in DEFAULT_MENS_SEASONS] + [
            ("womens", s) for s in DEFAULT_WOMENS_SEASONS
        ]
    else:
        gender = args[0].lower()
        if gender not in ("mens", "womens"):
            raise SystemExit("first arg must be 'mens' or 'womens'")
        seasons = [int(s) for s in args[1:]] or (
            list(DEFAULT_WOMENS_SEASONS) if gender == "womens" else list(DEFAULT_MENS_SEASONS)
        )
        targets = [(gender, s) for s in seasons]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for gender, season in targets:
        try:
            build_season(season, womens=(gender == "womens"))
        except Exception as e:
            print(f"{gender} {season}: SKIPPED ({e})")


if __name__ == "__main__":
    main()
