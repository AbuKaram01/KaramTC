import os
import subprocess

import pytest

from providers import tessdata_manager
from providers.ocr_types import OcrOptions, OcrPageError
from providers.tesseract import (
    DEFAULT_LANG, LANG_COMBOS, LANG_NAMES, PSM_OPTIONS, build_lang_options, lang_display_name,
    normalize_oem, normalize_psm, psm_index, threads_for_usage,
)
from providers.tesseract.command import build_command, parse_custom_params
from providers.tesseract.failures import raise_for_failure
from providers.tesseract.install import install_hint
from providers.tesseract.output import parse_mean_confidence
from providers.tesseract.process import ProcessOutput


def test_removed_page_segmentation_modes_fall_back_to_the_default():
    assert normalize_psm(0) == normalize_psm(2) == 3
    assert normalize_psm("6") == 6
    assert PSM_OPTIONS[psm_index(0)][0] == 3
    assert normalize_oem(9) == 3


def test_cpu_threads_follow_the_usage_choice():
    assert threads_for_usage("low", 8) == 1
    assert threads_for_usage("balanced", 8) == 4
    assert threads_for_usage("max", 8) == 8
    assert threads_for_usage("auto", 8) is None          # 4+ cores: leave Tesseract alone
    assert threads_for_usage("auto", 2) == 2             # fewer cores: never oversubscribe


def test_language_names_cover_the_combos_and_compound_codes():
    assert lang_display_name("ara+eng") == "Arabic + English"
    assert lang_display_name("zzz") == "zzz"
    assert all(part in LANG_NAMES for code, _name in LANG_COMBOS for part in code.split("+"))
    assert DEFAULT_LANG in dict(LANG_COMBOS)


def test_language_options_offer_combinations_only_when_every_pack_is_installed():
    codes = [code for code, _name in build_lang_options(["ara", "eng", "fra"])]
    assert codes[0] == "ara+eng" and "fra" in codes and codes.count("ara") == 1
    assert "ara+eng" not in [code for code, _name in build_lang_options(["ara"])]


def test_custom_parameters_are_parsed_leniently():
    assert parse_custom_params("a=1; b = 2\nc=3;;bad; =x") == [("a", "1"), ("b", "2"), ("c", "3")]


def test_command_line_has_custom_parameters_last_so_they_win():
    options = OcrOptions(want_pdf=True, chop_enable=True, custom_params="chop_enable=0", threads=2)
    command = build_command("in.png", "out", "eng", 6, options)
    assert command[:3] == ["tesseract", "in.png", "out"] and command[3:7] == ["-l", "eng", "--psm", "6"]
    assert "tessedit_create_pdf=1" in command and "tessedit_create_tsv=1" in command
    assert command[-1] == "chop_enable=0" and command.index("chop_enable=1") < command.index("chop_enable=0")


def test_mean_confidence_ignores_structural_rows(tmp_path):
    tsv = tmp_path / "r.tsv"
    tsv.write_text("level\tconf\ttext\n1\t-1\t\n5\t90\ta\n5\t70\tb\n")
    assert parse_mean_confidence(str(tsv)) == 80.0
    assert parse_mean_confidence(str(tmp_path / "missing.tsv")) is None


def test_failures_are_split_into_setup_problems_and_page_problems():
    with pytest.raises(OcrPageError):
        raise_for_failure(ProcessOutput("", "Segmentation fault", 139), psm=3, lang="eng", tessdata_dir=None)
    with pytest.raises(RuntimeError, match="language pack 'xyz'") as setup:
        raise_for_failure(ProcessOutput("", "Failed loading language 'xyz'", 1), psm=3, lang="xyz", tessdata_dir=None)
    assert not isinstance(setup.value, OcrPageError)
    with pytest.raises(RuntimeError, match="osd"):
        raise_for_failure(ProcessOutput("", "Failed loading language 'osd'", 0), psm=1, lang="eng", tessdata_dir=None)
    raise_for_failure(ProcessOutput("", "warning only", 0), psm=3, lang="eng", tessdata_dir=None)


def test_install_hint_uses_the_detected_package_manager(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name if name == "dnf" else None)
    assert install_hint("ara") == "Run: sudo dnf install tesseract-langpack-ara"
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert "package manager" in install_hint()


def test_tessdata_codes_are_validated_before_touching_the_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(tessdata_manager, "_data_root", lambda: str(tmp_path))
    assert tessdata_manager.list_downloaded("fast") == []
    tessdata_manager.delete("fast", "../../etc/passwd")          # must be a harmless no-op
    with pytest.raises(ValueError):
        tessdata_manager.local_tessdata_dir("bogus")
    (tmp_path / "fast").mkdir(exist_ok=True)
    (tmp_path / "fast" / "ara.traineddata").write_bytes(b"x" * 30_000)
    assert tessdata_manager.list_downloaded("fast") == ["ara"]


@pytest.mark.skipif(not os.path.exists("/usr/bin/tesseract"), reason="Tesseract is not installed")
def test_a_real_tesseract_run_reads_text(tmp_path):
    from PIL import Image, ImageDraw
    from providers.tesseract import ocr
    image = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(image).text((30, 60), "HELLO WORLD", fill="black", font_size=60)
    path = tmp_path / "t.png"
    image.save(path)
    assert "HELLO" in ocr(str(path), "eng").text.upper()
    assert subprocess.run(["tesseract", "--version"], capture_output=True, check=False).returncode == 0
