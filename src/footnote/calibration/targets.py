"""Published figures the generator is calibrated against, with their sources.

Season 2025/26 (380 matches) unless stated. Results, shots on target, fouls,
corners and yellow cards are counted from football-data.co.uk's match file.
Figures sourced to premierleague.com's club stats (Opta data) are the 20 clubs'
season totals, summed, read from the data behind the site's club stats pages;
those sums agree with Opta Analyst's published season totals where both exist
(goals, shots, successful passes, red cards, throw-ins, goal kicks). Quotes
were checked against the source pages on 2026-10-19.
"""

from __future__ import annotations

from dataclasses import dataclass

# The site's club stats pages choose the statistic and season on the page itself, so this links
# their starting point rather than a page per figure.
PL_CLUB_STATS = "https://www.premierleague.com/en/stats/top/clubs"
OPTA_TOTALS = "https://theanalyst.com/articles/premier-league-team-of-the-season-2025-26-opta"
OPTA_BIP = "https://theanalyst.com/articles/premier-league-rules-throw-ins-goal-kicks-ball-in-play"
OPTA_BIP_2425 = "https://theanalyst.com/articles/premier-league-ball-in-play-are-we-seeing-less-football-2025-26"
OPTA_SET_PIECES = "https://theanalyst.com/articles/fpl-set-piece-stats-projections-tips-premier-league-2026-27"
OPTA_RUNNING = "https://theanalyst.com/articles/premier-league-running-more-stats-myths"
BBC_VAR = "https://www.modernghana.com/sports/1497747/every-var-error-in-2025-26-premier-league-how.html"
PL_SPEED = "https://www.premierleague.com/en/news/4673057/who-ran-fastest-and-furthest-in-202526-premier-league"
PL_RUNNING_2425 = "https://www.premierleague.com/en/news/4272290"
ALLEN_2025 = "https://doi.org/10.1136/bjsports-2025-110430"
FOOTBALL_DATA = "https://www.football-data.co.uk/mmz4281/2526/E0.csv"
ELEVEN = "https://www.11v11.com/competitions/premier-league/2026/"


@dataclass(frozen=True)
class Target:
    key: str  # metric computed by report.py
    label: str
    value: float
    unit: str
    source: str
    url: str
    derivation: str  # how the published value was obtained


