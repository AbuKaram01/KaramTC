"""The app reopens the way it was left: window size, maximized state and the last tab.

The first group only reads the saved settings. The second builds the real main window, so it
needs GTK 4, libadwaita and a display (run it with `xvfb-run -a pytest` on a headless machine)
and is skipped without them.
"""
import time

import pytest

import settings
from ui import saved_settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_config_dir", lambda: str(tmp_path / "cfg"))
    settings._unsaved.clear()
    yield
    settings._unsaved.clear()


# ── Reading the saved values ────────────────────────────────────────

def test_a_first_launch_uses_the_default_window():
    assert saved_settings.window_size() == saved_settings.WINDOW_DEFAULT_SIZE == (700, 620)
    assert saved_settings.window_maximized() is False


def test_a_saved_window_size_is_used():
    settings.set(saved_settings.WINDOW_WIDTH, 1000)
    settings.set(saved_settings.WINDOW_HEIGHT, 750)
    assert saved_settings.window_size() == (1000, 750)


@pytest.mark.parametrize("width, height, expected", [
    (10, 10, saved_settings.WINDOW_MIN_SIZE),                         # smaller than the window can be
    (10**9, 10**9, saved_settings.WINDOW_MAX_SIZE),                   # absurdly big
    (-5, 0, saved_settings.WINDOW_MIN_SIZE),
    ("wide", None, saved_settings.WINDOW_DEFAULT_SIZE),               # wrong types: back to the default
    ([800], {"h": 1}, saved_settings.WINDOW_DEFAULT_SIZE),
])
def test_a_damaged_window_size_is_kept_within_sensible_limits(width, height, expected):
    settings.set(saved_settings.WINDOW_WIDTH, width)
    settings.set(saved_settings.WINDOW_HEIGHT, height)
    assert saved_settings.window_size() == expected


def test_only_a_real_true_counts_as_maximized():
    settings.set(saved_settings.WINDOW_MAXIMIZED, True)
    assert saved_settings.window_maximized() is True
    settings.set(saved_settings.WINDOW_MAXIMIZED, "yes")
    assert saved_settings.window_maximized() is False


# ── The real window ─────────────────────────────────────────────────

@pytest.fixture
def make_window():
    gi = pytest.importorskip("gi", reason="the window tests need PyGObject")
    try:
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, GLib
    except (ValueError, ImportError, RuntimeError):
        pytest.skip("GTK 4 or libadwaita is not available")
    if Gdk.Display.get_default() is None:              # GTK found no display to open
        pytest.skip("no display available")
    Adw.init()
    from ui.main_window import OcrWindow

    windows = []

    def build():
        window = OcrWindow()
        windows.append(window)
        return window

    yield build
    for window in windows:
        if window._state_save_id:
            GLib.source_remove(window._state_save_id)
        window.destroy()


def pump(condition, timeout=3.0):
    """Runs the GTK main loop until *condition()* holds; True if it did."""
    from gi.repository import GLib
    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        GLib.MainContext.default().iteration(False)
        time.sleep(0.01)
    return condition()


def test_a_first_launch_opens_the_default_window_on_the_pdf_tab(make_window):
    window = make_window()
    assert window.get_default_size() == (700, 620)
    assert window._current_tab == "pdf" and window._tab_stack.get_visible_child_name() == "pdf"


def test_the_window_reopens_with_the_saved_size_and_tab(make_window):
    settings.set(saved_settings.WINDOW_WIDTH, 900)
    settings.set(saved_settings.WINDOW_HEIGHT, 650)
    settings.set(saved_settings.LAST_TAB, "media")
    window = make_window()
    assert window.get_default_size() == (900, 650)
    assert window._current_tab == "media" and window._tab_stack.get_visible_child_name() == "media"
    assert [name for name, button in window._tab_buttons.items() if button.get_active()] == ["media"]


def test_opening_the_window_does_not_count_as_the_user_changing_it(make_window):
    make_window()
    for key in (saved_settings.WINDOW_WIDTH, saved_settings.WINDOW_HEIGHT,
                saved_settings.WINDOW_MAXIMIZED, saved_settings.LAST_TAB):
        assert settings.get(key, None) is None


@pytest.mark.parametrize("damaged", ["", "../../x", "PDF", 3, None])
def test_an_unknown_saved_tab_opens_the_pdf_tab(make_window, damaged):
    settings.set(saved_settings.LAST_TAB, damaged)
    assert make_window()._current_tab == "pdf"


def test_a_size_saved_on_a_bigger_screen_is_cut_down_to_the_screen(make_window):
    from gi.repository import Gdk
    settings.set(saved_settings.WINDOW_WIDTH, 16000)
    settings.set(saved_settings.WINDOW_HEIGHT, 16000)
    monitors = Gdk.Display.get_default().get_monitors()
    areas = [monitors.get_item(index).get_geometry() for index in range(monitors.get_n_items())]
    width, height = make_window().get_default_size()
    assert width <= max(area.width for area in areas) and height <= max(area.height for area in areas)


def test_choosing_a_tab_remembers_it(make_window):
    window = make_window()
    window._select_tab("image")
    assert settings.get(saved_settings.LAST_TAB, "") == "image"
    assert make_window()._current_tab == "image"


def test_the_window_size_is_saved_once_resizing_settles(make_window):
    window = make_window()
    window.set_default_size(830, 650)
    assert pump(lambda: settings.get(saved_settings.WINDOW_WIDTH, 0) == 830)
    assert saved_settings.window_size() == (830, 650)


def test_closing_the_window_saves_it_at_once(make_window):
    window = make_window()
    window.set_default_size(840, 660)
    window.emit("close-request")                      # no waiting for the settle delay
    assert saved_settings.window_size() == (840, 660)


def test_a_maximized_window_keeps_the_normal_size_saved(make_window):
    window = make_window()
    window.set_default_size(820, 640)
    window.save_window_state()
    window.is_maximized = lambda: True                # what the window manager would report
    window.set_default_size(1500, 900)
    window.save_window_state()
    assert saved_settings.window_maximized() is True
    assert saved_settings.window_size() == (820, 640)  # un-maximizing goes back to this

    window.is_maximized = lambda: False
    window.save_window_state()
    assert saved_settings.window_maximized() is False


def test_a_window_saved_as_maximized_opens_maximized(make_window, monkeypatch):
    from ui.main_window import OcrWindow
    calls = []
    monkeypatch.setattr(OcrWindow, "maximize", lambda self: calls.append("maximize"))
    make_window()
    assert calls == []
    settings.set(saved_settings.WINDOW_MAXIMIZED, True)
    make_window()
    assert calls == ["maximize"]
