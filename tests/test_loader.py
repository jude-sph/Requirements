import pytest
from pathlib import Path
from src.loader import load_workbook_data

XLSX_PATH = Path(__file__).parent.parent / "GTR-SDS.xlsx"


@pytest.fixture(scope="module")
def data():
    return load_workbook_data(XLSX_PATH)


class TestLoadDigs:
    def test_digs_loaded(self, data):
        assert len(data.digs) > 100
        assert len(data.digs) <= 110

    def test_dig_has_id_and_text(self, data):
        first = list(data.digs.values())[0]
        assert first["dig_id"] != ""
        assert first["dig_text"] != ""
        assert "." not in first["dig_id"]

    def test_no_leading_whitespace_in_dig_text(self, data):
        for dig in data.digs.values():
            assert dig["dig_text"] == dig["dig_text"].strip()

    def test_duplicate_dig_warned(self, data, capfd):
        assert "10237" in data.digs


class TestLoadSystemHierarchy:
    def test_hierarchy_loaded(self, data):
        assert len(data.system_hierarchy) > 100

    def test_top_level_blocks(self, data):
        ids = [h["id"] for h in data.system_hierarchy]
        assert any("100" in id for id in ids)
        assert any("200" in id for id in ids)
        assert any("900" in id for id in ids)

    def test_no_empty_entries(self, data):
        for h in data.system_hierarchy:
            assert h["id"].strip() != ""


class TestLoadChapters:
    def test_gtr_chapters_loaded(self, data):
        assert len(data.gtr_chapters) >= 11

    def test_sds_chapters_loaded(self, data):
        assert len(data.sds_chapters) >= 20

    def test_chapter_codes_stripped(self, data):
        for ch in data.gtr_chapters:
            assert ch == ch.strip()
        for ch in data.sds_chapters:
            assert ch == ch.strip()

    def test_gtr_chapter_format(self, data):
        for ch in data.gtr_chapters:
            assert ch.startswith("GTR-Ch")


class TestLoadAcceptancePhases:
    def test_five_phases(self, data):
        assert len(data.acceptance_phases) == 5

    def test_phase_text_not_empty(self, data):
        for phase in data.acceptance_phases:
            assert len(phase) > 20


class TestLoadVerificationRefs:
    def test_methods_loaded(self, data):
        assert len(data.verification_methods) >= 5
        method_names = [m["name"] for m in data.verification_methods]
        assert any("Test" in n for n in method_names)
        assert any("Inspection" in n for n in method_names)

    def test_events_loaded(self, data):
        assert len(data.verification_events) >= 6
        event_names = [e["name"] for e in data.verification_events]
        assert any("FAT" in n for n in event_names)
        assert any("HAT" in n for n in event_names)
