from footnote.generator.league import CAST, League, build_league, pick_lineup


def test_league_is_deterministic(league: League) -> None:
    again = build_league(2026)
    assert league.public() == again.public()
    assert league.hidden() == again.hidden()


def test_different_seed_gives_a_different_league(league: League) -> None:
    assert build_league(2027).public() != league.public()


def test_twenty_clubs_of_twenty_five(league: League) -> None:
    assert len(league.clubs) == 20
    for club in league.clubs:
        assert len(club.squad) == 25
        shirts = [p.shirt for p in club.squad]
        assert len(set(shirts)) == 25
        assert sum(p.role == "GK" for p in club.squad) == 3


def test_names_are_unique_and_surnames_distinct(league: League) -> None:
    names = [n for kind, n in league.all_names() if kind != "club"]
    assert len(names) == len(set(names))
    surnames = [n.split(" ", 1)[1] for n in names]
    assert len(surnames) == len(set(surnames))


def test_cast_from_the_docs_exists_with_their_numbers(league: League) -> None:
    for code, entries in CAST.items():
        club = league.club(code)
        for entry in entries:
            player = next(p for p in club.squad if p.surname == entry["surname"])
            assert player.given == entry["given"]
            assert player.shirt == entry["shirt"]
            assert player.id == f"{code.lower()}-{entry['shirt']:02d}"


def test_cast_start_for_their_clubs(league: League) -> None:
    for code, entries in CAST.items():
        starters, bench = pick_lineup(league.club(code))
        starting = {p.surname for p in starters}
        assert {e["surname"] for e in entries} <= starting
        assert len(starters) == 11 and len(bench) == 9


def test_public_data_carries_no_attributes(league: League) -> None:
    public = league.public()
    player = public["clubs"][0]["squad"][0]
    assert "attrs" not in player and "quality" not in public["clubs"][0] and "style" not in public["clubs"][0]
