"""设置页按钮回调的接线测试（不启动真实窗口）。"""

import asyncio
import inspect
import unittest
from unittest.mock import patch

import flet as ft

from wordvault.views.settings import open_settings


class _FakePage:
    def __init__(self):
        self.dialog = None

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.dialog = None

    def update(self):
        return None


class _FakeDb:
    path = "fake.db"

    def __init__(self):
        self.deleted = None

    def get_setting(self, key):
        return {
            "new_daily_limit": "20",
            "review_daily_limit": "100",
            "theme_mode": "system",
        }[key]

    def set_setting(self, key, value):
        return None

    def export_payload(self):
        return {"words": [], "states": [], "logs": []}

    def import_payload(self, payload, mode="merge"):
        return {"added": 1, "updated": 0, "logs": 0}

    def delete_all_data(self):
        self.deleted = {"words": 1, "logs": 1}
        return self.deleted


class _FakeCtx:
    def __init__(self):
        self.page = _FakePage()
        self.db = _FakeDb()
        self.file_picker = None
        self.snacks = []

    def snack(self, message, error=False):
        self.snacks.append((message, error))

    def notify_data_changed(self):
        return None


class SettingsHandlersTests(unittest.TestCase):
    def setUp(self):
        self.ctx = _FakeCtx()
        open_settings(self.ctx)
        col = self.ctx.page.dialog.content.content
        self.cloud_row = col.controls[8]
        self.manage_row = col.controls[12]

    def test_cloud_buttons_bind_async_handlers_directly(self):
        upload, restore = self.cloud_row.controls
        self.assertTrue(inspect.iscoroutinefunction(upload.on_click))
        self.assertTrue(inspect.iscoroutinefunction(restore.on_click))

    def test_upload_runs_and_reports(self):
        upload = self.cloud_row.controls[0]
        with patch(
            "wordvault.views.settings.cloud.upload_backup",
            return_value={
                "key": "word/x.json",
                "name": "x.json",
                "size": 1024,
            },
        ):
            asyncio.run(upload.on_click(None))
        self.assertTrue(any("已上传云端" in m for m, _ in self.ctx.snacks))
        self.assertEqual(upload.content.value, "上传云端")

    def test_restore_runs_and_reports(self):
        restore = self.cloud_row.controls[1]
        with patch(
            "wordvault.views.settings.cloud.download_latest",
            return_value=(
                {"key": "word/latest.json"},
                {"words": [], "states": [], "logs": []},
            ),
        ):
            asyncio.run(restore.on_click(None))
        self.assertIsInstance(self.ctx.page.dialog, ft.AlertDialog)
        self.assertEqual(self.ctx.page.dialog.title.value, "云端恢复完成")
        self.assertEqual(restore.content.value, "从云端恢复")

    def test_delete_requires_correct_password(self):
        delete = self.manage_row.controls[0]
        delete.on_click(None)
        confirm = self.ctx.page.dialog
        password_box = confirm.content.controls[2]
        error_box = confirm.content.controls[3]

        password_box.value = "wrong"
        confirm.actions[1].on_click(None)
        self.assertIn("密码错误", error_box.value)
        self.assertIsNone(self.ctx.db.deleted)

        password_box.value = "dev123456"
        confirm.actions[1].on_click(None)
        self.assertEqual(self.ctx.db.deleted, {"words": 1, "logs": 1})
        self.assertTrue(any("已删除全部数据" in m for m, _ in self.ctx.snacks))


if __name__ == "__main__":
    unittest.main()
