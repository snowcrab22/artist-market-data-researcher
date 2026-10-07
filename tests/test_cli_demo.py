from datetime import date

from artistscore.demo import seed_demo
from artistscore.service import Service
from artistscore.storage import Store
from tests.conftest import DictSettings


def test_demo_seed_is_idempotent_and_ranks_sensibly(tmp_path):
    store = Store(tmp_path / "d.db")
    assert len(seed_demo(store, date(2026, 10, 7))) == 3
    assert seed_demo(store, date(2026, 10, 7)) == []
    service = Service(store, DictSettings(), sources=[])
    totals = {a["name"]: service.report(a["id"])["score"].total for a in store.list_artists()}
    headliner = totals["Demo: Arena Headliner (synthetic)"]
    assert headliner > totals["Demo: Mid-level Touring Band (synthetic)"]
    assert service.report(1)["score"].tier == "Superstar / headliner"  # a stadium act lands in the top tier
    # the viral act has reach but little live history: it must not outrank the touring band by much
    assert totals["Demo: Viral Newcomer (synthetic)"] < headliner
