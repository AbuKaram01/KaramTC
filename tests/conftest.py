"""Shared fixtures: a project-root import path, throwaway PDFs and fake OCR providers."""
import os
import sys
import threading
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import winsupport  # noqa: E402 — needs the path set above

# On Windows the tests import GTK without going through main.py, so the runtime that install-windows.ps1
# set up has to be made findable here too. Does nothing on other systems, or where no runtime is installed.
winsupport.prepare_runtime()

LONG_TEXT = ("The quick brown fox jumps over the lazy dog while the committee reviews "
             "the quarterly report and every member checks the figures. ") * 3


@pytest.fixture(autouse=True)
def empty_data_folder(monkeypatch, tmp_path_factory):
    """Every test starts with an empty application data folder.

    On Windows KaramTC's own tesseract.exe, the one install-windows.ps1 unpacks into the data folder, is found before
    anything else. On a machine where it is installed (the windows-full-install job) that real copy would leak into every
    test that asks which program runs. A test that needs a copy sets its own XDG_DATA_HOME, as the tests of
    providers.tesseract.program do."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path_factory.getbasetemp() / "empty-data-home"))


@pytest.fixture
def make_pdf(tmp_path):
    """make_pdf(pages) -> path. *pages* is a string per page: "text" (native
    text) or "scan" (an image only, which needs OCR)."""
    fitz = pytest.importorskip("pymupdf", reason="PyMuPDF is required for the PDF pipeline tests")

    def build(pages, name="book.pdf"):
        document = fitz.open()
        for number, kind in enumerate(pages, 1):
            page = document.new_page()
            if kind == "text":
                page.insert_textbox(fitz.Rect(50, 60, 545, 780), f"Page {number}. {LONG_TEXT}", fontsize=11)
            else:
                pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 100), False)
                pixmap.clear_with(255)
                page.insert_image(fitz.Rect(40, 60, 300, 190), pixmap=pixmap)
        path = tmp_path / name
        document.save(path)
        document.close()
        return str(path)
    return build


@pytest.fixture
def register_provider(monkeypatch):
    """register_provider(name, ocr_function): makes `providers.<name>` resolvable."""
    def register(name, function):
        module = types.ModuleType(f"providers.{name}")
        module.ocr = function
        monkeypatch.setitem(sys.modules, f"providers.{name}", module)
    return register


@pytest.fixture
def cancel_event():
    return threading.Event()
