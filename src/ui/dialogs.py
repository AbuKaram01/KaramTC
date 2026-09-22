# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/dialogs.py — Toasts, message dialogs and confirmations.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

TOAST_TIMEOUT_S = 3


def show_toast(overlay: Adw.ToastOverlay, message: str, timeout: int = TOAST_TIMEOUT_S) -> None:
    toast = Adw.Toast(title=message, timeout=timeout)
    toast.set_use_markup(False)     # messages may contain file names with & or <
    overlay.add_toast(toast)


def show_message_dialog(parent, heading: str, body: str) -> None:
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("ok", "OK")
    dialog.set_default_response("ok")
    dialog.present(parent)


def show_error_dialog(parent, message: str) -> None:
    show_message_dialog(parent, "Error", message)


def confirm(
    parent,
    heading: str,
    body: str,
    *,
    accept_id: str,
    accept_label: str,
    on_accept,
    cancel_id: str = "cancel",
    cancel_label: str = "Cancel",
    destructive: bool = True,
) -> None:
    """
    Asks a two-way question and calls *on_accept()* only on the accept answer.

    A destructive confirmation defaults to the safe (cancel) answer; a
    suggested one defaults to accepting.
    """
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response(cancel_id, cancel_label)
    dialog.add_response(accept_id, accept_label)
    dialog.set_response_appearance(
        accept_id, Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED,
    )
    dialog.set_default_response(cancel_id if destructive else accept_id)
    dialog.set_close_response(cancel_id)
    dialog.connect("response", lambda _dialog, response: response == accept_id and on_accept())
    dialog.present(parent)
