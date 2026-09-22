# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tesseract's Windows builds cannot take paths with non-ASCII letters (a user name in Arabic puts them in TEMP and in
the data folder): it is started inside its working folder, given relative ASCII names and short paths.

Windows is simulated, so these run on every system. (The real thing is checked by the windows-full-install job.)
"""

import os
import shutil
import tempfile

import pytest

from providers.ocr_types import OcrOptions
from providers.tesseract import ascii_paths, engine, program
from providers.tesseract.ascii_paths import safe_arguments
from providers.tesseract.process import ProcessOutput

ARABIC = "\u0623\u062d\u0645\u062f"                # "Ahmad"
PICTURE_NAME = "\u0635\u0641\u062d\u0629.png"       # "page.png"


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(ascii_paths, "_on_windows", lambda: True)
    # Without 8.3 names and without junctions unless a test says otherwise.
    monkeypatch.setattr(ascii_paths, "short_path", lambda path: None)
    monkeypatch.setattr(ascii_paths, "make_junction", lambda target, link: False)


def make_picture(folder, name=PICTURE_NAME):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"picture bytes")
    return str(path)


# -- nothing to do ------------------------------------------------------------------------------------------

def test_ascii_paths_are_given_as_they_are(windows, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    image = make_picture(tmp_path / "pictures", "page.png")
    with safe_arguments(image, str(work / "result"), str(tmp_path / "tessdata"), str(work)) as safe:
        assert (safe.image, safe.output_base, safe.tessdata_dir, safe.cwd) == (
            image, str(work / "result"), str(tmp_path / "tessdata"), None)


def test_nothing_changes_outside_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(ascii_paths, "_on_windows", lambda: False)
    work = tmp_path / ARABIC
    work.mkdir()
    image = make_picture(tmp_path / ARABIC)
    with safe_arguments(image, str(work / "result"), str(tmp_path / ARABIC / "tessdata"), str(work)) as safe:
        assert (safe.image, safe.output_base, safe.tessdata_dir, safe.cwd) == (
            image, str(work / "result"), str(tmp_path / ARABIC / "tessdata"), None)


def test_a_missing_tessdata_dir_stays_missing(windows, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    image = make_picture(tmp_path / "pictures", "page.png")
    with safe_arguments(image, str(work / "result"), None, str(work)) as safe:
        assert safe.tessdata_dir is None


# -- the picture and the output ---------------------------------------------------------------------------

def test_a_picture_with_arabic_letters_is_copied_into_the_working_folder(windows, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    image = make_picture(tmp_path / ARABIC)
    with safe_arguments(image, str(work / "result"), None, str(work)) as safe:
        assert safe.image == "input.png" and safe.output_base == "result"
        assert safe.cwd == str(work)
        assert (work / "input.png").read_bytes() == b"picture bytes"
    assert os.path.exists(image)                                   # The original is left alone.


def test_a_working_folder_with_arabic_letters_gets_relative_names(windows, tmp_path):
    work = tmp_path / ARABIC / "Temp"
    work.mkdir(parents=True)
    ascii_picture = make_picture(tmp_path / "pictures", "page.png")
    with safe_arguments(ascii_picture, str(work / "result"), None, str(work)) as safe:
        assert safe.image == ascii_picture                          # Already ASCII: used as it is, not copied.
        assert safe.output_base == "result" and safe.cwd == str(work)
    assert not (work / "input.png").exists()


def test_a_picture_already_in_the_working_folder_is_not_copied(windows, tmp_path):
    work = tmp_path / ARABIC / "Temp"
    work.mkdir(parents=True)
    upright = make_picture(work, "upright.png")
    with safe_arguments(upright, str(work / "result"), None, str(work)) as safe:
        assert safe.image == "upright.png"
    assert sorted(os.listdir(work)) == ["upright.png"]


def test_a_picture_that_cannot_be_copied_is_given_as_it_is(windows, monkeypatch, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    image = make_picture(tmp_path / ARABIC)

    def refuse(source, target):
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copyfile", refuse)
    with safe_arguments(image, str(work / "result"), None, str(work)) as safe:
        assert safe.image == image


# -- the language data --------------------------------------------------------------------------------------

def test_language_data_in_an_arabic_folder_is_given_by_its_short_name(windows, monkeypatch, tmp_path):
    tessdata = tmp_path / ARABIC / "tessdata"
    tessdata.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(ascii_paths, "short_path", lambda path: "C:\\IO3F2D~1\\TESSDA~1" if path == str(tessdata) else None)
    with safe_arguments(str(tmp_path / "page.png"), str(work / "result"), str(tessdata), str(work)) as safe:
        assert safe.tessdata_dir == "C:\\IO3F2D~1\\TESSDA~1"
        assert safe.cwd == str(work) and safe.output_base == "result"
    assert not (work / "tessdata").exists()                        # No junction was needed.


def test_without_a_short_name_a_junction_in_the_working_folder_is_used_and_removed(windows, monkeypatch, tmp_path):
    tessdata = tmp_path / ARABIC / "tessdata"
    tessdata.mkdir(parents=True)
    (tessdata / "ara.traineddata").write_text("data")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(ascii_paths, "make_junction", lambda target, link: os.symlink(target, link) or True)
    with safe_arguments(str(tmp_path / "page.png"), str(work / "result"), str(tessdata), str(work)) as safe:
        assert safe.tessdata_dir == "tessdata"                     # Relative to the working folder.
        assert (work / "tessdata" / "ara.traineddata").read_text() == "data"
    assert not os.path.lexists(work / "tessdata")                   # Gone after the run...
    assert (tessdata / "ara.traineddata").read_text() == "data"     # ...and what it pointed to is untouched.


def test_the_junction_is_removed_even_when_the_run_fails(windows, monkeypatch, tmp_path):
    tessdata = tmp_path / ARABIC / "tessdata"
    tessdata.mkdir(parents=True)
    (tessdata / "ara.traineddata").write_text("data")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(ascii_paths, "make_junction", lambda target, link: os.symlink(target, link) or True)
    with pytest.raises(RuntimeError):
        with safe_arguments(str(tmp_path / "page.png"), str(work / "result"), str(tessdata), str(work)):
            raise RuntimeError("tesseract failed")
    assert not os.path.lexists(work / "tessdata") and (tessdata / "ara.traineddata").exists()


def test_with_neither_short_name_nor_junction_the_path_is_given_as_it_is(windows, tmp_path):
    tessdata = tmp_path / ARABIC / "tessdata"
    tessdata.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    with safe_arguments(str(tmp_path / "page.png"), str(work / "result"), str(tessdata), str(work)) as safe:
        assert safe.tessdata_dir == str(tessdata)


# -- the program ---------------------------------------------------------------------------------------------

def test_a_program_path_with_arabic_letters_is_started_by_its_short_name(windows, monkeypatch):
    path = "C:\\Users\\%s\\AppData\\Local\\tesseract\\tesseract.exe" % ARABIC
    monkeypatch.setattr(ascii_paths, "short_path", lambda candidate: "C:\\Users\\5C8F~1\\TESSER~1.EXE")
    assert ascii_paths.launchable(path) == "C:\\Users\\5C8F~1\\TESSER~1.EXE"


def test_a_program_path_without_a_short_name_is_used_as_it_is(windows):
    path = "C:\\Users\\%s\\tesseract.exe" % ARABIC
    assert ascii_paths.launchable(path) == path


def test_an_ascii_program_path_is_never_touched(windows, monkeypatch):
    monkeypatch.setattr(ascii_paths, "short_path", lambda path: pytest.fail("no need to ask"))
    assert ascii_paths.launchable("C:\\Program Files\\Tesseract-OCR\\tesseract.exe") == (
        "C:\\Program Files\\Tesseract-OCR\\tesseract.exe")


def test_the_program_that_is_run_is_given_in_its_short_form(monkeypatch, tmp_path):
    exe = tmp_path / ARABIC / "tesseract" / "tesseract.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(program, "is_windows", lambda: True)
    monkeypatch.setattr(program, "bundled_candidates", lambda: [str(exe)])
    monkeypatch.setattr(ascii_paths, "_on_windows", lambda: True)
    monkeypatch.setattr(ascii_paths, "short_path", lambda path: "C:\\SHORT~1\\TESSER~1.EXE")
    assert program.program() == "C:\\SHORT~1\\TESSER~1.EXE"
    assert program.find_tesseract() == str(exe)                    # What is shown and checked is the real path.


# -- the whole run -------------------------------------------------------------------------------------------

@pytest.fixture
def arabic_temp(monkeypatch, tmp_path):
    """TEMP in a folder with Arabic letters, as for a user whose name is in Arabic."""
    folder = tmp_path / ARABIC / "Temp"
    folder.mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


@pytest.fixture
def tesseract_is_installed(monkeypatch):
    """These runs use a stand-in for tesseract.exe, so the machine need not have the real one (the CI runners do not)."""
    monkeypatch.setattr(engine, "is_installed", lambda: True)


def fake_tesseract(seen):
    """Stands in for tesseract.exe: records what it was given, and writes its text file where a relative name says."""
    def run(command, threads, time_limit, cancel_event, cwd=None):
        seen["command"], seen["cwd"] = command, cwd
        base = command[command.index("-l") - 1]
        folder = cwd if cwd and not os.path.isabs(base) else ""
        with open(os.path.join(folder, base + ".txt"), "w", encoding="utf-8") as text_file:
            text_file.write("Hello KaramTC\n")
        return ProcessOutput("", "", 0)
    return run


def test_tesseract_is_never_given_a_non_ascii_character(windows, tesseract_is_installed, arabic_temp, monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(engine, "run_tesseract", fake_tesseract(seen))
    monkeypatch.setattr(ascii_paths, "short_path", lambda path: "C:\\TESSDA~1")
    image = make_picture(tmp_path / ARABIC / "Downloads")

    result = engine.ocr(image, "eng", options=OcrOptions(tessdata_dir=str(tmp_path / ARABIC / "tessdata")))

    assert result.text == "Hello KaramTC"
    assert all(argument.isascii() for argument in seen["command"]), seen["command"]
    assert seen["command"][1:3] == ["input.png", "result"]
    assert seen["command"][seen["command"].index("--tessdata-dir") + 1] == "C:\\TESSDA~1"
    assert seen["cwd"] is not None and seen["cwd"].startswith(str(arabic_temp))     # Started in the working folder.
    assert not list(arabic_temp.iterdir())                                           # Which is removed afterwards.


def test_on_other_systems_the_run_is_as_it_always_was(tesseract_is_installed, monkeypatch, arabic_temp, tmp_path):
    monkeypatch.setattr(ascii_paths, "_on_windows", lambda: False)
    seen = {}

    def run(command, threads, time_limit, cancel_event, cwd=None):
        seen["command"], seen["cwd"] = command, cwd
        with open(command[2] + ".txt", "w", encoding="utf-8") as text_file:
            text_file.write("Hello\n")
        return ProcessOutput("", "", 0)

    monkeypatch.setattr(engine, "run_tesseract", run)
    image = make_picture(tmp_path / ARABIC / "Downloads")
    assert engine.ocr(image, "eng").text == "Hello"
    assert seen["command"][1] == image and seen["cwd"] is None


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_the_real_tesseract_reads_a_picture_whose_folders_have_arabic_letters(windows, arabic_temp, tmp_path):
    """The mechanism itself (a working folder, relative names, the output read back) with a real Tesseract."""
    from PIL import Image, ImageDraw
    from providers.tesseract.languages import available_langs

    if "eng" not in available_langs():
        pytest.skip("English language data is not installed")
    image = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(image).text((30, 60), "HELLO WORLD", fill="black", font_size=60)
    folder = tmp_path / ARABIC / "Downloads"
    folder.mkdir(parents=True)
    path = folder / PICTURE_NAME
    image.save(path)
    assert "HELLO" in engine.ocr(str(path), "eng").text.upper()
