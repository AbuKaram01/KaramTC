"""The model downloader against a local stand-in for the Hugging Face API and file server."""
import json
import os
import threading

import pytest

from core.media import model_store
from core.media.errors import DownloadCancelledError
from core.media.model_location import model_status
from fake_hub import CONTENT, MIB, start_hub


@pytest.fixture
def hub():
    state, stop = start_hub()
    yield state
    stop()


def test_a_download_produces_a_verified_model_folder(hub, tmp_path):
    progress = []
    model_store.download(lambda done, total, what: progress.append((done, total)), None, hub.url, str(tmp_path))

    assert model_store.is_downloaded(str(tmp_path))
    for name, data in CONTENT.items():
        assert (tmp_path / name).read_bytes() == data
    assert not [name for name in os.listdir(tmp_path) if name.endswith(".part")]
    totals = {total for _done, total in progress}
    assert totals == {sum(len(data) for data in CONTENT.values())}
    done_values = [done for done, _total in progress]
    assert done_values == sorted(done_values) and done_values[-1] == totals.pop()


def test_a_cancelled_download_continues_where_it_stopped(hub, tmp_path):
    cancel = threading.Event()

    def cancel_after_first_chunk(done, total, what):
        if what == "model.bin":
            cancel.set()
    with pytest.raises(DownloadCancelledError):
        model_store.download(cancel_after_first_chunk, cancel, hub.url, str(tmp_path))
    assert model_store.has_partial_download(str(tmp_path)) and not model_store.is_downloaded(str(tmp_path))
    kept = (tmp_path / "model.bin.part").stat().st_size
    assert 0 < kept < len(CONTENT["model.bin"])

    hub.requests.clear()
    model_store.download(None, None, hub.url, str(tmp_path))
    assert model_store.is_downloaded(str(tmp_path))
    assert (tmp_path / "model.bin").read_bytes() == CONTENT["model.bin"]
    resolve_requests = [request for request in hub.requests if "/resolve/" in request[0]]
    assert [path.rsplit("/", 1)[-1] for path, _ in resolve_requests] == ["model.bin"]      # small files were not fetched again
    assert resolve_requests[0][1] == f"bytes={kept}-"


def test_a_server_that_ignores_range_requests_still_gives_a_correct_file(hub, tmp_path):
    (tmp_path / "model.bin.part").write_bytes(CONTENT["model.bin"][:MIB])
    hub.ignore_range = True
    model_store.download(None, None, hub.url, str(tmp_path))
    assert (tmp_path / "model.bin").read_bytes() == CONTENT["model.bin"]


def test_a_corrupt_download_is_rejected_and_removed(hub, tmp_path):
    hub.files["model.bin"] = b"\x00" * len(CONTENT["model.bin"])      # right size, wrong content
    with pytest.raises(RuntimeError, match="checksum"):
        model_store.download(None, None, hub.url, str(tmp_path))
    assert not (tmp_path / "model.bin").exists() and not (tmp_path / "model.bin.part").exists()
    assert not model_store.is_downloaded(str(tmp_path))


def test_a_file_of_the_wrong_size_is_not_accepted(hub, tmp_path):
    (tmp_path / "model.bin.part").write_bytes(b"x" * (len(CONTENT["model.bin"]) + 10))   # more than exists upstream
    model_store.download(None, None, hub.url, str(tmp_path))                              # restarts it
    assert (tmp_path / "model.bin").read_bytes() == CONTENT["model.bin"]


def test_a_repository_missing_a_required_file_is_reported(hub, tmp_path):
    hub.omit = {"tokenizer.json"}
    with pytest.raises(RuntimeError, match="tokenizer.json"):
        model_store.download(None, None, hub.url, str(tmp_path))


def test_server_errors_become_readable_messages(hub, tmp_path):
    hub.fail_api_with = 503
    with pytest.raises(RuntimeError, match="HTTP 503"):
        model_store.download(None, None, hub.url, str(tmp_path))
    with pytest.raises(RuntimeError, match="Could not reach the download server"):
        model_store.download(None, None, "http://127.0.0.1:9", str(tmp_path))


def test_a_model_folder_that_lost_a_file_is_no_longer_ready(hub, tmp_path):
    model_store.download(None, None, hub.url, str(tmp_path))
    (tmp_path / "vocabulary.json").write_bytes(b"cut")
    assert not model_store.is_downloaded(str(tmp_path))
    model_store.delete(str(tmp_path))
    assert not tmp_path.exists()


