# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The folders GLib would report when GLib is not there, and what the application does on Windows before GTK loads.

Windows is simulated, so these run on every system.
"""

import os
import sys

import pytest

import config
import winsupport
from config import APP_ID


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(config, "_on_windows", lambda: True)
    monkeypatch.setattr(winsupport, "is_windows", lambda: True)


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(config, "_on_windows", lambda: False)
    monkeypatch.setattr(winsupport, "is_windows", lambda: False)


# -- config.fallback_base_dir -----------------------------------------------------------------------------

def test_on_linux_the_fallback_folders_are_the_xdg_defaults(linux, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert config.fallback_base_dir("data") == str(tmp_path / ".local" / "share")
    assert config.fallback_base_dir("config") == str(tmp_path / ".config")


def test_on_windows_data_is_local_app_data_and_settings_are_in_app_data(windows, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Ali\AppData\Local")
    monkeypatch.setenv("APPDATA", r"C:\Users\Ali\AppData\Roaming")
    assert config.fallback_base_dir("data") == r"C:\Users\Ali\AppData\Local"
    assert config.fallback_base_dir("config") == r"C:\Users\Ali\AppData\Roaming"


def test_on_windows_a_missing_variable_falls_back_to_the_profile_folder(windows, monkeypatch, tmp_path):
    for variable in ("LOCALAPPDATA", "APPDATA"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert config.fallback_base_dir("data") == os.path.join(str(tmp_path), "AppData", "Local")
    assert config.fallback_base_dir("config") == os.path.join(str(tmp_path), "AppData", "Roaming")


def test_an_unknown_kind_of_folder_is_refused():
    with pytest.raises(ValueError):
        config.fallback_base_dir("cache")


def test_the_data_folder_without_glib_follows_the_fallback(windows, monkeypatch):
    monkeypatch.setitem(sys.modules, "gi.repository", None)          # `from gi.repository import GLib` now fails.
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Ali\AppData\Local")
    assert config.user_data_dir() == os.path.join(r"C:\Users\Ali\AppData\Local", APP_ID)


# -- winsupport: finding the GTK runtime -----------------------------------------------------------------

def make_runtime(folder):
    (folder / "bin").mkdir(parents=True)
    (folder / "lib" / "girepository-1.0").mkdir(parents=True)
    return str(folder)


@pytest.fixture
def clean_environment(monkeypatch, tmp_path):
    monkeypatch.delenv(winsupport.GTK_DIR_VARIABLE, raising=False)
    monkeypatch.delenv("GI_TYPELIB_PATH", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("PATH", "original")
    monkeypatch.setattr(winsupport, "_dll_directories", [])
    # The installer puts the application beside its virtual environment: <app>\.venv is sys.prefix, <app>\gtk the runtime.
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "app" / ".venv"))


def test_the_runtime_in_the_variable_is_used_first(clean_environment, monkeypatch, tmp_path):
    custom = make_runtime(tmp_path / "my-gtk")
    make_runtime(tmp_path / "data" / APP_ID / "gtk")
    monkeypatch.setenv(winsupport.GTK_DIR_VARIABLE, custom)
    assert winsupport.runtime_folder() == custom


def test_without_the_variable_the_runtime_is_where_the_install_script_puts_it(clean_environment, tmp_path):
    default = make_runtime(tmp_path / "data" / APP_ID / "gtk")
    assert winsupport.runtime_folder() == default


def test_a_variable_that_points_nowhere_is_ignored(clean_environment, monkeypatch, tmp_path):
    default = make_runtime(tmp_path / "data" / APP_ID / "gtk")
    monkeypatch.setenv(winsupport.GTK_DIR_VARIABLE, str(tmp_path / "gone"))
    assert winsupport.runtime_folder() == default


def test_no_runtime_means_none(clean_environment):
    assert winsupport.runtime_folder() is None


def test_the_application_folder_is_the_parent_of_the_virtual_environment(clean_environment, tmp_path):
    assert winsupport.application_folder() == str(tmp_path / "app")


def test_the_runtime_inside_the_installer_is_found_before_a_downloaded_one(clean_environment, tmp_path):
    # The installer puts it in <application folder>\gtk, beside the .venv, and nothing has to tell the application.
    bundled = make_runtime(tmp_path / "app" / "gtk")
    make_runtime(tmp_path / "data" / APP_ID / "gtk")
    assert winsupport.runtime_folder() == bundled
    assert winsupport.runtime_candidates() == [bundled, os.path.join(str(tmp_path / "data"), APP_ID, "gtk")]


def test_the_variable_still_wins_over_the_runtime_inside_the_installer(clean_environment, monkeypatch, tmp_path):
    make_runtime(tmp_path / "app" / "gtk")
    custom = make_runtime(tmp_path / "my-gtk")
    monkeypatch.setenv(winsupport.GTK_DIR_VARIABLE, custom)
    assert winsupport.runtime_folder() == custom


def test_a_variable_that_points_nowhere_falls_back_to_the_runtime_inside_the_installer(clean_environment, monkeypatch, tmp_path):
    bundled = make_runtime(tmp_path / "app" / "gtk")
    monkeypatch.setenv(winsupport.GTK_DIR_VARIABLE, str(tmp_path / "gone"))
    assert winsupport.runtime_folder() == bundled


def test_a_folder_without_bin_is_not_a_runtime(clean_environment, tmp_path):
    (tmp_path / "app" / "gtk").mkdir(parents=True)                    # An empty or damaged folder.
    default = make_runtime(tmp_path / "data" / APP_ID / "gtk")
    assert winsupport.runtime_folder() == default


# -- winsupport: preparing it -------------------------------------------------------------------------------

def test_the_runtime_is_registered_for_dlls_and_put_on_the_search_paths(windows, clean_environment, monkeypatch, tmp_path):
    root = make_runtime(tmp_path / "gtk")
    monkeypatch.setenv(winsupport.GTK_DIR_VARIABLE, root)
    registered = []
    monkeypatch.setattr(os, "add_dll_directory", lambda folder: registered.append(folder) or object(), raising=False)

    assert winsupport.prepare_runtime() == root
    assert registered == [os.path.join(root, "bin")]
    assert os.environ["PATH"] == os.path.join(root, "bin") + os.pathsep + "original"
    assert os.environ["GI_TYPELIB_PATH"] == os.path.join(root, "lib", "girepository-1.0")


def test_an_existing_typelib_path_is_kept_after_the_runtime_s(windows, clean_environment, monkeypatch, tmp_path):
    root = make_runtime(tmp_path / "gtk")
    monkeypatch.setenv(winsupport.GTK_DIR_VARIABLE, root)
    monkeypatch.setenv("GI_TYPELIB_PATH", "elsewhere")
    monkeypatch.setattr(os, "add_dll_directory", lambda folder: object(), raising=False)
    winsupport.prepare_runtime()
    assert os.environ["GI_TYPELIB_PATH"] == os.path.join(root, "lib", "girepository-1.0") + os.pathsep + "elsewhere"


def test_nothing_is_changed_when_no_runtime_is_found(windows, clean_environment):
    assert winsupport.prepare_runtime() is None
    assert os.environ["PATH"] == "original"


def test_nothing_is_changed_outside_windows(linux, clean_environment, monkeypatch, tmp_path):
    monkeypatch.setenv(winsupport.GTK_DIR_VARIABLE, make_runtime(tmp_path / "gtk"))
    assert winsupport.prepare_runtime() is None
    assert os.environ["PATH"] == "original"


# -- winsupport: the Visual C++ runtime that the installer carries -----------------------------------------

RUNTIME_DLLS = ("msvcp140.dll", "msvcp140_1.dll", "vcomp140.dll", "concrt140.dll")


def make_vcruntime(folder, names=RUNTIME_DLLS) -> str:
    folder.mkdir(parents=True)
    for name in names:
        (folder / name).write_bytes(b"x")
    (folder / "NOTICE.txt").write_text("not a library", encoding="utf-8")
    return str(folder)


def test_the_runtime_dlls_that_came_with_the_installer_are_found_beside_the_program(clean_environment, tmp_path):
    assert winsupport.find_vcruntime() is None                                       # <application folder>\\vcruntime does not exist.
    (tmp_path / "app" / "vcruntime").mkdir(parents=True)
    assert winsupport.find_vcruntime() is None                                       # A folder without libraries is no runtime.
    make_vcruntime(tmp_path / "other" / "vcruntime")
    assert winsupport.find_vcruntime() is None                                       # Only the one beside this program counts.
    (tmp_path / "app" / "vcruntime" / "msvcp140.dll").write_bytes(b"x")
    assert winsupport.find_vcruntime() == str(tmp_path / "app" / "vcruntime")


def test_configuring_loads_every_runtime_dll_in_order_and_makes_the_folder_known(clean_environment, monkeypatch, tmp_path):
    folder = make_vcruntime(tmp_path / "vcruntime")
    loaded, added = [], []
    monkeypatch.setattr(winsupport, "_load_library", lambda path: loaded.append(path))
    monkeypatch.setattr(os, "add_dll_directory", lambda path: added.append(path) or object(), raising=False)
    names = winsupport.configure_vcruntime(folder)
    # msvcp140.dll has to be there before msvcp140_1.dll, which imports it.
    assert names == ["concrt140.dll", "msvcp140.dll", "msvcp140_1.dll", "vcomp140.dll"]
    assert loaded == [os.path.join(folder, name) for name in names]                  # By full path.
    assert added == [folder]
    assert os.environ["PATH"].split(os.pathsep) == [folder, "original"]


def test_a_runtime_dll_that_cannot_be_loaded_is_skipped_and_the_others_still_are(clean_environment, monkeypatch, tmp_path):
    folder = make_vcruntime(tmp_path / "vcruntime")
    tried = []

    def load(path):
        tried.append(os.path.basename(path))
        if os.path.basename(path) == "msvcp140_1.dll":
            raise OSError("not a valid Win32 application")

    monkeypatch.setattr(winsupport, "_load_library", load)
    monkeypatch.setattr(os, "add_dll_directory", lambda path: object(), raising=False)
    assert winsupport.configure_vcruntime(folder) == ["concrt140.dll", "msvcp140.dll", "vcomp140.dll"]
    assert tried == ["concrt140.dll", "msvcp140.dll", "msvcp140_1.dll", "vcomp140.dll"]


def test_a_folder_that_windows_will_not_register_does_not_stop_the_libraries_from_being_loaded(clean_environment, monkeypatch, tmp_path):
    folder = make_vcruntime(tmp_path / "vcruntime")
    loaded = []

    def refuse(path):
        raise OSError("refused")

    monkeypatch.setattr(os, "add_dll_directory", refuse, raising=False)
    monkeypatch.setattr(winsupport, "_load_library", lambda path: loaded.append(os.path.basename(path)))
    assert winsupport.configure_vcruntime(folder) == loaded == ["concrt140.dll", "msvcp140.dll", "msvcp140_1.dll", "vcomp140.dll"]


def test_pythons_own_runtime_is_never_loaded_a_second_time(clean_environment, monkeypatch, tmp_path):
    # vcruntime140.dll is already in the process (python.exe loaded it from the Python folder); a second copy would be a
    # second C runtime. The build leaves it out (scripts/vcruntime-bundle.ps1); this makes sure nothing here loads one.
    folder = make_vcruntime(tmp_path / "vcruntime", (*RUNTIME_DLLS, "vcruntime140.dll", "vcruntime140_1.dll"))
    loaded = []
    monkeypatch.setattr(winsupport, "_load_library", lambda path: loaded.append(os.path.basename(path)))
    monkeypatch.setattr(os, "add_dll_directory", lambda path: object(), raising=False)
    winsupport.configure_vcruntime(folder)
    assert loaded and not [name for name in loaded if name.startswith("vcruntime")]


def test_a_folder_that_cannot_be_listed_loads_nothing(clean_environment, monkeypatch, tmp_path):
    monkeypatch.setattr(winsupport, "_load_library", lambda path: pytest.fail("there is nothing to load"))
    monkeypatch.setattr(os, "add_dll_directory", lambda path: object(), raising=False)
    assert winsupport.configure_vcruntime(str(tmp_path / "gone")) == []


def test_prepare_loads_the_installers_runtime_before_gtk_is_looked_for(windows, clean_environment, monkeypatch, tmp_path):
    folder = make_vcruntime(tmp_path / "app" / "vcruntime")
    runtime = make_runtime(tmp_path / "app" / "gtk")
    steps = []
    monkeypatch.setattr(winsupport, "configure_vcruntime", lambda path: steps.append(("vcruntime", path)))
    real_runtime_folder = winsupport.runtime_folder

    def runtime_folder():
        steps.append("looking for gtk")
        return real_runtime_folder()

    monkeypatch.setattr(winsupport, "runtime_folder", runtime_folder)
    monkeypatch.setattr(os, "add_dll_directory", lambda path: steps.append(("gtk", path)) or object(), raising=False)
    assert winsupport.prepare_runtime() == runtime
    assert steps == [("vcruntime", folder), "looking for gtk", ("gtk", os.path.join(runtime, "bin"))]


def test_the_runtime_dlls_are_loaded_even_when_there_is_no_gtk_runtime(windows, clean_environment, monkeypatch, tmp_path):
    folder = make_vcruntime(tmp_path / "app" / "vcruntime")
    steps = []
    monkeypatch.setattr(winsupport, "configure_vcruntime", lambda path: steps.append(path))
    assert winsupport.prepare_runtime() is None                                      # No GTK: the answer stays the same ...
    assert steps == [folder]                                                         # ... and the libraries still get their runtime.


def test_prepare_without_the_installers_runtime_loads_nothing(windows, clean_environment, monkeypatch):
    monkeypatch.setattr(winsupport, "configure_vcruntime", lambda path: pytest.fail("there is nothing to load"))
    assert winsupport.prepare_runtime() is None


def test_prepare_loads_nothing_outside_windows(linux, clean_environment, monkeypatch, tmp_path):
    make_vcruntime(tmp_path / "app" / "vcruntime")
    monkeypatch.setattr(winsupport, "configure_vcruntime", lambda path: pytest.fail("this is not Windows"))
    assert winsupport.prepare_runtime() is None


def test_a_library_is_loaded_by_its_full_path_and_the_handle_is_kept(monkeypatch, tmp_path):
    import ctypes

    asked, handles = [], []

    def win_dll(path):
        asked.append(path)
        handles.append(object())
        return handles[-1]

    monkeypatch.setattr(ctypes, "WinDLL", win_dll, raising=False)          # Windows only; a stand-in here.
    monkeypatch.setattr(winsupport, "_loaded_runtime", [])
    path = str(tmp_path / "msvcp140.dll")
    winsupport._load_library(path)
    assert asked == [path]
    assert winsupport._loaded_runtime == handles                           # Kept for as long as the process lives.


@pytest.mark.skipif(sys.platform != "win32", reason="loads a real Windows library")
def test_on_windows_a_library_is_loaded_by_its_full_path_and_kept(tmp_path):
    version_dll = os.path.join(os.environ["SystemRoot"], "System32", "version.dll")
    before = len(winsupport._loaded_runtime)
    winsupport._load_library(version_dll)
    assert len(winsupport._loaded_runtime) == before + 1
    with pytest.raises(OSError):
        winsupport._load_library(str(tmp_path / "missing.dll"))


# -- winsupport: the log of a start without a console ---------------------------------------------------

def lose_the_console(monkeypatch):
    """pythonw.exe: no stdout, no stderr (the process's real descriptors are left alone).

    Called inside the test: pytest puts its own streams back on sys.stdout and sys.stderr between a fixture and the test."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(winsupport, "_redirect_c_streams", lambda stream: None)


def test_errors_of_a_start_without_a_console_go_to_the_log(windows, clean_environment, monkeypatch, tmp_path):
    lose_the_console(monkeypatch)
    assert winsupport.log_errors_without_a_console()
    expected = tmp_path / "data" / APP_ID / "karamtc.log"
    assert winsupport.log_path() == str(expected)
    print("traceback text", file=sys.stderr)
    sys.stderr.flush()
    text = expected.read_text(encoding="utf-8")
    assert "KaramTC is starting" in text and "traceback text" in text
    sys.stderr.close()


def test_the_log_is_appended_to_and_started_afresh_when_it_grows_too_big(windows, clean_environment, monkeypatch, tmp_path):
    lose_the_console(monkeypatch)
    path = tmp_path / "data" / APP_ID / "karamtc.log"
    path.parent.mkdir(parents=True)
    path.write_text("an earlier run\n", encoding="utf-8")
    assert winsupport.log_errors_without_a_console()
    sys.stderr.close()
    assert path.read_text(encoding="utf-8").startswith("an earlier run\n")

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(winsupport, "_LOG_LIMIT_BYTES", 5)
    assert winsupport.log_errors_without_a_console()
    sys.stderr.close()
    assert "an earlier run" not in path.read_text(encoding="utf-8")


def test_a_console_is_left_alone(windows, clean_environment, capsys, tmp_path):
    assert sys.stderr is not None
    assert not winsupport.log_errors_without_a_console()
    assert not (tmp_path / "data").exists()


def test_no_log_is_made_outside_windows(linux, clean_environment, monkeypatch, tmp_path):
    lose_the_console(monkeypatch)
    assert not winsupport.log_errors_without_a_console()
    assert sys.stderr is None and not (tmp_path / "data").exists()


def test_a_log_that_cannot_be_opened_does_not_stop_the_start(windows, clean_environment, monkeypatch):
    lose_the_console(monkeypatch)

    def refuse(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("builtins.open", refuse)
    assert not winsupport.log_errors_without_a_console()
