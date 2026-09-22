# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tesseract on Windows: found in its installer's folder, started without a console window, installed by winget.

Windows is simulated, so these run on every system.
"""

import os
import types
from pathlib import Path

import pytest

from config import SUPPORTED_EXT
from providers.ocr_types import OcrOptions
from providers.tesseract import install, languages, process, program
from providers.tesseract.command import build_command


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(program, "is_windows", lambda: True)


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(program, "is_windows", lambda: False)


@pytest.fixture
def installed_in_program_files(monkeypatch, tmp_path):
    """tesseract.exe in a Program Files folder, and nothing on PATH (the Windows installer never adds it)."""
    exe = tmp_path / "Program Files" / "Tesseract-OCR" / "tesseract.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(program.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    return str(exe)


# -- finding the program ------------------------------------------------------------------------------

def test_windows_looks_where_the_installer_puts_tesseract(windows, installed_in_program_files):
    assert program.windows_install_path() == installed_in_program_files
    assert program.find_tesseract() == installed_in_program_files
    assert program.program() == installed_in_program_files          # A full path: it is not on PATH.


def test_a_program_on_path_is_run_by_name(windows, monkeypatch):
    monkeypatch.setattr(program.shutil, "which", lambda name: "C:/tools/tesseract.exe")
    assert program.find_tesseract() == "C:/tools/tesseract.exe"
    assert program.program() == "tesseract"


def test_the_installer_folder_is_not_searched_outside_windows(linux, installed_in_program_files):
    assert program.windows_install_path() is None
    assert program.find_tesseract() is None
    assert program.program() == "tesseract"


def test_nothing_found_on_windows_still_names_the_program(windows, monkeypatch, tmp_path):
    monkeypatch.setattr(program.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "empty"))
    assert program.program() == "tesseract"


def test_the_commands_use_the_found_program(windows, installed_in_program_files):
    command = build_command("in.png", "out", "eng", 6, OcrOptions())
    assert command[:3] == [installed_in_program_files, "in.png", "out"]


def test_is_installed_sees_the_installer_folder(windows, installed_in_program_files):
    assert install.is_installed()


def test_is_not_installed_when_nothing_is_there(linux, installed_in_program_files):
    assert not install.is_installed()


def test_winget_is_the_install_command_on_windows(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "winget.exe" if name == "winget" else None)
    assert install.install_hint() == "Run: winget install UB-Mannheim.TesseractOCR"
    assert install.install_hint("ara") == "Run: winget install UB-Mannheim.TesseractOCR"
    assert install.osd_install_hint() == "Run: winget install UB-Mannheim.TesseractOCR"


# -- KaramTC's own copy of tesseract.exe --------------------------------------------------------------------------

@pytest.fixture
def own_copy(monkeypatch, tmp_path):
    """A tesseract.exe where the installer (or the install script) puts KaramTC's own copy."""
    exe = tmp_path / "app" / "tesseract" / "tesseract.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(program, "bundled_candidates", lambda: [str(tmp_path / "missing.exe"), str(exe)])
    return str(exe)


def test_the_copy_that_ships_with_karamtc_wins_over_everything_else(windows, own_copy, monkeypatch):
    monkeypatch.setattr(program.shutil, "which", lambda name: "C:/tools/tesseract.exe")       # Another one is on PATH.
    assert program.bundled_path() == own_copy
    assert program.find_tesseract() == own_copy
    assert program.program() == own_copy
    assert build_command("in.png", "out", "eng", 6, OcrOptions())[0] == own_copy


def test_an_own_copy_counts_as_installed(windows, own_copy, monkeypatch):
    monkeypatch.setattr(program.shutil, "which", lambda name: None)
    assert install.is_installed()


def test_an_own_copy_is_not_looked_for_outside_windows(linux, own_copy, monkeypatch):
    monkeypatch.setattr(program.shutil, "which", lambda name: None)
    assert program.bundled_path() is None
    assert program.find_tesseract() is None
    assert program.program() == "tesseract"


def test_without_an_own_copy_the_old_order_still_applies(windows, monkeypatch, tmp_path):
    monkeypatch.setattr(program, "bundled_candidates", lambda: [str(tmp_path / "nothing.exe")])
    monkeypatch.setattr(program.shutil, "which", lambda name: "C:/tools/tesseract.exe")
    assert program.bundled_path() is None
    assert program.find_tesseract() == "C:/tools/tesseract.exe"
    assert program.program() == "tesseract"


def test_the_own_copy_sits_beside_the_program_and_in_the_data_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    program_side, data_side = program.bundled_candidates()
    assert program_side.endswith(os.path.join("tesseract", "tesseract.exe"))
    assert Path(program_side).parent.parent == Path(program.__file__).resolve().parents[3]     # The folder holding src/.
    assert data_side == str(tmp_path / "data" / "io.github.AbuKaram01.KaramTC" / "tesseract" / "tesseract.exe")


# -- no console window -----------------------------------------------------------------------------------

def test_windows_starts_tesseract_without_a_console_window(windows):
    assert program.quiet_window_options() == {"creationflags": 0x08000000}


def test_nothing_is_added_outside_windows(linux):
    assert program.quiet_window_options() == {}


@pytest.mark.parametrize("on_windows, expected", [(True, {"creationflags": 0x08000000}), (False, {})])
def test_the_child_process_is_started_with_those_options(monkeypatch, on_windows, expected):
    monkeypatch.setattr(program, "is_windows", lambda: on_windows)
    started = {}

    def fake_popen(command, **options):
        started.update(options)
        return types.SimpleNamespace()

    monkeypatch.setattr(process.subprocess, "Popen", fake_popen)
    process._start(["tesseract", "in.png", "out"], None)
    assert {key: started[key] for key in expected} == expected
    assert ("creationflags" in started) is on_windows


def test_listing_languages_uses_the_found_program_and_no_console(windows, installed_in_program_files, monkeypatch):
    monkeypatch.setattr(languages, "is_installed", lambda: True)
    asked = {}

    def fake_run(command, **options):
        asked["command"], asked["options"] = command, options
        return types.SimpleNamespace(stdout="List of available languages (2):\neng\nara\n", stderr="")

    monkeypatch.setattr(languages.subprocess, "run", fake_run)
    assert languages.available_langs() == ["eng", "ara"]
    assert asked["command"] == [installed_in_program_files, "--list-langs"]
    assert asked["options"]["creationflags"] == 0x08000000


# -- the screen shown when it is missing ---------------------------------------------------------------------

def test_the_missing_tesseract_page_lists_windows():
    pytest.importorskip("gi")
    import gi

    try:
        gi.require_version("Adw", "1")
    except ValueError:
        pytest.skip("libadwaita is not available")
    from ui.install_warning import INSTALL_COMMANDS

    assert ("Windows", "winget install UB-Mannheim.TesseractOCR") in INSTALL_COMMANDS


# -- file dialogs ----------------------------------------------------------------------------------------------

def test_a_filter_matches_by_extension_whatever_the_case_and_the_registered_type():
    pytest.importorskip("gi")
    import gi

    try:
        gi.require_version("Gtk", "4.0")
    except ValueError:
        pytest.skip("GTK 4 is not available")
    from gi.repository import Gio

    from ui.file_dialogs import make_filter

    def entry(name):
        info = Gio.FileInfo()
        info.set_name(name)
        info.set_display_name(name)
        return info

    images = make_filter("Images", suffixes=SUPPORTED_EXT)
    assert all(images.match(entry(name)) for name in ("a.webp", "B.PNG", "c.JpEg", "d.jpg"))
    assert not images.match(entry("notes.txt"))