def test_the_managed_folder_lives_in_the_app_data_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(model_store, "user_data_dir", lambda: str(tmp_path))
    assert model_store.managed_model_dir() == str(tmp_path / "models" / "whisper-large-v3-turbo")
    assert not model_store.is_downloaded()


# ── Choosing between the downloadable models ────────────────────────

def test_the_catalog_offers_turbo_as_the_recommended_model_and_large_v3_too():
    by_id = {model.id: model for model in model_store.MODELS}
    assert set(by_id) == {"large-v3-turbo", "large-v3"}
    assert [model.id for model in model_store.MODELS if model.recommended] == ["large-v3-turbo"]
    assert model_store.DEFAULT_MODEL_ID == "large-v3-turbo"
    assert by_id["large-v3-turbo"].display_label == "Whisper large-v3 turbo (Recommended)"
    assert by_id["large-v3"].display_label == "Whisper large-v3"
    assert by_id["large-v3"].repo == "Systran/faster-whisper-large-v3"
    assert len({model.folder for model in model_store.MODELS}) == len(model_store.MODELS)      # never share a folder
    assert len({model.repo for model in model_store.MODELS}) == len(model_store.MODELS)


@pytest.mark.parametrize("unknown", [None, "", "large-v2", "../../etc", ["large-v3"], 3])
def test_an_unknown_model_id_falls_back_to_the_default_model(unknown):
    assert model_store.get_model(unknown).id == model_store.DEFAULT_MODEL_ID


def test_each_model_has_its_own_folder_in_the_app_data_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(model_store, "user_data_dir", lambda: str(tmp_path))
    assert model_store.managed_model_dir("large-v3") == str(tmp_path / "models" / "whisper-large-v3")
    assert model_store.managed_model_dir("large-v3-turbo") == str(tmp_path / "models" / "whisper-large-v3-turbo")
    assert model_store.managed_model_dir("../../etc") == model_store.managed_model_dir()     # can't leave the models folder


def test_large_v3_is_downloaded_from_its_own_repository(hub, tmp_path):
    model_store.download(None, None, hub.url, str(tmp_path), model_id="large-v3")
    assert model_store.is_downloaded(str(tmp_path))
    paths = [path for path, _range in hub.requests]
    assert paths[0] == "/api/models/Systran/faster-whisper-large-v3/tree/main"
    assert all(path.startswith("/Systran/faster-whisper-large-v3/resolve/main/") for path in paths[1:])
    assert json.loads((tmp_path / "manifest.json").read_text())["repo"] == "Systran/faster-whisper-large-v3"


def test_the_default_download_still_comes_from_the_turbo_repository(hub, tmp_path):
    model_store.download(None, None, hub.url, str(tmp_path))
    assert hub.requests[0][0] == "/api/models/mobiuslabsgmbh/faster-whisper-large-v3-turbo/tree/main"


def test_the_models_are_kept_and_removed_independently(hub, monkeypatch, tmp_path):
    monkeypatch.setattr(model_store, "user_data_dir", lambda: str(tmp_path))
    model_store.download(None, None, hub.url, model_id="large-v3-turbo")
    assert model_store.is_downloaded(model_id="large-v3-turbo") and not model_store.is_downloaded(model_id="large-v3")

    model_store.download(None, None, hub.url, model_id="large-v3")
    assert model_store.is_downloaded(model_id="large-v3")

    model_store.delete(model_id="large-v3")
    assert not model_store.is_downloaded(model_id="large-v3") and model_store.is_downloaded(model_id="large-v3-turbo")


def test_the_model_status_names_the_chosen_model(hub, monkeypatch, tmp_path):
    monkeypatch.setattr(model_store, "user_data_dir", lambda: str(tmp_path))
    model_store.download(None, None, hub.url, model_id="large-v3-turbo")

    assert model_status("managed", "", "large-v3-turbo") == (True, "Whisper large-v3 turbo is ready")
    assert model_status("managed", "") == (True, "Whisper large-v3 turbo is ready")           # the default
    assert model_status("managed", "", "large-v3") == (False, "Whisper large-v3 is not downloaded yet")
    (tmp_path / "models" / "whisper-large-v3").mkdir()
    (tmp_path / "models" / "whisper-large-v3" / "model.bin.part").write_bytes(b"x")
    assert "partial download can be continued" in model_status("managed", "", "large-v3").message
