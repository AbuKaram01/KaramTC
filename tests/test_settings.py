import json

import pytest

import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_config_dir", lambda: str(tmp_path / "cfg"))
    settings._unsaved.clear()
    yield tmp_path / "cfg" / settings.SETTINGS_FILE_NAME
    settings._unsaved.clear()


def test_values_round_trip_and_can_be_removed():
    assert settings.get("missing", 5) == 5
    settings.set("a", 7)
    assert settings.get("a", 0) == 7
    settings.remove("a")
    assert settings.get("a", 0) == 0


def test_a_stored_value_of_the_wrong_type_falls_back_to_the_default(isolated_settings):
    settings.set("seed", 1)
    isolated_settings.write_text(json.dumps({"n": "text", "flag": 1, "ratio": 2, "whole": 3.0, "items": {}}))
    assert settings.get("n", 10) == 10
    assert settings.get("flag", False) is False          # an int is not a bool
    assert settings.get("ratio", 0.5) == 2.0
    assert settings.get("whole", 0) == 3
    assert settings.get("items", []) == []


def test_a_damaged_file_is_set_aside_not_destroyed(isolated_settings):
    settings.set("seed", 1)
    isolated_settings.write_text("{not json")
    assert settings.load() == {}
    assert isolated_settings.with_name(isolated_settings.name + ".corrupt").exists()


def test_unwritable_settings_still_apply_for_the_session(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    monkeypatch.setattr(settings, "_config_dir", lambda: str(blocker / "sub"))
    settings.set("k", "v")
    assert settings.get("k", "") == "v"
