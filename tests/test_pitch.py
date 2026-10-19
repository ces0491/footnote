import numpy as np
import pytest

from footnote.generator.movement import offside_line
from footnote.generator.pitch import LENGTH, WIDTH, exit_point, goal_angle, to_frame


def test_team_frame_is_its_own_inverse() -> None:
    xy = np.array([[10.0, 20.0], [100.0, 5.0]])
    for direction in (1, -1):
        assert np.allclose(to_frame(to_frame(xy, direction), direction), xy)


def test_team_frame_flips_both_axes_for_a_team_attacking_left() -> None:
    assert np.allclose(to_frame(np.array([0.0, 0.0]), -1), [LENGTH, WIDTH])


def test_goal_angle_is_widest_close_to_goal() -> None:
    assert goal_angle(100.0, 34.0) > goal_angle(90.0, 34.0) > goal_angle(90.0, 10.0)


def test_exit_point_finds_the_line_crossed() -> None:
    point, line = exit_point(np.array([50.0, 60.0]), np.array([50.0, 80.0]))
    assert line == "touch" and point[1] == pytest.approx(WIDTH)
    assert exit_point(np.array([50.0, 30.0]), np.array([60.0, 30.0])) is None


def test_offside_line_is_the_second_last_opponent_and_never_behind_halfway() -> None:
    # Keeper at 103, last defender at 88, others deeper.
    assert offside_line(np.array([103.0, 88.0, 80.0, 70.0]), ball_u=60.0) == 88.0
    # Ball beyond the second-last opponent moves the line to the ball.
    assert offside_line(np.array([103.0, 88.0]), ball_u=95.0) == 95.0
    # In a team's own half nobody is offside.
    assert offside_line(np.array([103.0, 40.0]), ball_u=30.0) == LENGTH / 2
