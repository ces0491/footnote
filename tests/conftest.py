from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from footnote.generator.league import League, build_league
from footnote.generator.season import Fixture, GeneratedMatch, generate_match


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    """Psycopg's async mode can't run on Windows' default (proactor) loop; Linux keeps its default."""
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}


@pytest.fixture(scope="session")
def league() -> League:
    return build_league(2026)


@pytest.fixture(scope="session")
def fixture_sal_kin() -> Fixture:
    return Fixture(matchday=1, home="SAL", away="KIN", kickoff=datetime(2026, 8, 15, 14, 0, tzinfo=UTC))


@pytest.fixture(scope="session")
def match(league: League, fixture_sal_kin: Fixture) -> GeneratedMatch:
    """One full match with tracking, shared by the tests that inspect a match."""
    return generate_match(league, fixture_sal_kin, with_tracking=True, match_id="test-sal-kin")


@pytest.fixture(scope="session")
def matches(league: League) -> list[GeneratedMatch]:
    """A handful of different pairings, for checks that should hold in every match."""
    pairs = [("ESK", "STE"), ("BRW", "THI"), ("CAL", "FAL"), ("IRO", "MAR"), ("DUN", "YAR")]
    kickoff = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)
    return [generate_match(league, Fixture(1, h, a, kickoff), match_id=f"test-{h}-{a}".lower()) for h, a in pairs]
