"""界面四：外刊阅读（The Guardian）+ 点词查义 + 一键入库 + 阅读记录。"""

from __future__ import annotations

import asyncio
import re

import flet as ft

from wordvault import news
from wordvault.dict_provider import uk_phonetic


GUARDIAN_SECTIONS = [
    ("", "全部"),
    ("world", "国际"),
    ("culture", "文化"),
    ("books", "图书"),
    ("science", "科学"),
    ("technology", "科技"),
    ("environment", "环境"),
    ("business", "商业"),
]


class ReadingView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page = ctx.page
        self.db = ctx.db
        self.provider = ctx.provider

        self.section = ""
        self._lookup_task = None

        self.section_dropdown = ft.Dropdown(
            value="",
            options=[
                ft.dropdown.Option(key, label) for key, label in GUARDIAN_SECTIONS
            ],
            on_select=lambda e: self._on_section_change(e.control.value),
        )
        self.article_list = ft.ListView(expand=True, spacing=8)
        self.history_list = ft.ListView(expand=True, spacing=8)

        self.tabs = ft.Tabs(
            length=2,
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="文章"),
                            ft.Tab(label="记录"),
                        ]
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[
                            ft.Column(
                                expand=True,
                                spacing=8,
                                controls=[
                                    self.section_dropdown,
                                    self.article_list,
                                ],
                            ),
                            ft.Column(
                                expand=True,
                                spacing=8,
                                controls=[
                                    ft.Text(
                                        "按最近打开时间排序",
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                    self.history_list,
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

        self.list_view = ft.Container(expand=True, content=self.tabs)
        self.detail_view = ft.Container(expand=True, visible=False)
        self.body = ft.Container(
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[self.list_view, self.detail_view],
            ),
        )
        self.root = ft.Column(
            expand=True,
            spacing=8,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            "外刊阅读",
                            size=20,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip="清除未读缓存",
                            on_click=lambda e: self._clear_cache(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            tooltip="刷新文章",
                            on_click=lambda e: self.page.run_task(self.refresh),
                        ),
                    ]
                ),
                self.body,
            ],
        )

        self._render_articles()

    # ---------------- 列表 ----------------

    def _render_articles(self) -> None:
        articles = [
            a
            for a in self.db.list_articles(self.section or None)
            if not a.get("last_opened_at")
        ]
        controls = []
        for a in articles:
            controls.append(
                ft.Card(
                    content=ft.Container(
                        padding=ft.Padding(12, 10, 12, 10),
                        on_click=lambda e, aid=a["id"]: self.open_article(aid),
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Text(
                                    a["title"],
                                    size=14,
                                    weight=ft.FontWeight.W_600,
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    f"{a['source']} · {a['section'] or '综合'} · "
                                    f"{a['published_at'][:10]}",
                                    size=11,
                                    color=ft.Colors.GREY_600,
                                ),
                            ],
                        ),
                    )
                )
            )
        if not controls:
            controls = [
                ft.Container(
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding(0, 40, 0, 0),
                    content=ft.Text(
                        "还没有文章，点右上角刷新",
                        size=14,
                        color=ft.Colors.GREY_600,
                    ),
                )
            ]
        self.article_list.controls = controls
        self.page.update()

    def _render_history(self) -> None:
        history = self.db.reading_history()
        controls = []
        for a in history:
            finished = bool(a.get("finished"))
            controls.append(
                ft.Card(
                    content=ft.Container(
                        padding=ft.Padding(12, 10, 12, 10),
                        on_click=lambda e, aid=a["id"]: self.open_article(aid),
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            a["title"],
                                            size=14,
                                            weight=ft.FontWeight.W_600,
                                            max_lines=2,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                            color=(
                                                "#2E9E5B" if finished else None
                                            ),
                                            expand=True,
                                        ),
                                        ft.Icon(
                                            ft.Icons.CHECK_CIRCLE,
                                            size=18,
                                            color="#2E9E5B",
                                        )
                                        if finished
                                        else ft.Container(),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE_OUTLINE,
                                            icon_size=18,
                                            tooltip="删除这条记录",
                                            on_click=lambda e, aid=a["id"]: self._delete_record(aid),
                                        ),
                                    ]
                                ),
                                ft.Text(
                                    f"上次打开：{a['last_opened_at'][:16]}",
                                    size=11,
                                    color=ft.Colors.GREY_600,
                                ),
                            ],
                        ),
                    )
                )
            )
        if not controls:
            controls = [
                ft.Container(
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding(0, 40, 0, 0),
                    content=ft.Text(
                        "还没有阅读记录",
                        size=14,
                        color=ft.Colors.GREY_600,
                    ),
                )
            ]
        self.history_list.controls = controls
        self.page.update()

    def _delete_record(self, article_id: str) -> None:
        article = self.db.get_article(article_id)
        title = article["title"] if article else "这条文章"

        def do_delete(_):
            self.page.pop_dialog()
            self.db.delete_article(article_id)
            self._render_history()
            self._render_articles()
            self.ctx.snack("已删除这条阅读记录")

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("删除阅读记录"),
            content=ft.Text(f"确定删除「{title}」的阅读记录吗？"),
            actions=[
                ft.TextButton(
                    content=ft.Text("取消"),
                    on_click=lambda e: self.page.pop_dialog(),
                ),
                ft.FilledButton(
                    content=ft.Text("删除"),
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE
                    ),
                    on_click=do_delete,
                ),
            ],
        )
        self.page.show_dialog(dialog)

    async def refresh(self) -> None:
        try:
            articles = await asyncio.to_thread(
                news.fetch_articles, self.section or None, 12
            )
            for a in articles:
                self.db.upsert_article(a)
            self._render_articles()
            self.ctx.snack(f"已刷新 {len(articles)} 篇文章")
        except news.NewsError as exc:
            self.ctx.snack(str(exc), error=True)
        except Exception as exc:  # noqa: BLE001
            self.ctx.snack(f"刷新失败：{exc}", error=True)

    def _on_section_change(self, value: str) -> None:
        self.section = value or ""
        self._render_articles()

    def _clear_cache(self) -> None:
        count = self.db.clear_unopened_articles()
        self._render_articles()
        self.ctx.snack(f"已清除 {count} 篇未读缓存文章")

    # ---------------- 阅读正文 ----------------

    def open_article(self, article_id: str) -> None:
        article = self.db.get_article(article_id)
        if article is None:
            return
        self.db.mark_article_opened(article_id)

        back_button = ft.TextButton(
            content=ft.Text("← 返回"),
            on_click=lambda e: self._back_to_list(),
        )
        title = ft.Text(article["title"], size=20, weight=ft.FontWeight.BOLD)
        meta = ft.Text(
            f"来源：{article['source']} · {article['section'] or '综合'} · "
            f"{article['published_at'][:16]}",
            size=12,
            color=ft.Colors.GREY_600,
        )

        search_box = ft.TextField(
            hint_text="自由查词：输入单词或短语",
            dense=True,
            expand=True,
            on_submit=lambda e: self._lookup_word(search_box.value),
        )
        search_button = ft.IconButton(
            icon=ft.Icons.SEARCH,
            tooltip="查词",
            on_click=lambda e: self._lookup_word(search_box.value),
        )

        paragraph_controls = []
        for paragraph in self._split_paragraphs(article["body"]):
            paragraph_controls.append(
                ft.Text(
                    spans=self._article_spans(paragraph),
                    size=16,
                )
            )

        finished = bool(article.get("finished"))
        finish_button = ft.FilledButton(
            content=ft.Text("已读完 ✓" if finished else "Finish"),
            icon=None if finished else ft.Icons.CHECK,
            height=44,
            on_click=(
                None if finished else lambda e: self._finish_article(article_id)
            ),
        )
        detail = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
            controls=[
                back_button,
                title,
                meta,
                ft.Row(controls=[search_box, search_button], spacing=6),
                *paragraph_controls,
                finish_button,
            ],
        )
        self.detail_view.content = detail
        self.detail_view.visible = True
        self.list_view.visible = False
        self.page.update()
        self._render_history()

    @staticmethod
    def _paragraph_text(body: str) -> str:
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'])", body)
            if s.strip()
        ]
        if not sentences:
            return body
        paragraphs = []
        for i in range(0, len(sentences), 3):
            paragraphs.append(" ".join(sentences[i : i + 3]))
        return "\n\n".join(paragraphs)

    @staticmethod
    def _split_paragraphs(body: str) -> list[str]:
        return [
            p for p in ReadingView._paragraph_text(body).split("\n\n") if p.strip()
        ]

    def _article_spans(self, paragraph: str) -> list[ft.TextSpan]:
        spans: list[ft.TextSpan] = []
        last = 0
        for m in re.finditer(r"[A-Za-z][A-Za-z'’-]*", paragraph):
            if m.start() > last:
                spans.append(ft.TextSpan(text=paragraph[last : m.start()]))
            word = m.group(0)
            spans.append(
                ft.TextSpan(
                    text=word,
                    on_click=lambda e, w=word: self._lookup_word(w),
                )
            )
            last = m.end()
        if last < len(paragraph):
            spans.append(ft.TextSpan(text=paragraph[last:]))
        return spans

    def _back_to_list(self) -> None:
        self.list_view.visible = True
        self.detail_view.visible = False
        self._render_articles()
        self._render_history()
        self.page.update()

    def _finish_article(self, article_id: str) -> None:
        self.db.mark_article_finished(article_id)
        self.ctx.snack("已标记为读完，记录中会显示绿色")
        self.open_article(article_id)

    # ---------------- 点词查义 ----------------

    def _lookup_word(self, word: str) -> None:
        word = (word or "").strip()
        if not word:
            return
        if self._lookup_task is not None:
            self._lookup_task.cancel()
        self._lookup_task = self.page.run_task(self._lookup_now, word)

    async def _lookup_now(self, text: str) -> None:
        result = await asyncio.to_thread(self.provider.lookup, text, True)
        self._show_word_sheet(result, text)

    def _show_word_sheet(self, result, query_text: str) -> None:
        query_box = ft.TextField(value=query_text, dense=True)
        meanings_text = "\n".join(
            f"{m.pos} {m.text}".strip() if m.pos else m.text
            for m in result.meanings[:6]
        )
        if not meanings_text:
            meanings_text = "（未找到释义，可修改上方单词后重新查询）"

        mode_dropdown = ft.Dropdown(
            value="write",
            options=[
                ft.dropdown.Option("write", "写作型（会拼写）"),
                ft.dropdown.Option("read", "阅读型（认识即可）"),
            ],
        )

        def re_query(_):
            new_query = (query_box.value or "").strip()
            if not new_query:
                return
            self.page.pop_dialog()
            self._lookup_word(new_query)

        def add(_):
            mode = mode_dropdown.value or "write"
            created = self.db.add_word(
                word=result.word,
                phonetic=result.phonetic,
                meanings=result.meanings,
                examples=result.examples,
                source=result.source if result.ok else "manual",
                learn_mode=mode,
            )
            self.page.pop_dialog()
            if created:
                self.ctx.notify_data_changed()
                self.ctx.snack(
                    f"已加入词库：{result.word}（{'写作型' if mode == 'write' else '阅读型'}）"
                )
            else:
                self.ctx.snack(f"「{result.word}」已在词库中")

        phonetic = uk_phonetic(result.phonetic)
        content = ft.Container(
            padding=ft.Padding(20, 16, 20, 20),
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                spacing=10,
                controls=[
                    query_box,
                    ft.Text(
                        result.word, size=22, weight=ft.FontWeight.BOLD
                    ),
                    ft.Text(phonetic, size=13, color=ft.Colors.GREY_600)
                    if phonetic
                    else ft.Container(),
                    ft.Text(meanings_text, size=15),
                    mode_dropdown,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.TextButton(
                                content=ft.Text("查询"),
                                on_click=re_query,
                            ),
                            ft.TextButton(
                                content=ft.Text("关闭"),
                                on_click=lambda e: self.page.pop_dialog(),
                            ),
                            ft.FilledButton(
                                content=ft.Text("加入词库"),
                                on_click=add,
                            ),
                        ],
                    ),
                ],
            ),
        )
        sheet = ft.BottomSheet(
            content=content,
            scrollable=True,
            show_drag_handle=True,
        )
        self.page.show_dialog(sheet)

    # ---------------- 生命周期 ----------------

    def on_show(self) -> None:
        self._render_articles()
        self._render_history()
