# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Main application window: header, tabs, and what spans them.

The tabs themselves live in ui/pdf_tab, ui/image_tab and ui/media_tab. The window only wires them together: the
toast overlay, the OCR and Speech Settings entry points, the guard against quitting mid-job, and remembering
where the user left off (size, maximized state, last tab).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

import settings as app_settings
from config import APP_NAME
from providers.tesseract import is_installed
from ui import dialogs, saved_settings
from ui.image_tab import ImageTab
from ui.install_warning import build_install_warning_page
from ui.media_tab import MediaTab
from ui.ocr_settings import present_ocr_settings
from ui.pdf_tab import PdfTab
from ui.speech_settings import present_speech_settings

# Tab identifiers: names of the pages in the tab stack and values stored as the "last tab" setting.
_TAB_PDF, _TAB_IMAGE, _TAB_MEDIA = "pdf", "image", "media"
# (tab id, header icon, header label), in display order. The first tab is the default.
_TABS = [
    (_TAB_PDF, "x-office-document-symbolic", "PDF"),
    (_TAB_IMAGE, "image-x-generic-symbolic", "Image"),
    (_TAB_MEDIA, "audio-x-generic-symbolic", "Audio/Video"),
]
# The tabs that need Tesseract. The Audio/Video tab does not.
_OCR_TABS = (_TAB_PDF, _TAB_IMAGE)
# Pages of the root stack: the tabs, or the install-Tesseract warning shown in their place.
_CONTENT_TABS, _CONTENT_WARNING = "tabs", "warning"
# Resizing fires many times a second; the window state is written once it settles.
_STATE_SAVE_DELAY_MS = 400

# Bodies of the "Extraction still running" dialog, one per kind of job that quitting would interrupt.
_PDF_RUNNING_BODY = (
    "A PDF extraction is still running. Progress is saved as it "
    "goes, so you can resume from where it left off next time you "
    "open this file \u2014 but quitting now stops it partway."
)
_IMAGE_RUNNING_BODY = (
    "An image is still being processed. Quitting now discards "
    "that result \u2014 it hasn't been saved anywhere yet."
)
_MEDIA_RUNNING_BODY = (
    "A recording is still being transcribed. Quitting now stops it "
    "partway \u2014 turn on \u201cContinue interrupted transcriptions\u201d in "
    "Speech Settings to pick it up again next time."
)


