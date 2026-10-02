import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.rules import RuleSet

r=RuleSet(ROOT/'config'/'rules_2026_2027.json')


def test_official_weekly_totals():
    assert sum(r.subjects(1).values()) == 20*60
    assert sum(r.subjects(2).values()) == 22*60
    assert sum(r.subjects(3).values()) == 25*60
    assert sum(r.subjects(4).values()) == 25*60
    assert sum(r.subjects(5).values()) == 28*60
    assert sum(r.subjects(6).values()) == 28*60


def test_profiles_only_recommend_official_subjects():
    official = set(r.all_subjects())
    assert r.specialties()
    assert r.trainings()
    for specialty in r.specialties():
        assert set(r.recommended_subjects(specialty)) <= official
