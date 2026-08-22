"""单词本 WordVault 入口。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import flet as ft

from wordvault.app_context import AppContext
from wordvault.db import Database
from wordvault.dict_provider import DictProvider
from wordvault.theme import apply_theme_mode, build_dark_theme, build_theme
from wordvault.views.add_view import AddView
from wordvault.views.reading_view import ReadingView
from wordvault.views.review_view import ReviewView
from wordvault.views.settings import open_settings
from wordvault.views.stats_view import StatsView


APP_DIR = Path(__file__).resolve().parent
OFFLINE_DICT = APP_DIR / "assets" / "dict" / "ecdict.db"
SMOKE = "--smoke-test" in sys.argv


def _find_offline_dict() -> Path | None:
    """桌面端在项目目录下找词库；安卓端兜底查找工作目录下的 assets。"""
    candidates = [
        OFFLINE_DICT,
        Path.cwd() / "assets" / "dict" / "ecdict.db",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def main(page: ft.Page) -> None:
    page.title = "wordvault"
    font_family = (
        "Microsoft YaHei UI"
        if page.platform == ft.PagePlatform.WINDOWS
        else None
    )
    page.theme = build_theme(font_family)
    page.dark_theme = build_dark_theme(font_family)

    db = Database()
    provider = DictProvider(_find_offline_dict())
    ctx = AppContext(page, db, provider)
    apply_theme_mode(page, db.get_setting("theme_mode"))

    if page.platform in (
        ft.PagePlatform.WINDOWS,
        ft.PagePlatform.MACOS,
        ft.PagePlatform.LINUX,
    ):
        page.window.width = 420
        page.window.height = 860
        page.window.min_width = 360
        page.window.min_height = 640

    add_view = AddView(ctx)
    review_view = ReviewView(ctx)
    reading_view = ReadingView(ctx)
    stats_view = StatsView(ctx)
    ctx.register(add_view)
    ctx.register(review_view)
    ctx.register(reading_view)
    ctx.register(stats_view)

    tabs = [
        {"label": "添加", "icon": ft.Icons.ADD, "view": add_view},
        {"label": "复习", "icon": ft.Icons.SCHOOL, "view": review_view},
        {"label": "阅读", "icon": ft.Icons.AUTO_STORIES, "view": reading_view},
        {"label": "统计", "icon": ft.Icons.INSIGHTS, "view": stats_view},
    ]

    body = ft.Container(expand=True, content=add_view.root)

    def switch(index: int) -> None:
        body.content = tabs[index]["view"].root
        tabs[index]["view"].on_show()
        page.update()

    header = ft.Container(
        padding=ft.Padding(16, 14, 10, 6),
        content=ft.Row(
            controls=[
                ft.Text(
                    "WordVault",
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="设置与备份",
                    on_click=lambda e: open_settings(ctx),
                ),
            ]
        ),
    )

    nav = ft.NavigationBar(
        selected_index=0,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.ADD, label="添加"),
            ft.NavigationBarDestination(icon=ft.Icons.SCHOOL, label="复习"),
            ft.NavigationBarDestination(icon=ft.Icons.AUTO_STORIES, label="阅读"),
            ft.NavigationBarDestination(icon=ft.Icons.INSIGHTS, label="统计"),
        ],
        on_change=lambda e: switch(int(e.control.selected_index)),
    )

    page.add(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[header, body, nav],
        )
    )
    # 启动时立即加载一次词表，避免进入添加页是空的
    switch(0)

    if SMOKE:
        page.run_task(
            _smoke_flow,
            page,
            ctx,
            switch,
            add_view,
            review_view,
            reading_view,
            stats_view,
            nav,
        )


async def _smoke_flow(
    page, ctx, switch, add_view, review_view, reading_view, stats_view, nav
) -> None:
    """冒烟测试：自动切页、真实加词、复习作答，输出标记后退出。"""
    try:
        import os
        from pathlib import Path as _Path
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        shots = _Path(__file__).resolve().parent / "ui_shots"
        shots.mkdir(exist_ok=True)
        page.enable_screenshots = True

        async def snap(name: str):
            data = await page.take_screenshot(delay=700)
            (shots / f"{name}.png").write_bytes(data)
            print(f"SMOKE_SHOT {name}", flush=True)

        print("SMOKE_START", flush=True)
        await asyncio.sleep(1.0)

        if os.environ.get("SMOKE_STATS_ONLY") == "1":
            # 只验证真实导航栏切换路径 + 统计图渲染
            class _FakeEvent:
                control = None

            ev = _FakeEvent()
            ev.control = _FakeEvent()
            ev.control.selected_index = 3
            nav.on_change(ev)
            await asyncio.sleep(1.0)

            # 现场 dump 实际渲染树中的柱状图数值
            try:
                col = stats_view.content.content
                card = col.controls[4]
                inner = card.content.content.controls[1]
                bars = inner.controls[0].controls
                print(
                    "SMOKE_BARDUMP "
                    + repr(
                        [
                            (round(b.height, 1), b.bgcolor)
                            for b in bars[-6:]
                        ]
                    ),
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"SMOKE_BARDUMP_FAIL {exc!r}", flush=True)

            await snap("stats_only")
            print("SMOKE_STATS_DONE", flush=True)
            await asyncio.sleep(0.5)
            try:
                await page.window.close()
            except Exception:
                pass
            return

        # 打开设置对话框（验证 FilePicker 以 Service 方式创建不再报错）
        from wordvault.views.settings import open_settings

        open_settings(ctx)
        await asyncio.sleep(0.6)
        await snap("00_settings")
        page.pop_dialog()
        print("SMOKE_SETTINGS_OK", flush=True)

        print("SMOKE_TAB_ADD", flush=True)

        # 走一遍真实添加流程（关闭例句请求，纯离线，速度快）
        add_view.want_examples.value = False
        add_view.input_box.value = "apple, banana\ncherry 樱桃"
        await add_view.on_parse()
        await add_view.on_confirm()
        word_count = ctx.db.count_words()
        print(f"SMOKE_ADD_DONE words={word_count}", flush=True)
        await snap("01_add_list")

        # 打开编辑弹窗截图，验证可滚动内容与按钮换行
        first_word = next(iter(ctx.db.list_words()), None)
        if first_word:
            add_view.open_edit_dialog(first_word.id)
            await asyncio.sleep(0.6)
            await snap("01b_edit_dialog")
            page.pop_dialog()

        # 补充一批词，让预览与四选一更真实
        add_view.want_examples.value = False
        add_view.input_box.value = "school, family\nbook 书, water\nmusic"
        await add_view.on_parse()
        await snap("02_add_preview")
        add_view.open_meaning_editor(0)
        await asyncio.sleep(0.5)
        await snap("02b_meaning_editor")
        page.pop_dialog()
        await add_view.on_confirm()

        await asyncio.sleep(0.8)
        switch(1)
        print("SMOKE_TAB_REVIEW", flush=True)
        review_view.start_session()
        if review_view.mode == "session":
            await snap("03_review_question")
            if review_view.options:
                review_view.on_answer(review_view.correct_text)
            else:
                review_view.on_answer("__know__")
            print("SMOKE_ANSWER_DONE", flush=True)
            await snap("04_review_reveal")
        else:
            print("SMOKE_REVIEW_EMPTY", flush=True)

        await asyncio.sleep(0.8)
        switch(2)
        print("SMOKE_TAB_READING", flush=True)
        await snap("04b_reading")

        # 注入 30 天模拟复习记录，用于验证统计图表渲染
        word_ids = [w.id for w in ctx.db.list_words()][:3]
        if word_ids:
            with ctx.db._lock:
                for offset in range(29, -1, -1):
                    ts = (
                        _dt.now() - _td(days=offset)
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    for k in range((offset * 7) % 9):
                        ctx.db._conn.execute(
                            "INSERT INTO review_log(word_id, reviewed_at, result, "
                            "answer, correct_answer, ms, proficiency_after, "
                            "interval_after, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                word_ids[k % len(word_ids)],
                                ts,
                                "correct" if k % 3 else "wrong",
                                "",
                                "",
                                500,
                                0.5,
                                1.0,
                                "choice",
                            ),
                        )
                ctx.db._conn.commit()

        await asyncio.sleep(0.8)
        switch(3)
        print("SMOKE_TAB_STATS", flush=True)
        await snap("05_stats")
        await asyncio.sleep(0.8)
        switch(0)
        print("SMOKE_OK", flush=True)
        await asyncio.sleep(0.5)
        try:
            if hasattr(page, "window"):
                await page.window.close()
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE_FAIL {exc!r}", flush=True)


if __name__ == "__main__":
    ft.run(main=main)
