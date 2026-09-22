# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/widgets.py — Small widget factories shared by every screen.

Each one captures a widget recipe the app repeats (a flat button in a row, a
switch row, a scrolled clamp…), so screens read as layout, not as property
setting.
"""
from __future__ import annotations

import contextlib

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk


def labeled_button(label: str, icon_name: str) -> Gtk.Button:
    """
    A button showing an icon AND its text.

    Don't build these with Gtk.Button(label=...) followed by set_icon_name():
    GTK replaces the button's child with the icon, silently dropping the
    label, so the button ends up icon-only and users can't tell similar
    icons apart (e.g. "Open text file" vs. "Open folder").
    """
    button = Gtk.Button()
    button.set_child(Adw.ButtonContent(label=label, icon_name=icon_name))
    return button


def set_button_text(button: Gtk.Button, text: str) -> None:
    """Changes the text of a labeled_button() while keeping its icon."""
    content = button.get_child()
    if isinstance(content, Adw.ButtonContent):
        content.set_label(text)
    else:
        button.set_label(text)


def pill_button(
    label: str, icon_name: str, on_click=None, suggested: bool = False, tooltip: str | None = None,
) -> Gtk.Button:
    button = labeled_button(label, icon_name)
    button.add_css_class("pill")
    if suggested:
        button.add_css_class("suggested-action")
    if tooltip:
        button.set_tooltip_text(tooltip)
    if on_click:
        button.connect("clicked", on_click)
    return button


def flat_text_button(label: str, on_click=None) -> Gtk.Button:
    """A flat text button, vertically centred — for the suffix of a row."""
    button = Gtk.Button(label=label)
    button.add_css_class("flat")
    button.set_valign(Gtk.Align.CENTER)
    if on_click:
        button.connect("clicked", on_click)
    return button


def flat_icon_button(
    icon_name: str, tooltip: str | None = None, on_click=None, centered: bool = True,
) -> Gtk.Button:
    button = Gtk.Button()
    button.set_icon_name(icon_name)
    button.add_css_class("flat")
    if centered:
        button.set_valign(Gtk.Align.CENTER)
    if tooltip:
        button.set_tooltip_text(tooltip)
    if on_click:
        button.connect("clicked", on_click)
    return button


def make_icon_prefix(icon_name: str) -> Gtk.Image:
    """Creates a 16px icon suitable for use as a prefix in Adw rows."""
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(16)
    return image


def switch_row(title: str, active: bool, on_toggled=None, subtitle: str | None = None):
    """An ActionRow with a switch; returns (row, switch). *on_toggled* is
    connected after the initial state is set, so it doesn't fire for it."""
    switch = Gtk.Switch()
    switch.set_active(active)
    switch.set_valign(Gtk.Align.CENTER)
    if on_toggled:
        switch.connect("notify::active", on_toggled)
    row = Adw.ActionRow(title=title, subtitle=subtitle) if subtitle else Adw.ActionRow(title=title)
    row.add_suffix(switch)
    row.set_activatable_widget(switch)
    return row, switch


def string_list(labels) -> Gtk.StringList:
    strings = Gtk.StringList()
    for label in labels:
        strings.append(label)
    return strings


def dim_label(text: str = "", caption: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.add_css_class("dim-label")
    if caption:
        label.add_css_class("caption")
    return label


def status_page(icon_name: str, title: str, description: str | None = None) -> Adw.StatusPage:
    page = Adw.StatusPage()
    page.set_icon_name(icon_name)
    page.set_title(title)
    if description:
        page.set_description(description)
    return page


def scrolled_clamp(
    maximum_size: int,
    tightening_threshold: int,
    *,
    margin_top: int = 24,
    margin_bottom: int = 24,
    margin_start: int = 12,
    margin_end: int = 12,
) -> tuple[Gtk.ScrolledWindow, Adw.Clamp]:
    """A vertically scrolling page whose content is centred and width-limited."""
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)

    clamp = Adw.Clamp(maximum_size=maximum_size, tightening_threshold=tightening_threshold)
    clamp.set_margin_top(margin_top)
    clamp.set_margin_bottom(margin_bottom)
    clamp.set_margin_start(margin_start)
    clamp.set_margin_end(margin_end)
    scroll.set_child(clamp)
    return scroll, clamp


def centered_row(*children: Gtk.Widget) -> Gtk.Box:
    """A horizontally centred row of widgets."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_halign(Gtk.Align.CENTER)
    for child in children:
        box.append(child)
    return box


def add_file_drop_target(widget: Gtk.Widget, on_drop) -> None:
    """Lets files be dropped on *widget*; on_drop(target, value, x, y) -> bool."""
    target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
    target.connect("drop", on_drop)
    widget.add_controller(target)


def clear_children(box: Gtk.Box) -> None:
    child = box.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child


@contextlib.contextmanager
def handler_blocked(widget: Gtk.Widget, handler):
    """Temporarily stops *handler* reacting to *widget*'s signal — for updating
    a widget to reflect state without that update being reported as a user change."""
    widget.handler_block_by_func(handler)
    try:
        yield
    finally:
        widget.handler_unblock_by_func(handler)


def command_row(title: str, command: str) -> Adw.ActionRow:
    """A row showing a shell command, with a button that copies it."""
    row = Adw.ActionRow()
    row.set_use_markup(False)       # commands contain < and > (and &), which would be read as markup
    row.set_title(title)
    row.set_subtitle(command)
    row.add_prefix(make_icon_prefix("utilities-terminal-symbolic"))
    row.add_suffix(flat_icon_button(
        "edit-copy-symbolic", "Copy command", lambda button: button.get_clipboard().set(command),
    ))
    return row
