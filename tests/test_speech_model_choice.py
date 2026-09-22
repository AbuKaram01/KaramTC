"""Which downloadable speech model is saved, and what the app does with a damaged setting."""
import pytest

pytest.importorskip("gi", reason="ui.saved_settings needs PyGObject")

import settings
from core.media import model_store
from ui import saved_settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_config_dir", lambda: str(tmp_path / "cfg"))
    monkeypatch.setattr(model_store, "user_data_dir", lambda: str(tmp_path / "data"))
    settings._unsaved.clear()
    yield
    settings._unsaved.clear()


def test_the_recommended_model_is_used_until_another_is_chosen():
    assert saved_settings.speech_model_id() == "large-v3-turbo"
    assert saved_settings.read_speech_engine_settings().model_dir.endswith("whisper-large-v3-turbo")


def test_a_chosen_model_is_remembered_and_loaded_from_its_own_folder(tmp_path):
    settings.set(saved_settings.SPEECH_MODEL_CHOICE, "large-v3")
    assert saved_settings.speech_model_id() == "large-v3"
    assert saved_settings.read_speech_engine_settings().model_dir == str(tmp_path / "data" / "models" / "whisper-large-v3")
    assert saved_settings.speech_model_status() == (False, "Whisper large-v3 is not downloaded yet")


@pytest.mark.parametrize("damaged", ["large-v2", "", "../../etc/passwd", ["large-v3"], 7, None])
def test_a_damaged_model_choice_falls_back_to_the_recommended_model(tmp_path, damaged):
    settings.set(saved_settings.SPEECH_MODEL_CHOICE, damaged)
    assert saved_settings.speech_model_id() == "large-v3-turbo"
    assert saved_settings.read_speech_engine_settings().model_dir == model_store.managed_model_dir("large-v3-turbo")


def test_the_custom_folder_choice_ignores_the_downloadable_model(tmp_path):
    settings.set(saved_settings.SPEECH_MODEL_SOURCE, "custom")
    settings.set(saved_settings.SPEECH_MODEL_CHOICE, "large-v3")
    settings.set(saved_settings.SPEECH_MODEL_DIR, str(tmp_path / "mine"))
    assert saved_settings.read_speech_engine_settings().model_dir == str(tmp_path / "mine")
