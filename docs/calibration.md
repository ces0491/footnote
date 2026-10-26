# Calibration

How closely generated seasons match a real one. The generator was tuned against the published
figures below. This report measures two full generated seasons, under league seeds 2026 and 2027,
which separates the gaps that hold under both seeds from those that come and go with one
season's draws.

Generated on 2026-10-26: all 380 fixtures of the 2026/27 season under each seed, with 10 Hz
tracking, in 5 minutes. Generator fingerprint `5e1cde3bdb459aba`. Regenerate with
`python -m footnote.calibration`.

Published figures are for the 2025/26 Premier League season unless the row says otherwise.
"±" is the 95% interval of the generated mean from the simulation's own sampling noise;
the published figure is a single real season and is noisy too.

| Metric | Generated, seed 2026 | Generated, seed 2027 | Published | Difference | Source | How the published figure was obtained |
| --- | --- | --- | --- | --- | --- | --- |
| Goals per match | 2.73 ± 0.19 | 2.82 ± 0.18 | 2.75 | -1% / +3% | [Opta Analyst](https://theanalyst.com/articles/premier-league-team-of-the-season-2025-26-opta) | 1,045 goals in 380 matches (Opta Analyst); [11v11](https://www.11v11.com/competitions/premier-league/2026/) states 2.75 per game |
| Home wins | 47.1% ± 5.0 | 46.8% ± 5.0 | 42.6% | +10% / +10% | [football-data.co.uk results](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | counted from full-time results: 162 home wins of 380 |
| Draws | 21.3% ± 4.1 | 20.0% ± 4.0 | 27.4% | -22% / -27% | [football-data.co.uk results](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | counted from full-time results: 104 draws of 380 |
| Away wins | 31.6% ± 4.7 | 33.2% ± 4.7 | 30.0% | +5% / +11% | [football-data.co.uk results](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | counted from full-time results: 114 away wins of 380 |
| Both teams scored | 43.2% ± 5.0 | 45.5% ± 5.0 | 56.1% | -23% / -19% | [football-data.co.uk results](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | counted from full-time scores: 213 of 380 |
| Goalless matches | 9.5% ± 2.9 | 7.1% ± 2.6 | 7.1% | +33% / +0% | [football-data.co.uk results](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | counted from full-time scores: 27 of 380 |
| Shots per match | 25.0 ± 0.66 | 25.5 ± 0.65 | 25.0 | +0% / +2% | [Opta Analyst](https://theanalyst.com/articles/premier-league-team-of-the-season-2025-26-opta) | 9,503 shots including blocked shots |
| Shots on target per match | 7.16 ± 0.31 | 7.31 ± 0.33 | 8.37 | -15% / -13% | [football-data.co.uk match statistics](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | summed shots on target (HST, AST): 3,182 |
| Blocked shots per match | 5.93 ± 0.27 | 5.92 ± 0.27 | 7.36 | -20% / -20% | [Opta Analyst; premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | 9,503 shots (Opta Analyst) less the 6,705 that weren't blocked (club totals summed) |
| Goals per shot | 10.9% ± 0.6 | 11.1% ± 0.6 | 11.0% | -1% / +1% | [Opta Analyst](https://theanalyst.com/articles/premier-league-team-of-the-season-2025-26-opta) | 1,045 goals / 9,503 shots, own goals included |
| Passes per team per match | 443.4 ± 10.3 | 448.1 ± 10.8 | 437.0 | +1% / +3% | [premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | club totals summed: 332,121 passes over 760 team-matches |
| Pass completion | 80.6% ± 0.1 | 80.6% ± 0.1 | 82.5% | -2% / -2% | [Opta Analyst; premierleague.com club stats](https://theanalyst.com/articles/premier-league-team-of-the-season-2025-26-opta) | 273,956 successful passes (Opta Analyst) / 332,121 passes (club totals summed) |
| Lowest club possession (season) | 31.7% | 29.9% | 42.5% | -25% / -30% | [premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | lowest club's season possession: West Ham, 42.5% |
| Highest club possession (season) | 65.3% | 63.8% | 60.4% | +8% / +6% | [premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | highest club's season possession: Manchester City, 60.4% |
| Corners per match | 10.5 ± 0.37 | 10.5 ± 0.35 | 10.00 | +5% / +5% | [football-data.co.uk match statistics](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | summed corners (HC, AC): 3,799 |
| Throw-ins per match | 35.0 ± 0.80 | 34.9 ± 0.79 | 35.8 | -2% / -3% | [Opta Analyst](https://theanalyst.com/articles/premier-league-rules-throw-ins-goal-kicks-ball-in-play) | 13,615 throw-ins |
| Goal kicks per match | 14.3 ± 0.41 | 14.5 ± 0.40 | 15.5 | -8% / -7% | [Opta Analyst](https://theanalyst.com/articles/premier-league-rules-throw-ins-goal-kicks-ball-in-play) | 5,901 goal kicks |
| Fouls per match | 21.9 ± 0.65 | 20.9 ± 0.57 | 21.6 | +1% / -3% | [football-data.co.uk match statistics](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | summed fouls committed (HF, AF): 8,224 |
| Offsides per match | 3.27 ± 0.23 | 3.49 ± 0.26 | 3.09 | +6% / +13% | [premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | club totals summed: 1,175 offsides |
| Yellow cards per match | 4.10 ± 0.20 | 3.98 ± 0.19 | 3.75 | +9% / +6% | [football-data.co.uk match statistics](https://www.football-data.co.uk/mmz4281/2526/E0.csv) | summed yellow cards (HY, AY): 1,424; a first yellow that a second turns into a red isn't counted |
| Red cards per match | 0.17 ± 0.04 | 0.14 ± 0.04 | 0.12 | +45% / +18% | [Opta Analyst](https://theanalyst.com/articles/premier-league-team-of-the-season-2025-26-opta) | 44 red cards |
| Penalties per match | 0.27 ± 0.05 | 0.30 ± 0.06 | 0.24 | +11% / +23% | [premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | club totals summed: 92 penalties won |
| Penalty conversion | 89.2% ± 6.0 | 77.0% ± 7.8 | 83.7% | +7% / -8% | [premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | club totals summed: 77 penalty goals from 92 penalties |
| Own goals per match | 0.13 ± 0.04 | 0.10 ± 0.03 | 0.11 | +25% / -7% | [premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | club totals summed: 40 own goals conceded |
| Headed share of goals | 16.9% ± 2.3 | 13.2% ± 2.0 | 17.6% | -4% / -25% | [premierleague.com club stats](https://www.premierleague.com/en/stats/top/clubs) | club totals summed: 184 headed goals of 1,045 |
| Non-penalty set-piece share of goals | 27.6% ± 2.7 | 28.8% ± 2.7 | 27.4% | +1% / +5% | [Opta Analyst](https://theanalyst.com/articles/fpl-set-piece-stats-projections-tips-premier-league-2026-27) | "27.4% of all goals came from non-penalty set-pieces" |
| VAR overturns per match | 0.28 ± 0.05 | 0.29 ± 0.05 | 0.28 | +1% / +5% | [BBC Sport (republished)](https://www.modernghana.com/sports/1497747/every-var-error-in-2025-26-premier-league-how.html) | 105 overturns; read from ModernGhana's republication of the BBC Sport article |
| Ball in play | 53:20 ± 41 s | 53:45 ± 42 s | 55:23 | -4% / -3% | [Opta Analyst](https://theanalyst.com/articles/premier-league-rules-throw-ins-goal-kicks-ball-in-play) | "just 55 mins, 23 seconds last season" |
| Match length including added time (2024/25) | 100:59 ± 20 s | 101:17 ± 21 s | 99:44 | +1% / +2% | [Opta Analyst](https://theanalyst.com/articles/premier-league-ball-in-play-are-we-seeing-less-football-2025-26) | "99 mins, 44 secs" in 2024/25; no full-season 2025/26 figure found |
| Distance per team per match | 110.7 km ± 0.44 | 111.7 km ± 0.46 | 114.4 km | -3% / -2% | [Opta Analyst](https://theanalyst.com/articles/premier-league-running-more-stats-myths) | top-10 and bottom-10 season averages (4,363 and 4,332 km) over 38 matches |
| Fastest speed recorded in the season | 36.2 km/h | 36.2 km/h | 37.3 km/h | -3% / -3% | [Premier League](https://www.premierleague.com/en/news/4673057/who-ran-fastest-and-furthest-in-202526-premier-league) | "top speed of 37.30km/h" |
| Slowest club's fastest player | 34.0 km/h | 34.2 km/h | 34.7 km/h | -2% / -2% | [Premier League](https://www.premierleague.com/en/news/4673057/who-ran-fastest-and-furthest-in-202526-premier-league) | each club's fastest player: lowest 34.68 km/h |

## Largest differences

20 of the 32 figures are within 10% of the published value under both seeds, and 24 within 20%.

More than 10% off under both seeds, in the same direction, furthest first:

- Lowest club possession (season): generated 31.7% and 29.9%, published 42.5%.
- Draws: generated 21.3% and 20.0%, published 27.4%.
- Blocked shots per match: generated 5.93 and 5.92, published 7.36.
- Both teams scored: generated 43.2% and 45.5%, published 56.1%.
- Red cards per match: generated 0.17 and 0.14, published 0.12.
- Shots on target per match: generated 7.16 and 7.31, published 8.37.
- Penalties per match: generated 0.27 and 0.30, published 0.24.

Possession here is each club's share of the passes in its matches. The generated clubs spread wider than the real ones: the club with least of the ball has less of it than any real club, and the club with most has more.

Draws are rarer than in the real league. Most of the difference has gone to home wins: across the seasons they average +4.3 points on the published rate, and away wins +2.4, so home advantage is stronger than in the real league.

More shots miss the target than in the real league: across the seasons, 12.1 a match against 9.3, since fewer are on target or blocked.

More than 10% off under one seed but not the other: away wins (+5% / +11%), goalless matches (+33% / +0%), offsides per match (+6% / +13%), own goals per match (+25% / -7%), headed share of goals (-4% / -25%).

## Physical figures for context

These published figures describe a different season, or were read from a chart rather than text,
so they are shown beside the generated figures, pooled over both seasons, without being used as
targets.

| Metric | Generated | Published | Source |
| --- | --- | --- | --- |
| Distance per team per match, 2024/25 | 111.2 km (SD 6.3) | 113.9 km (SD 4.1) | [Allen et al., Br J Sports Med 2025 (Second Spectrum tracking); value read from Figure 2](https://doi.org/10.1136/bjsports-2025-110430) |
| Sprint distance (>7 m/s) per team per match, 2024/25 | 2.7 km (SD 0.9) | 2.3 km (SD 0.5) | [Allen et al., Br J Sports Med 2025; value read from Figure 2](https://doi.org/10.1136/bjsports-2025-110430) |
| Distance per 90 minutes, regular players, 2024/25 to Matchweek 29 | 8.1 to 11.1 km (lowest and highest of the outfield players with 1,500 minutes or more by matchday 29, both seasons) | 8.5 to 12.3 km | [premierleague.com (Opta Analyst)](https://www.premierleague.com/en/news/4272290) |

## Sources

Results, shots on target, fouls, corners and yellow cards are counted from football-data.co.uk's
2025/26 match file. Figures sourced to premierleague.com's club stats are the 20 clubs' 2025/26
season totals, summed, read from the data behind the site's club stats pages; the sums match Opta
Analyst's published season totals where both exist (1,045 goals, 9,503 shots, 273,956 successful
passes, 44 red cards, 13,615 throw-ins, 5,901 goal kicks).
The VAR count is from ModernGhana's republication of the BBC Sport article; the BBC original
wasn't read. Quotes and sums were checked against the sources on 2026-10-19.