TARGETS: tuple[Target, ...] = (
    Target(
        "goals",
        "Goals per match",
        1045 / 380,
        "goals",
        "Opta Analyst",
        OPTA_TOTALS,
        f"1,045 goals in 380 matches (Opta Analyst); [11v11]({ELEVEN}) states 2.75 per game",
    ),
    Target(
        "home_win",
        "Home wins",
        162 / 380,
        "share",
        "football-data.co.uk results",
        FOOTBALL_DATA,
        "counted from full-time results: 162 home wins of 380",
    ),
    Target(
        "draw",
        "Draws",
        104 / 380,
        "share",
        "football-data.co.uk results",
        FOOTBALL_DATA,
        "counted from full-time results: 104 draws of 380",
    ),
    Target(
        "away_win",
        "Away wins",
        114 / 380,
        "share",
        "football-data.co.uk results",
        FOOTBALL_DATA,
        "counted from full-time results: 114 away wins of 380",
    ),
    Target(
        "btts",
        "Both teams scored",
        213 / 380,
        "share",
        "football-data.co.uk results",
        FOOTBALL_DATA,
        "counted from full-time scores: 213 of 380",
    ),
    Target(
        "nil_nil",
        "Goalless matches",
        27 / 380,
        "share",
        "football-data.co.uk results",
        FOOTBALL_DATA,
        "counted from full-time scores: 27 of 380",
    ),
    Target(
        "shots",
        "Shots per match",
        9503 / 380,
        "shots",
        "Opta Analyst",
        OPTA_TOTALS,
        "9,503 shots including blocked shots",
    ),
    Target(
        "shots_on_target",
        "Shots on target per match",
        3182 / 380,
        "shots",
        "football-data.co.uk match statistics",
        FOOTBALL_DATA,
        "summed shots on target (HST, AST): 3,182",
    ),
    Target(
        "shots_blocked",
        "Blocked shots per match",
        (9503 - 6705) / 380,
        "shots",
        "Opta Analyst; premierleague.com club stats",
        PL_CLUB_STATS,
        "9,503 shots (Opta Analyst) less the 6,705 that weren't blocked (club totals summed)",
    ),
    Target(
        "conversion",
        "Goals per shot",
        1045 / 9503,
        "share",
        "Opta Analyst",
        OPTA_TOTALS,
        "1,045 goals / 9,503 shots, own goals included",
    ),
    Target(
        "passes_per_team",
        "Passes per team per match",
        332121 / 760,
        "passes",
        "premierleague.com club stats",
        PL_CLUB_STATS,
        "club totals summed: 332,121 passes over 760 team-matches",
    ),
    Target(
        "pass_completion",
        "Pass completion",
        273956 / 332121,
        "share",
        "Opta Analyst; premierleague.com club stats",
        OPTA_TOTALS,
        "273,956 successful passes (Opta Analyst) / 332,121 passes (club totals summed)",
    ),
    Target(
        "possession_low",
        "Lowest club possession (season)",
        0.425,
        "share",
        "premierleague.com club stats",
        PL_CLUB_STATS,
        "lowest club's season possession: West Ham, 42.5%",
    ),
    Target(
        "possession_high",
        "Highest club possession (season)",
        0.604,
        "share",
        "premierleague.com club stats",
        PL_CLUB_STATS,
        "highest club's season possession: Manchester City, 60.4%",
    ),
    Target(
        "corners",
        "Corners per match",
        3799 / 380,
        "corners",
        "football-data.co.uk match statistics",
        FOOTBALL_DATA,
        "summed corners (HC, AC): 3,799",
    ),
    Target("throw_ins", "Throw-ins per match", 13615 / 380, "throw-ins", "Opta Analyst", OPTA_BIP, "13,615 throw-ins"),
    Target(
        "goal_kicks", "Goal kicks per match", 5901 / 380, "goal kicks", "Opta Analyst", OPTA_BIP, "5,901 goal kicks"
    ),
    Target(
        "fouls",
        "Fouls per match",
        8224 / 380,
        "fouls",
        "football-data.co.uk match statistics",
        FOOTBALL_DATA,
        "summed fouls committed (HF, AF): 8,224",
    ),
    Target(
        "offsides",
        "Offsides per match",
        1175 / 380,
        "offsides",
        "premierleague.com club stats",
        PL_CLUB_STATS,
        "club totals summed: 1,175 offsides",
    ),
    Target(
        "yellow_cards",
        "Yellow cards per match",
        1424 / 380,
        "cards",
        "football-data.co.uk match statistics",
        FOOTBALL_DATA,
        "summed yellow cards (HY, AY): 1,424; a first yellow that a second turns into a red isn't counted",
    ),
    Target("red_cards", "Red cards per match", 44 / 380, "cards", "Opta Analyst", OPTA_TOTALS, "44 red cards"),
    Target(
        "penalties",
        "Penalties per match",
        92 / 380,
        "penalties",
        "premierleague.com club stats",
        PL_CLUB_STATS,
        "club totals summed: 92 penalties won",
    ),
    Target(
        "penalty_conversion",
        "Penalty conversion",
        77 / 92,
        "share",
        "premierleague.com club stats",
        PL_CLUB_STATS,
        "club totals summed: 77 penalty goals from 92 penalties",
    ),
    Target(
        "own_goals",
        "Own goals per match",
        40 / 380,
        "goals",
        "premierleague.com club stats",
        PL_CLUB_STATS,
        "club totals summed: 40 own goals conceded",
    ),
    Target(
        "headed_share",
        "Headed share of goals",
        184 / 1045,
        "share",
        "premierleague.com club stats",
        PL_CLUB_STATS,
        "club totals summed: 184 headed goals of 1,045",
    ),
    Target(
        "set_piece_share",
        "Non-penalty set-piece share of goals",
        0.274,
        "share",
        "Opta Analyst",
        OPTA_SET_PIECES,
        '"27.4% of all goals came from non-penalty set-pieces"',
    ),
    Target(
        "var_overturns",
        "VAR overturns per match",
        105 / 380,
        "overturns",
        "BBC Sport (republished)",
        BBC_VAR,
        "105 overturns; read from ModernGhana's republication of the BBC Sport article",
    ),
    Target(
        "ball_in_play_min",
        "Ball in play",
        55 + 23 / 60,
        "minutes",
        "Opta Analyst",
        OPTA_BIP,
        '"just 55 mins, 23 seconds last season"',
    ),
    Target(
        "match_minutes",
        "Match length including added time (2024/25)",
        99 + 44 / 60,
        "minutes",
        "Opta Analyst",
        OPTA_BIP_2425,
        '"99 mins, 44 secs" in 2024/25; no full-season 2025/26 figure found',
    ),
    Target(
        "team_distance_km",
        "Distance per team per match",
        (4363 + 4332) / 2 / 38,
        "km",
        "Opta Analyst",
        OPTA_RUNNING,
        "top-10 and bottom-10 season averages (4,363 and 4,332 km) over 38 matches",
    ),
    Target(
        "top_speed_max",
        "Fastest speed recorded in the season",
        37.30,
        "km/h",
        "Premier League",
        PL_SPEED,
        '"top speed of 37.30km/h"',
    ),
    Target(
        "club_fastest_low",
        "Slowest club's fastest player",
        34.68,
        "km/h",
        "Premier League",
        PL_SPEED,
        "each club's fastest player: lowest 34.68 km/h",
    ),
)

# Published figures shown for context but not used as targets: a different season, or read
# from a figure rather than text.
CONTEXT = (
    (
        "Distance per team per match, 2024/25",
        "113.9 km (SD 4.1)",
        "Allen et al., Br J Sports Med 2025 (Second Spectrum tracking); value read from Figure 2",
        ALLEN_2025,
    ),
    (
        "Sprint distance (>7 m/s) per team per match, 2024/25",
        "2.3 km (SD 0.5)",
        "Allen et al., Br J Sports Med 2025; value read from Figure 2",
        ALLEN_2025,
    ),
    (
        "Distance per 90 minutes, regular players, 2024/25 to Matchweek 29",
        "8.5 to 12.3 km",
        "premierleague.com (Opta Analyst)",
        PL_RUNNING_2425,
    ),
)
