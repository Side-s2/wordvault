"""跨页面共享的应用上下文。"""

from __future__ import annotations

import flet as ft

from wordvault.db import Database
from wordvault.dict_provider import DictProvider


class AppContext:
    def __init__(self, page: ft.Page, db: Database, provider: DictProvider):
        self.page = page
        self.db = db
        self.provider = provider
        self.views: list = []

    def register(self, view) -> None:
        self.views.append(view)

    def notify_data_changed(self) -> None:
        for view in self.views:
            on_change = getattr(view, "on_data_changed", None)
            if callable(on_change):
                on_change()

    def snack(self, message: str, error: bool = False) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                ft.Text(message),
                bgcolor=ft.Colors.RED_700 if error else None,
                duration=2600,
            )
        )
