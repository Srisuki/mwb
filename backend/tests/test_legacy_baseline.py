from pathlib import Path

from app.services.legacy_baseline import read_legacy_baseline


def test_complete_legacy_baseline_is_preserved():
    source = Path(__file__).parents[2] / "MWB_Internal_Audit_Manager.html"
    entities, areas, checklist = read_legacy_baseline(source)
    assert len(entities) == 34
    assert len(areas) == 16
    assert sum(len(items) for items in checklist.values()) == 131
    assert (
        checklist["Sales Audit"][0] == "Whether GSTR-1 generated from Tally is free from all errors"
    )