class OcrWindow(Adw.ApplicationWindow):
    """The application window: a header with the tab switcher and main menu above the PDF, Image and Audio/Video tabs.

    On start-up the window restores its saved size, maximized state and last tab. It locks the Settings entry
    points while a job is running and asks for confirmation before quitting in the middle of one.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(APP_NAME)
        self._state_save_id = 0
        self.set_default_size(*self._size_that_fits_the_screen(*saved_settings.window_size()))
        self.set_size_request(*saved_settings.WINDOW_MIN_SIZE)
        if saved_settings.window_maximized():
            self.maximize()

        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)
        toolbar_view = Adw.ToolbarView()
        self._toast_overlay.set_child(toolbar_view)
        toolbar_view.add_top_bar(self._build_header())

        # Root content: either the install-Tesseract warning or the tabs.
        self._content_stack = Gtk.Stack()
        self._content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        toolbar_view.set_content(self._content_stack)
        self._content_stack.add_named(build_install_warning_page(), _CONTENT_WARNING)
        self._content_stack.add_named(self._build_tabs(), _CONTENT_TABS)

        self.connect("close-request", self._on_close_request)
        self._tesseract_installed = is_installed()
        self._select_tab(self._remembered_tab(), remember=False)
        # Connected last, so restoring the window above doesn't count as the user changing it.
        for signal in ("notify::default-width", "notify::default-height", "notify::maximized"):
            self.connect(signal, self._on_window_state_changed)

    def show_toast(self, message: str) -> None:
        """Show *message* as a toast over the window content."""
        dialogs.show_toast(self._toast_overlay, message)

    # --- Construction ---

    def _build_header(self) -> Adw.HeaderBar:
        header = Adw.HeaderBar()
        header.set_title_widget(self._build_tab_switcher())
        # OCR Settings are app-wide (shared by both OCR tabs), so they live in the main menu, reachable before any
        # file is chosen, and, as a shortcut, in each tab's language row. Ctrl+, is bound in ui/app.py.
        self._settings_action = Gio.SimpleAction.new("ocr-settings", None)
        self._settings_action.connect("activate", self._on_open_ocr_settings)
        self.add_action(self._settings_action)
        self._speech_action = Gio.SimpleAction.new("speech-settings", None)
        self._speech_action.connect("activate", self._on_open_speech_settings)
        self.add_action(self._speech_action)
        header.pack_end(self._build_main_menu())
        return header

    @staticmethod
    def _build_main_menu() -> Gtk.MenuButton:
        menu = Gio.Menu()
        settings_section = Gio.Menu()
        settings_section.append("OCR Settings", "win.ocr-settings")
        settings_section.append("Speech Settings", "win.speech-settings")
        menu.append_section(None, settings_section)
        about_section = Gio.Menu()
        about_section.append("About", "app.about")
        menu.append_section(None, about_section)

        button = Gtk.MenuButton()
        button.set_icon_name("open-menu-symbolic")
        button.set_menu_model(menu)
        button.set_tooltip_text("Main menu")
        return button

    def _build_tab_switcher(self) -> Gtk.Box:
        """Build the linked tab buttons that take the place of the title in the header."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.add_css_class("linked")
        box.set_halign(Gtk.Align.CENTER)
        self._tab_buttons = {tab: self._tab_button(icon, label, tab) for tab, icon, label in _TABS}
        self._current_tab = _TAB_PDF
        self._tab_buttons[_TAB_PDF].set_active(True)  # PDF is the first (default) tab.
        for button in self._tab_buttons.values():
            box.append(button)
        return box

    def _tab_button(self, icon_name: str, label: str, tab: str) -> Gtk.ToggleButton:
        content = Adw.ButtonContent()
        content.set_icon_name(icon_name)
        content.set_label(label)
        button = Gtk.ToggleButton()
        button.set_child(content)
        button.connect("clicked", lambda *_: self._select_tab(tab))
        return button

    def _build_tabs(self) -> Gtk.Stack:
        self._tab_stack = Gtk.Stack()
        self._tab_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._pdf_tab = PdfTab(
            on_settings_changed=self._on_ocr_settings_changed,
            on_running_changed=self._update_settings_access,
        )
        self._image_tab = ImageTab(
            on_open_settings=self._on_open_ocr_settings,
            on_busy_changed=self._update_settings_access,
            show_toast=self.show_toast,
        )
        self._media_tab = MediaTab(
            on_running_changed=self._update_settings_access,
            on_open_speech_settings=self._on_open_speech_settings,
        )
        self._tab_stack.add_named(self._pdf_tab, _TAB_PDF)
        self._tab_stack.add_named(self._image_tab, _TAB_IMAGE)
        self._tab_stack.add_named(self._media_tab, _TAB_MEDIA)
        self._tab_stack.set_visible_child_name(_TAB_PDF)
        return self._tab_stack

    def _select_tab(self, tab: str, remember: bool = True) -> None:
        self._current_tab = tab
        if remember:
            self._remember(saved_settings.LAST_TAB, tab)
        for name, button in self._tab_buttons.items():
            button.set_active(name == tab)
        self._tab_stack.set_visible_child_name(tab)
        self._update_content()

    def _update_content(self) -> None:
        """Show the install-Tesseract page instead of an OCR tab when Tesseract is missing.

        The Audio/Video tab does not need Tesseract and is always shown.
        """
        needs_tesseract = self._current_tab in _OCR_TABS and not self._tesseract_installed
        self._content_stack.set_visible_child_name(_CONTENT_WARNING if needs_tesseract else _CONTENT_TABS)

    # --- Remembering where the user left off ---

    @staticmethod
    def _remember(key: str, value) -> None:
        """Save *value* under *key* unless it is already what is saved.

        Without the check, resizing the window would rewrite the settings file endlessly.
        """
        if app_settings.get(key, None) != value:
            app_settings.set(key, value)

    def _remembered_tab(self) -> str:
        saved = app_settings.get(saved_settings.LAST_TAB, _TAB_PDF)
        return saved if saved in self._tab_buttons else _TAB_PDF

    @staticmethod
    def _size_that_fits_the_screen(width: int, height: int) -> tuple[int, int]:
        """Return the saved size, cut down to the biggest screen there is now.

        A size saved on a bigger screen (or on a monitor that is no longer connected) would otherwise make the
        window open larger than anything it could be shown on.
        """
        display = Gdk.Display.get_default()
        monitors = display.get_monitors() if display is not None else None
        areas = (
            [monitors.get_item(index).get_geometry() for index in range(monitors.get_n_items())]
            if monitors is not None else []
        )
        if not areas:
            return width, height
        min_width, min_height = saved_settings.WINDOW_MIN_SIZE
        return (
            max(min_width, min(width, max(area.width for area in areas))),
            max(min_height, min(height, max(area.height for area in areas))),
        )

    def _on_window_state_changed(self, *_) -> None:
        if self._state_save_id:
            GLib.source_remove(self._state_save_id)
        self._state_save_id = GLib.timeout_add(_STATE_SAVE_DELAY_MS, self._save_window_state_when_settled)

    def _save_window_state_when_settled(self) -> bool:
        self._state_save_id = 0
        self.save_window_state()
        return GLib.SOURCE_REMOVE

    def save_window_state(self) -> None:
        """Save the maximized state and the size for the next launch.

        While the window is maximized (or fullscreen) the saved size is left alone: it is the normal size that
        un-maximizing goes back to.
        """
        if self._state_save_id:
            GLib.source_remove(self._state_save_id)
            self._state_save_id = 0
        maximized = self.is_maximized()
        self._remember(saved_settings.WINDOW_MAXIMIZED, maximized)
        if maximized or self.is_fullscreen():
            return
        width, height = self.get_default_size()
        if width > 0 and height > 0:
            self._remember(saved_settings.WINDOW_WIDTH, width)
            self._remember(saved_settings.WINDOW_HEIGHT, height)

    # --- OCR Settings ---

    def _is_ocr_busy(self) -> bool:
        return self._image_tab.is_busy() or self._pdf_tab.is_running()

    def _on_open_ocr_settings(self, *_) -> None:
        if self._is_ocr_busy():
            self.show_toast("OCR Settings are locked while an extraction is running")
            return
        present_ocr_settings(self, on_changed=self._on_ocr_settings_changed)

    def _update_settings_access(self) -> None:
        """Lock the Settings entry points while a job is running.

        The OCR Settings entry points (menu item, Ctrl+, and both gear buttons) are locked while an extraction is
        running in either OCR tab, and Speech Settings while a recording is being transcribed. Deleting a language
        or model, or switching the source, under a running job could make it fail.
        """
        enabled = not self._is_ocr_busy()
        self._settings_action.set_enabled(enabled)
        self._image_tab.set_settings_enabled(enabled)
        self._pdf_tab.set_settings_enabled(enabled)
        self._speech_action.set_enabled(not self._media_tab.is_running())

    def _on_ocr_settings_changed(self) -> None:
        """Refresh the language rows of both OCR tabs after the language source or the downloaded languages changed."""
        self._image_tab.refresh_languages()
        self._pdf_tab.refresh_languages()

    # --- Speech Settings ---

    def _on_open_speech_settings(self, *_) -> None:
        if self._media_tab.is_running():
            self.show_toast("Speech Settings are locked while a transcription is running")
            return
        present_speech_settings(self, on_changed=self._media_tab.refresh)

    # --- Quitting ---

    def _on_close_request(self, *_) -> bool:
        """Warn before quitting mid-extraction.

        Closing abruptly would otherwise give no hint that an image result would be lost, or that a book is about
        to stop partway (and why the next launch shows a "resume" banner).
        """
        self.save_window_state()
        body = self._running_job_description()
        if body is None:
            return False  # Nothing running: let the window close normally.

        dialogs.confirm(
            self, "Extraction still running", body,
            accept_id="quit", accept_label="Quit anyway", on_accept=self._quit,
            cancel_label="Keep working",
        )
        return True  # Block the close until the dialog is answered.

    def _running_job_description(self) -> str | None:
        """Return what to tell the user about the job that quitting would interrupt, or None if there is none."""
        if self._pdf_tab.is_running():
            return _PDF_RUNNING_BODY
        if self._media_tab.is_running():
            return _MEDIA_RUNNING_BODY
        if self._image_tab.is_busy():
            return _IMAGE_RUNNING_BODY
        return None

    def _quit(self) -> None:
        app = self.get_application()
        if app is not None:
            app.quit()
        else:
            self.destroy()
