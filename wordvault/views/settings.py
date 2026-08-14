"""设置：每日配额、主题、数据备份（导出/导入）。"""

from __future__ import annotations

import asyncio
import hmac
import json
from pathlib import Path

import flet as ft

from wordvault import __version__
from wordvault import cloud
from wordvault.backup import import_json
from wordvault.theme import apply_theme_mode


_DELETE_PASSWORD = "dev123456"


def open_settings(ctx) -> None:
    page = ctx.page
    db = ctx.db

    new_box = ft.TextField(
        label="每日新词上限",
        value=db.get_setting("new_daily_limit"),
        keyboard_type=ft.KeyboardType.NUMBER,
        dense=True,
    )
    review_box = ft.TextField(
        label="每日复习上限",
        value=db.get_setting("review_daily_limit"),
        keyboard_type=ft.KeyboardType.NUMBER,
        dense=True,
    )
    theme_dropdown = ft.Dropdown(
        label="外观主题",
        value=db.get_setting("theme_mode"),
        options=[
            ft.dropdown.Option("system", "跟随系统"),
            ft.dropdown.Option("light", "浅色"),
            ft.dropdown.Option("dark", "深色"),
        ],
    )

    picker = getattr(ctx, "file_picker", None)
    if picker is None:
        picker = ft.FilePicker()
        ctx.file_picker = picker

    def save(_):
        try:
            new_limit = int(new_box.value)
            review_limit = int(review_box.value)
        except (TypeError, ValueError):
            ctx.snack("请输入有效的数字", error=True)
            return
        if not (0 <= new_limit <= 500) or not (0 <= review_limit <= 2000):
            ctx.snack("新词上限 0-500，复习上限 0-2000", error=True)
            return
        db.set_setting("new_daily_limit", str(new_limit))
        db.set_setting("review_daily_limit", str(review_limit))
        db.set_setting("theme_mode", theme_dropdown.value or "system")
        apply_theme_mode(page, theme_dropdown.value or "system")
        page.pop_dialog()
        ctx.snack("设置已保存")
        ctx.notify_data_changed()

    async def export(_):
        payload = json.dumps(
            ctx.db.export_payload(), ensure_ascii=False, indent=2
        )
        try:
            path = await picker.save_file(
                file_name="wordvault_backup.json",
                allowed_extensions=["json"],
                dialog_title="导出备份",
                src_bytes=payload.encode("utf-8"),
            )
            if path:
                ctx.snack(f"已导出备份：{path}")
        except ValueError as exc:
            ctx.snack(f"导出失败：{exc}", error=True)

    async def import_(_):
        files = await picker.pick_files(
            allowed_extensions=["json"],
            dialog_title="选择备份文件",
        )
        if files and files[0].path:
            _ask_import_mode(ctx, Path(files[0].path))

    upload_label = ft.Text("上传云端")
    restore_label = ft.Text("从云端恢复")

    async def upload_cloud(_):
        await _upload_cloud(
            ctx, upload_button, restore_button, upload_label, restore_label
        )

    async def restore_cloud(_):
        await _restore_cloud(
            ctx, upload_button, restore_button, upload_label, restore_label
        )

    upload_button = ft.FilledButton(
        content=upload_label,
        icon=ft.Icons.CLOUD_UPLOAD,
        on_click=upload_cloud,
    )
    restore_button = ft.OutlinedButton(
        content=restore_label,
        icon=ft.Icons.CLOUD_DOWNLOAD,
        on_click=restore_cloud,
    )
    delete_button = ft.OutlinedButton(
        content=ft.Text("删除本地数据"),
        icon=ft.Icons.DELETE_FOREVER,
        style=ft.ButtonStyle(color=ft.Colors.RED_700),
        on_click=lambda e: _confirm_delete(ctx),
    )

    dialog = ft.AlertDialog(
        modal=True,
        scrollable=True,
        title=ft.Text("设置"),
        content=ft.Container(
            content=ft.Column(
                spacing=12,
                controls=[
                    new_box,
                    review_box,
                    theme_dropdown,
                    ft.Divider(height=1),
                    ft.Text(
                        "数据备份",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(
                        controls=[
                            ft.FilledButton(
                                content=ft.Text("导出备份"),
                                icon=ft.Icons.UPLOAD_FILE,
                                on_click=export,
                            ),
                            ft.OutlinedButton(
                                content=ft.Text("导入备份"),
                                icon=ft.Icons.DOWNLOAD,
                                on_click=import_,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Divider(height=1),
                    ft.Text(
                        "云端同步",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(
                        controls=[upload_button, restore_button],
                        wrap=True,
                        spacing=10,
                        run_spacing=8,
                    ),
                    ft.Text(
                        "上传会把当前数据保存到云端 word/ 目录；"
                        "恢复会自动下载最新备份并合并，本地数据不会被删除。",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Divider(height=1),
                    ft.Text(
                        "数据管理",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(
                        controls=[delete_button],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Text(
                        f"数据库位置：{db.path}",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Divider(height=1),
                    ft.Text(
                        f"版本 {__version__}",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Text(
                        "Developed by Side_ Through Vibecoding",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
                ],
            ),
        ),
        actions=[
            ft.TextButton(
                content=ft.Text("关闭"),
                on_click=lambda e: page.pop_dialog(),
            ),
            ft.FilledButton(content=ft.Text("保存"), on_click=save),
        ],
    )
    page.show_dialog(dialog)


def _err_text(exc: Exception) -> str:
    """把云端异常转成中文提示。"""
    if isinstance(exc, cloud.CloudError):
        return str(exc)
    return cloud.describe_error(exc)


async def _upload_cloud(
    ctx, upload_button, restore_button, upload_label, restore_label
) -> None:
    upload_button.disabled = True
    restore_button.disabled = True
    upload_label.value = "上传中…"
    ctx.page.update()
    try:
        result = await asyncio.to_thread(cloud.upload_backup, ctx.db)
        ctx.snack(
            f"已上传云端：{result['name']}（{result['size'] / 1024:.1f} KB）"
        )
    except Exception as exc:  # noqa: BLE001
        ctx.snack(f"上传失败：{_err_text(exc)}", error=True)
    finally:
        upload_button.disabled = False
        restore_button.disabled = False
        upload_label.value = "上传云端"
        ctx.page.update()


async def _restore_cloud(
    ctx, upload_button, restore_button, upload_label, restore_label
) -> None:
    upload_button.disabled = True
    restore_button.disabled = True
    restore_label.value = "恢复中…"
    ctx.page.update()
    try:
        latest, payload = await asyncio.to_thread(cloud.download_latest)
        stats = ctx.db.import_payload(payload, mode="sync")
        ctx.notify_data_changed()
        message = (
            f"来自：{latest['key']}\n"
            f"新增 {stats['added']} 个，更新 {stats['updated']} 个，"
            f"恢复复习记录 {stats['logs']} 条。\n"
            "采用合并方式导入，本地原有数据未删除。"
        )
        ctx.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("云端恢复完成"),
                content=ft.Text(message, size=14),
                actions=[
                    ft.FilledButton(
                        content=ft.Text("确定"),
                        on_click=lambda e: ctx.page.pop_dialog(),
                    )
                ],
            )
        )
    except Exception as exc:  # noqa: BLE001
        ctx.snack(f"云端恢复失败：{_err_text(exc)}", error=True)
    finally:
        upload_button.disabled = False
        restore_button.disabled = False
        restore_label.value = "从云端恢复"
        ctx.page.update()


def _confirm_delete(ctx) -> None:
    page = ctx.page
    password_box = ft.TextField(
        label="删除密码",
        password=True,
        can_reveal_password=True,
        autofocus=True,
        dense=True,
        on_submit=lambda e: do_delete(None),
    )
    error_box = ft.Text("", size=12, color=ft.Colors.RED_600)

    def do_delete(_):
        if not hmac.compare_digest(
            str(password_box.value or ""), _DELETE_PASSWORD
        ):
            error_box.value = "密码错误，请重新输入"
            password_box.value = ""
            page.update()
            return
        stats = ctx.db.delete_all_data()
        page.pop_dialog()
        ctx.notify_data_changed()
        ctx.snack(
            f"已删除全部数据：{stats['words']} 个单词、"
            f"{stats['logs']} 条复习记录"
        )

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("删除本地数据"),
        content=ft.Column(
            tight=True,
            spacing=10,
            controls=[
                ft.Text(
                    "此操作会删除所有单词、学习进度与复习记录，且无法恢复"
                    "（外观与配额设置会保留）。",
                    size=13,
                    color=ft.Colors.RED_700,
                ),
                ft.Text("请输入删除密码确认：", size=13),
                password_box,
                error_box,
            ],
        ),
        actions=[
            ft.TextButton(
                content=ft.Text("取消"),
                on_click=lambda e: (page.pop_dialog(), open_settings(ctx)),
            ),
            ft.FilledButton(
                content=ft.Text("确认删除"),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE
                ),
                on_click=do_delete,
            ),
        ],
    )
    page.show_dialog(dialog)


def _ask_import_mode(ctx, source: Path) -> None:
    page = ctx.page
    result_box = ft.Text("", size=13)

    def do_import(mode: str):
        try:
            stats = import_json(ctx.db, source, mode=mode)
            message = (
                f"导入完成：新增 {stats['added']} 个词，跳过重复 "
                f"{stats['skipped']} 个，恢复复习记录 {stats['logs']} 条。"
            )
            error = False
        except (OSError, ValueError) as exc:
            message = f"导入失败：{exc}"
            error = True
        page.pop_dialog()
        ctx.notify_data_changed()
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("导入失败" if error else "导入完成"),
                content=ft.Text(message, size=14),
                actions=[
                    ft.FilledButton(
                        content=ft.Text("确定"),
                        on_click=lambda e: page.pop_dialog(),
                    )
                ],
            )
        )

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("导入方式"),
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Text(
                    "合并：保留现有数据，重复单词跳过；\n"
                    "覆盖：清空当前数据后导入（原数据会丢失）。",
                    size=13,
                ),
                result_box,
            ],
        ),
        actions=[
            ft.Row(
                spacing=16,
                alignment=ft.MainAxisAlignment.END,
                controls=[
                    ft.TextButton(
                        content=ft.Text("取消"),
                        on_click=lambda e: page.pop_dialog(),
                    ),
                    ft.OutlinedButton(
                        content=ft.Text("覆盖导入"),
                        on_click=lambda e: do_import("replace"),
                    ),
                    ft.FilledButton(
                        content=ft.Text("合并导入"),
                        on_click=lambda e: do_import("merge"),
                    ),
                ],
            ),
        ],
    )
    page.show_dialog(dialog)
