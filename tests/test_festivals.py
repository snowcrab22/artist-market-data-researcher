from datetime import date

import pytest

from artistscore.festivals import dedupe, festival_score, match_festival
from artistscore.models import FestivalAppearance

TODAY = date(2026, 10, 7)


def test_matches_catalog_name_in_event_title():
    assert match_festival("Coachella 2024") == ("Coachella", 1)


def test_matches_catalog_venue():
    assert match_festival("", "Empire Polo Club") == ("Coachella", 1)


def test_matches_accented_and_punctuated_names():
    assert match_festival("Primavera Sound Barcelona 2025") == ("Primavera Sound", 1)
    assert match_festival("Sónar 2024") == ("Sónar", 2)


def test_generic_festival_word_is_tier_three():
    assert match_festival("Some Town Fest") == ("Some Town Fest", 3)
    assert match_festival("Some Town Fest 2024") == ("Some Town Fest", 3)
    assert match_festival(None, "Riverside Music Festival Grounds") == ("Riverside Music Festival Grounds", 3)


@pytest.mark.parametrize("text", ["Madison Square Garden", "Reading Town Hall", "Festival Hall"])
def test_non_festivals_do_not_match(text):
    # "Festival Hall" is a common venue name, not a festival
    assert match_festival(text) is None


def test_score_decays_with_two_year_half_life():
    assert festival_score([FestivalAppearance("Coachella", 1, TODAY)], TODAY) == pytest.approx(10)
    two_years = date(2024, 10, 7)
    assert festival_score([FestivalAppearance("Coachella", 1, two_years)], TODAY) == pytest.approx(5, rel=0.01)


def test_score_points_by_tier_and_role():
    apps = [FestivalAppearance("A", 1, TODAY, "headliner"), FestivalAppearance("B", 2, TODAY),
            FestivalAppearance("C", 3, TODAY, "headliner")]
    assert festival_score(apps, TODAY) == pytest.approx(20 + 5 + 3)


def test_score_ignores_older_than_five_years_and_counts_upcoming_fully():
    apps = [FestivalAppearance("Old", 1, date(2020, 1, 1)), FestivalAppearance("Soon", 2, date(2027, 6, 1))]
    assert festival_score(apps, TODAY) == pytest.approx(5)


def test_dedupe_same_festival_same_year_prefers_headliner():
    apps = [FestivalAppearance("Coachella", 1, date(2024, 4, 12), None, "setlistfm"),
            FestivalAppearance("Coachella", 1, date(2024, 4, 19), "headliner", "musicbrainz"),
            FestivalAppearance("Coachella", 1, date(2023, 4, 14), None, "setlistfm")]
    result = dedupe(apps)
    assert len(result) == 2
    assert [a.role for a in result if a.date.year == 2024] == ["headliner"]
