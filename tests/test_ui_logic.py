"""UI logic that needs the GTK bindings only to be imported (no display)."""
import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # noqa: F401
except (ValueError, ImportError):
    pytest.skip("GTK 4 / libadwaita typelibs are not installed", allow_module_level=True)

from core.book import IMAGE_MODES, OUTPUT_BOTH, OUTPUT_PDF, OUTPUT_TXT, BookResult
from ui.pdf_tab.done_view import describe_result
from ui.pdf_tab.options import IMAGE_MODE_CHOICES, OUTPUT_FORMAT_CHOICES
from ui.pdf_tab.source_rows import pages_summary
from ui.ocr_settings.groups import describe_cpu_usage


def test_every_core_choice_has_a_ui_label():
    assert [choice.id for choice in IMAGE_MODE_CHOICES] == list(IMAGE_MODES)
    assert {choice.id for choice in OUTPUT_FORMAT_CHOICES} == {OUTPUT_TXT, OUTPUT_PDF, OUTPUT_BOTH}


def test_pages_summary_wording():
    assert pages_summary(None, 0) == ""
    assert pages_summary(10, 0) == "All 10 pages"
    assert pages_summary(10, 3) == "7 of 10 pages \u2014 3 excluded"


def test_result_description_reports_ocr_failures_and_outputs():
    result = BookResult(
        txt_path="/b/a.txt", pdf_path="/b/a.pdf", total_pages=20, ocr_pages=5, avg_confidence=91.4,
        low_text_pages=2, failed_pages={7: "boom", 9: "bang"},
    )
    text = describe_result(result)
    assert "Extracted 20 pages" in text and "5 of them via OCR (avg. OCR confidence 91%)" in text
    assert "2 page(s) had little or no native text" in text
    assert "2 page(s) could not be read" in text and "7, 9" in text
    assert "/b/a.txt\n/b/a.pdf" in text


def test_long_failure_lists_are_abbreviated():
    result = BookResult(None, "/b/a.pdf", 50, 50, None, failed_pages=dict.fromkeys(range(1, 31), "x"))
    assert "and 18 more" in describe_result(result)


def test_cpu_usage_descriptions_match_the_machine():
    assert "1 core" in describe_cpu_usage("low", 8)
    assert describe_cpu_usage("balanced", 8) == "4 of your 8 cores"
    assert "All 1 core" in describe_cpu_usage("max", 1)


def test_job_setup_reports_what_blocks_a_start(monkeypatch):
    from ui.pdf_tab import job_setup
    monkeypatch.setattr(job_setup, "is_installed", lambda: False)
    assert "not installed" in job_setup.problem_blocking_start("auto", True, 10, 0)
    assert job_setup.problem_blocking_start("off", False, 10, 0) is None        # native text only needs neither
    monkeypatch.setattr(job_setup, "is_installed", lambda: True)
    assert "No OCR language" in job_setup.problem_blocking_start("on", False, 10, 0)
    assert "All pages are excluded" in job_setup.problem_blocking_start("auto", True, 10, 10)
    assert job_setup.problem_blocking_start("auto", True, 10, 9) is None


def test_job_setup_lists_only_the_outputs_a_new_run_would_overwrite(tmp_path):
    from ui.pdf_tab import job_setup
    pdf = str(tmp_path / "book.pdf")
    (tmp_path / "book.txt").write_text("old")
    (tmp_path / "book_searchable.pdf").write_text("old")
    assert job_setup.existing_outputs(pdf, None, OUTPUT_TXT) == ["book.txt"]
    assert job_setup.existing_outputs(pdf, None, OUTPUT_PDF) == ["book_searchable.pdf"]
    assert job_setup.existing_outputs(pdf, None, OUTPUT_BOTH) == ["book.txt", "book_searchable.pdf"]
    assert job_setup.existing_outputs(pdf, str(tmp_path / "elsewhere"), OUTPUT_BOTH) == []


def test_job_setup_checks_that_the_output_folder_can_be_written(tmp_path):
    from ui.pdf_tab import job_setup
    assert job_setup.output_folder_is_usable(str(tmp_path / "new" / "folder"))
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert not job_setup.output_folder_is_usable(str(blocker / "sub"))
