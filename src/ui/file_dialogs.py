# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Open, save and choose-folder dialogs that hand back a local path.

The dialogs wrap Gtk.FileDialog. A cancelled dialog is ignored silently. The application works with local file
paths only, so a file that has no local path (for example one on a remote GVfs mount) is reported through the
optional *on_not_local* callback instead of being passed on.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk


def make_filter(name: str, mime_types=(), patterns=(), suffixes=()) -> Gtk.FileFilter:
    """Build a file-dialog filter matching any of *mime_types*, *patterns* or *suffixes*.

    *suffixes* (".png" or "png") match by extension whatever its case, and without needing the system to know the
    file type: on Windows a content type exists only for the extensions that are registered there, so a MIME-type
    filter alone can hide files the application opens perfectly well.
    """
    file_filter = Gtk.FileFilter()
    file_filter.set_name(name)
    for mime_type in mime_types:
        file_filter.add_mime_type(mime_type)
    for pattern in patterns:
        file_filter.add_pattern(pattern)
    for suffix in suffixes:
        # Gtk.FileFilter.add_suffix() always matches case-insensitively.
        file_filter.add_suffix(suffix.lstrip("."))
    return file_filter


def _filter_list(filters) -> Gio.ListStore:
    store = Gio.ListStore.new(Gtk.FileFilter)
    for file_filter in filters:
        store.append(file_filter)
    return store


def _local_path_or_report(gfile, on_not_local) -> str | None:
    """Return the local path of *gfile*; call *on_not_local* (if given) when it has none."""
    path = gfile.get_path() if gfile else None
    if gfile and not path and on_not_local:
        on_not_local()
    return path


def open_file(parent, title: str, filters: list[Gtk.FileFilter], on_path, on_not_local=None) -> None:
    """Ask for an existing file and call ``on_path(path)`` with its local path.

    The first filter in *filters* is the default one. *on_not_local* is called, without arguments, when the chosen
    file has no local path.
    """
    dialog = Gtk.FileDialog()
    dialog.set_title(title)
    dialog.set_filters(_filter_list(filters))
    dialog.set_default_filter(filters[0])

    def finished(source, result):
        try:
            gfile = source.open_finish(result)
        except GLib.Error:
            return
        path = _local_path_or_report(gfile, on_not_local)
        if path:
            on_path(path)

    dialog.open(parent, None, finished)


def choose_folder(parent, title: str, initial_folder: str | None, on_path) -> None:
    """Ask for a folder and call ``on_path(path)`` with its local path, starting in *initial_folder* if given."""
    dialog = Gtk.FileDialog()
    dialog.set_title(title)
    if initial_folder:
        dialog.set_initial_folder(Gio.File.new_for_path(initial_folder))

    def finished(source, result):
        try:
            gfile = source.select_folder_finish(result)
        except GLib.Error:
            return
        if gfile and gfile.get_path():
            on_path(gfile.get_path())

    dialog.select_folder(parent, None, finished)


def save_file(
    parent, title: str, initial_name: str | None, file_filter: Gtk.FileFilter, on_path, *, on_not_local=None,
) -> None:
    """Ask where to save a file and call ``on_path(path)`` with the chosen local path.

    *initial_name* pre-fills the file name; *on_not_local* is called, without arguments, when the chosen location
    has no local path.
    """
    dialog = Gtk.FileDialog()
    dialog.set_title(title)
    if initial_name:
        dialog.set_initial_name(initial_name)
    dialog.set_filters(_filter_list([file_filter]))

    def finished(source, result):
        try:
            gfile = source.save_finish(result)
        except GLib.Error:
            return
        path = _local_path_or_report(gfile, on_not_local)
        if path:
            on_path(path)

    dialog.save(parent, None, finished)
