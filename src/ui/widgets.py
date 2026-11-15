# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Small widget factories shared by every screen.

Each one captures a widget recipe the app repeats (a flat button in a row, a switch row, a scrolled clamp, ...), so
that screens read as layout, not as property setting.
"""

from __future__ import annotations

import contextlib

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk


def labeled_button(label: str, icon_name: str) -> Gtk.Button:
    """Create a button that shows an icon and its text.

    Do not build these with Gtk.Button(label=...) followed by set_icon_name(): GTK replaces the child of the button
    with the icon, silently dropping the label, so the button ends up icon-only and users cannot tell similar icons
    apart (for example "Open text file" and "Open folder").
    """
    button = Gtk.Button()
    button.set_child(Adw.ButtonContent(label=label, icon_name=icon_name))
    return button


def set_button_text(button: Gtk.Button, text: str) -> None:
    """Change the text of a labeled_button() while keeping its icon."""
    content = button.get_child()
    if isinstance(content, Adw.ButtonContent):
        content.set_label(text)
    else:
        button.set_label(text)


def pill_button(
    label: str, icon_name: str, on_click=None, suggested: bool = False, tooltip: str | None = None,
) -> Gtk.Button:
    """Create a rounded "pill" button with an icon and text.

    Args:
        label: The button text.
        icon_name: The name of the icon shown next to the text.
        on_click: Connected to the "clicked" signal when given.
        suggested: Style the button as the suggested (primary) action.
        tooltip: The tooltip text, if any.
    """
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
    """Create a flat text button, vertically centred, for the suffix of a row."""
    button = Gtk.Button(label=label)
    button.add_css_class("flat")
    button.set_valign(Gtk.Align.CENTER)
    if on_click:
        button.connect("clicked", on_click)
    return button


def flat_icon_button(
    icon_name: str, tooltip: str | None = None, on_click=None, centered: bool = True,
) -> Gtk.Button:
    """Create a flat icon-only button.

    Args:
        icon_name: The name of the icon.
        tooltip: The tooltip text, if any. An icon-only button needs one to be understandable.
        on_click: Connected to the "clicked" signal when given.
        centered: Centre the button vertically, as needed for the suffix of a row.
    """
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
    """Create a 16px icon suitable for use as a prefix in Adw rows."""
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(16)
    return image


def switch_row(title: str, active: bool, on_toggled=None, subtitle: str | None = None):
    """Create an Adw.ActionRow with a switch and return ``(row, switch)``.

    *on_toggled* is connected after the initial state is set, so it does not fire for it.
    """
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
    """Return a Gtk.StringList holding *labels*, for use as the model of a combo row."""
    strings = Gtk.StringList()
    for label in labels:
        strings.append(label)
    return strings


def dim_label(text: str = "", caption: bool = False) -> Gtk.Label:
    """Create a de-emphasised label; *caption* also applies the smaller caption style."""
    label = Gtk.Label(label=text)
    label.add_css_class("dim-label")
    if caption:
        label.add_css_class("caption")
    return label


def status_page(icon_name: str, title: str, description: str | None = None) -> Adw.StatusPage:
    """Create an Adw.StatusPage with an icon, a title and an optional description."""
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
    """Create a vertically scrolling page whose content is centred and width-limited.

    Returns:
        The scrolled window to place in the UI, and the clamp inside it that receives the content.
    """
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
    """Create a horizontally centred row of widgets."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_halign(Gtk.Align.CENTER)
    for child in children:
        box.append(child)
    return box


def add_file_drop_target(widget: Gtk.Widget, on_drop) -> None:
    """Let files be dropped on *widget*; ``on_drop(target, value, x, y)`` returns whether the drop was accepted."""
    target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
    target.connect("drop", on_drop)
    widget.add_controller(target)


def clear_children(box: Gtk.Box) -> None:
    """Remove every child of *box*."""
    child = box.get_first_child()
    while child is not None:
        # Read the next sibling first: a removed child no longer has one.
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child


@contextlib.contextmanager
def handler_blocked(widget: Gtk.Widget, handler):
    """Temporarily stop *handler* from reacting to the signal of *widget*.

    Use it to update a widget to reflect state without that update being reported as a user change.
    """
    widget.handler_block_by_func(handler)
    try:
        yield
    finally:
        widget.handler_unblock_by_func(handler)


def command_row(title: str, command: str) -> Adw.ActionRow:
    """Create a row showing a shell command, with a button that copies it."""
    row = Adw.ActionRow()
    # Commands contain "<", ">" and "&", which would be read as markup.
    row.set_use_markup(False)
    row.set_title(title)
    row.set_subtitle(command)
    row.add_prefix(make_icon_prefix("utilities-terminal-symbolic"))
    row.add_suffix(flat_icon_button(
        "edit-copy-symbolic", "Copy command", lambda button: button.get_clipboard().set(command),
    ))
    return row
