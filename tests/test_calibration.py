"""A guard against drift: a small batch of matches stays in broad bands around the published
figures. docs/calibration.md has the full comparison."""

import pytest

from footnote.calibration.report import measure, run


@pytest.mark.slow
def test_a_small_batch_stays_in_range() -> None:
    summaries, physical, _ = run(seed=2026, workers=8, limit=48)
    m = measure(summaries, physical)
    bands = {
        "goals": (2.0, 3.6),
        "shots": (19.0, 31.0),
        "passes_per_team": (360.0, 520.0),
        "pass_completion": (0.78, 0.86),
        "fouls": (16.0, 27.0),
        "corners": (7.5, 12.5),
        "throw_ins": (28.0, 44.0),
        "offsides": (2.0, 5.0),
        "ball_in_play_min": (50.0, 61.0),
        "team_distance_km": (100.0, 125.0),
    }
    for key, (low, high) in bands.items():
        assert low <= m[key][0] <= high, f"{key} = {m[key][0]:.2f} outside [{low}, {high}]"
