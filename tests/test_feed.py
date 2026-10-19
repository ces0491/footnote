from footnote.generator.feed import MatchClock, clock_fields
from footnote.generator.schema import feed_json_schema


def test_broadcast_minute_counts_the_minute_in_progress() -> None:
    assert clock_fields(1, 22 * 60 + 30)["minute"] == 23
    assert clock_fields(1, 0.0)["minute"] == 1
    assert clock_fields(2, 0.0)["minute"] == 46
    assert clock_fields(2, 6 * 60 + 5)["minute"] == 52


def test_added_time_holds_the_minute_and_counts_on() -> None:
    first = clock_fields(1, 45 * 60 + 70)
    assert (first["minute"], first["added_minute"]) == (45, 2)
    second = clock_fields(2, 45 * 60 + 10)
    assert (second["minute"], second["added_minute"]) == (90, 1)
    assert clock_fields(2, 600.0)["clock"] == 2700.0 + 600.0


def test_a_correction_while_the_clock_is_stopped_shows_the_whistle() -> None:
    clock = MatchClock(first_half_end=2830.0, match_end=2990.0)
    # In play, the clock is the clock.
    assert clock.issued(clock.wall(2, 100.0)) == (2, 100.0, clock_fields(2, 100.0))
    # At half-time it sorts after the first half's whistle and shows that whistle's clock.
    period, t, shown = clock.issued(clock.wall(1, 2830.0) + 300.0)
    assert (period, t) == (1, 3130.0) and shown == clock_fields(1, 2830.0)
    # After the match likewise, with the final whistle's clock.
    period, t, shown = clock.issued(clock.wall(2, 2990.0) + 1200.0)
    assert period == 2 and t == 4190.0 and shown == clock_fields(2, 2990.0)


def test_schema_exports() -> None:
    schema = feed_json_schema()
    assert "oneOf" in schema or "discriminator" in schema


def test_schema_bounds_coordinates_to_the_pitch() -> None:
    """2 m to spare beyond each line: 105 m long, 68 m wide."""
    props = feed_json_schema()["$defs"]["Pass"]["properties"]
    assert (props["x"]["minimum"], props["x"]["maximum"]) == (-2.0, 107.0)
    assert (props["y"]["minimum"], props["y"]["maximum"]) == (-2.0, 70.0)
