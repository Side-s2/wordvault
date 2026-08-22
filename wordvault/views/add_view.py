"""界面一：单词/短语添加与词库管理（添加 / 词库两个分段）。"""

from __future__ import annotations

import asyncio

import flet as ft

from wordvault.db import Example, Meaning, Word
from wordvault.dict_provider import split_pos, uk_phonetic
from wordvault.parse_input import parse_input_text
from wordvault.theme import all_border


SOURCE_LABELS = {
    "offline": "离线词库",
    "online": "在线翻译",
    "none": "未匹配",
    "manual": "手动",
}

SOURCE_COLORS = {
    "offline": "#3E8BD9",
    "online": "#2E9E5B",
    "none": "#E8A13D",
    "manual": "#9AA0AC",
}


def parse_meaning_lines(text: str) -> list[Meaning]:
    meanings: list[Meaning] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        pos, rest = split_pos(line)
        meanings.append(Meaning(pos=pos, text=rest if rest else line))
    return meanings


def meanings_to_text(meanings: list[Meaning]) -> str:
    return "\n".join(
        (f"{m.pos} {m.text}".strip() if m.pos else m.text) for m in meanings
    )


def examples_to_text(examples: list[Example]) -> str:
    return "\n".join(f"{e.en} || {e.zh}" for e in examples)


def parse_example_lines(text: str) -> list[Example]:
    examples: list[Example] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "||" in line:
            en, zh = line.split("||", 1)
            examples.append(Example(en=en.strip(), zh=zh.strip()))
        else:
            examples.append(Example(en="", zh=line))
    return examples


class AddView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page = ctx.page
        self.db = ctx.db
        self.provider = ctx.provider

        self.pending: list[dict] = []
        self.overflow: list[str] = []
        self.search_query = ""
        self.sort_key = "time_desc"
        self._search_task = None
        self._busy = False

        self.input_box = ft.TextField(
            hint_text="输入单词/短语，可批量：每行一个，或用逗号、分号分隔（空格保留在短语内）；"
            "带中文尾巴会自动忽略（如 apple 苹果）",
            multiline=True,
            min_lines=2,
            max_lines=4,
            text_size=15,
            dense=True,
        )
        self.want_examples = ft.Checkbox(
            label="联网获取例句",
            value=True,
        )
        self.learn_mode_dropdown = ft.Dropdown(
            value="write",
            height=46,
            options=[
                ft.dropdown.Option("write", "写作型（会拼写）"),
                ft.dropdown.Option("read", "阅读型（认识即可）"),
            ],
        )
        self.parse_button = ft.FilledButton(
            content=ft.Text("解析并翻译"),
            icon=ft.Icons.SEARCH,
            on_click=lambda e: self.page.run_task(self.on_parse),
        )
        self.parse_progress = ft.ProgressRing(width=24, height=24, visible=False)
        self.status_text = ft.Text("", size=12)
        self.preview_list = ft.ListView(
            expand=True, spacing=8, auto_scroll=True, visible=False
        )
        self.confirm_button = ft.FilledButton(
            content=ft.Text("确认添加"),
            icon=ft.Icons.ADD,
            visible=False,
            on_click=lambda e: self.page.run_task(self.on_confirm),
        )
        self.confirm_count = ft.Text("", size=13)

        self.search_box = ft.TextField(
            hint_text="搜索单词或释义…",
            prefix_icon=ft.Icons.SEARCH,
            height=46,
            expand=True,
            on_change=lambda e: self.on_search_change(e.control.value),
        )
        self.sort_dropdown = ft.Dropdown(
            value="time_desc",
            width=96,
            height=46,
            options=[
                ft.dropdown.Option("time_desc", "时间 ↓"),
                ft.dropdown.Option("time_asc", "时间 ↑"),
                ft.dropdown.Option("alpha", "A→Z"),
            ],
            on_select=lambda e: self.on_sort_change(e.control.value),
        )
        self.word_count = ft.Text("", size=13)
        self.word_list = ft.ListView(expand=True, spacing=6)

        add_page = ft.Container(
            padding=8,
            content=ft.Column(
                expand=True,
                spacing=8,
                controls=[
                    self.input_box,
                    ft.Row(
                        controls=[self.want_examples, self.learn_mode_dropdown],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        controls=[self.parse_button, self.parse_progress],
                        spacing=10,
                    ),
                    self.status_text,
                    self.preview_list,
                    ft.Row(
                        controls=[self.confirm_button, self.confirm_count],
                        spacing=10,
                    ),
                ],
            ),
        )

        library_page = ft.Container(
            padding=8,
            content=ft.Column(
                expand=True,
                spacing=8,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                "我的单词",
                                size=14,
                                weight=ft.FontWeight.BOLD,
                            ),
                            self.word_count,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        controls=[self.search_box, self.sort_dropdown],
                        spacing=8,
                    ),
                    self.word_list,
                ],
            ),
        )

        self.root = ft.Tabs(
            length=2,
            selected_index=0,
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="添加"),
                            ft.Tab(label="词库"),
                        ]
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[add_page, library_page],
                    ),
                ],
            ),
        )

    # ---------------- 解析与添加 ----------------

    async def on_parse(self) -> None:
        if self._busy:
            return
        words = parse_input_text(self.input_box.value)
        if not words:
            self.ctx.snack("没有识别到有效单词，请检查输入", error=True)
            return
        if len(words) > 50:
            self.overflow = words[50:]
            words = words[:50]
            self.want_examples.value = False
            self.page.update()
            self.ctx.snack(
                f"共识别 {len(words) + len(self.overflow)} 个，预览前 50 个；"
                "其余将在确认添加时自动翻译入库（已关闭例句以提速）"
            )
        else:
            self.overflow = []

        self._busy = True
        self.parse_button.disabled = True
        self.parse_progress.visible = True
        self.pending = []
        self.page.update()
        try:
            for i, word in enumerate(words, start=1):
                self.status_text.value = f"正在查询 {i}/{len(words)}：{word}"
                self.page.update()
                result = await asyncio.to_thread(
                    self.provider.lookup, word, bool(self.want_examples.value)
                )
                box = ft.TextField(
                    value=meanings_to_text(result.meanings),
                    multiline=True,
                    min_lines=2,
                    max_lines=5,
                    dense=True,
                    text_size=14,
                )
                self.pending.append(
                    {"word": word, "result": result, "box": box}
                )
            self._rebuild_preview()
            matched = sum(1 for p in self.pending if p["result"].ok)
            self.status_text.value = (
                f"解析完成：{len(self.pending)} 个词，{matched} 个匹配到释义"
                + (f"，另有 {len(self.overflow)} 个待自动处理" if self.overflow else "")
            )
            self.confirm_button.visible = bool(self.pending or self.overflow)
            self.confirm_count.value = (
                f"将添加 {len(self.pending) + len(self.overflow)} 个"
            )
        finally:
            self._busy = False
            self.parse_button.disabled = False
            self.parse_progress.visible = False
            self.page.update()

    def _rebuild_preview(self) -> None:
        controls = []
        for index, item in enumerate(self.pending):
            result = item["result"]
            label = SOURCE_LABELS.get(result.source, "未匹配")
            color = SOURCE_COLORS.get(result.source, "#9AA0AC")
            meanings_preview = (item["box"].value or "").strip() or "未匹配，点击补充释义"
            card = ft.Card(
                content=ft.Container(
                    padding=10,
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        item["word"],
                                        size=15,
                                        weight=ft.FontWeight.BOLD,
                                        expand=True,
                                    ),
                                    ft.Container(
                                        content=ft.Text(
                                            label, size=11, color=ft.Colors.WHITE
                                        ),
                                        bgcolor=color,
                                        padding=ft.Padding(6, 2, 6, 2),
                                        border_radius=8,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.CLOSE,
                                        icon_size=18,
                                        tooltip="移除",
                                        on_click=lambda e, i=index: self.remove_pending(i),
                                    ),
                                ]
                            ),
                            ft.Text(
                                uk_phonetic(result.phonetic),
                                size=12,
                                color=ft.Colors.GREY_700,
                            )
                            if result.phonetic
                            else ft.Container(),
                            ft.Container(
                                content=ft.Text(
                                    meanings_preview,
                                    size=13,
                                    color=ft.Colors.GREY_800,
                                    max_lines=3,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                padding=ft.Padding(8, 6, 8, 6),
                                border=all_border(ft.Colors.GREY_300),
                                border_radius=8,
                                on_click=lambda e, i=index: self.open_meaning_editor(i),
                            ),
                            ft.Text(
                                "点击上方释义区域可编辑",
                                size=11,
                                color=ft.Colors.GREY_600,
                            ),
                        ],
                    ),
                )
            )
            controls.append(card)
        self.preview_list.controls = controls
        self.preview_list.visible = bool(self.pending)
        self.page.update()

    def open_meaning_editor(self, index: int) -> None:
        if not (0 <= index < len(self.pending)):
            return
        item = self.pending[index]
        editor = ft.TextField(
            value=item["box"].value,
            multiline=True,
            min_lines=8,
            max_lines=16,
            autofocus=True,
            label="释义（词性. 意思，每行一条）",
            text_size=16,
        )

        def save(_):
            item["box"].value = editor.value
            self.page.pop_dialog()
            self._rebuild_preview()

        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text(item["word"]),
            content=ft.Container(content=editor),
            actions=[
                ft.TextButton(
                    content=ft.Text("取消"),
                    on_click=lambda e: self.page.pop_dialog(),
                ),
                ft.FilledButton(content=ft.Text("保存释义"), on_click=save),
            ],
        )
        self.page.show_dialog(dialog)

    def remove_pending(self, index: int) -> None:
        if 0 <= index < len(self.pending):
            self.pending.pop(index)
            self._rebuild_preview()
            self.confirm_count.value = (
                f"将添加 {len(self.pending) + len(self.overflow)} 个"
            )
            self.confirm_button.visible = bool(self.pending or self.overflow)
            self.page.update()

    async def on_confirm(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.parse_button.disabled = True
        self.confirm_button.disabled = True
        learn_mode = self.learn_mode_dropdown.value or "write"
        try:
            to_add: list[tuple[str, str, list[Meaning], list[Example], str]] = []
            for item in self.pending:
                result = item["result"]
                meanings = parse_meaning_lines(item["box"].value)
                to_add.append(
                    (
                        item["word"],
                        result.phonetic,
                        meanings,
                        result.examples,
                        result.source if result.ok else "manual",
                    )
                )
            for i, word in enumerate(self.overflow, start=1):
                self.status_text.value = (
                    f"正在处理剩余 {i}/{len(self.overflow)}：{word}"
                )
                self.page.update()
                result = await asyncio.to_thread(
                    self.provider.lookup, word, bool(self.want_examples.value)
                )
                to_add.append(
                    (
                        word,
                        result.phonetic,
                        result.meanings,
                        result.examples,
                        result.source if result.ok else "manual",
                    )
                )

            added = dup = 0
            for word, phonetic, meanings, examples, source in to_add:
                created = self.db.add_word(
                    word=word,
                    phonetic=phonetic,
                    meanings=meanings,
                    examples=examples,
                    source=source,
                    learn_mode=learn_mode,
                )
                if created:
                    added += 1
                else:
                    dup += 1

            self.input_box.value = ""
            self.pending = []
            self.overflow = []
            self.preview_list.controls = []
            self.preview_list.visible = False
            self.status_text.value = ""
            self.confirm_button.visible = False
            self.confirm_count.value = ""
            self.ctx.snack(f"已添加 {added} 个单词，跳过重复 {dup} 个")
            self.refresh_word_list()
            self.ctx.notify_data_changed()
        finally:
            self._busy = False
            self.parse_button.disabled = False
            self.confirm_button.disabled = False
            self.page.update()

    # ---------------- 单词列表 ----------------

    def on_search_change(self, value: str) -> None:
        self.search_query = value or ""
        if self._search_task is not None:
            self._search_task.cancel()
        self._search_task = self.page.run_task(self._debounced_search)

    async def _debounced_search(self) -> None:
        await asyncio.sleep(0.25)
        self.refresh_word_list()

    def on_sort_change(self, value: str) -> None:
        self.sort_key = value or "time_desc"
        self.refresh_word_list()

    def refresh_word_list(self) -> None:
        words = self.db.search_words(self.search_query, self.sort_key)
        self.word_count.value = f"共 {len(words)} 个"
        controls = []
        for w in words:
            controls.append(self._word_tile(w))
        self.word_list.controls = controls
        self.page.update()

    def _word_tile(self, w: Word) -> ft.Control:
        phonetic = uk_phonetic(w.phonetic)
        meanings_text = "；".join(
            f"{m.pos} {m.text}".strip() if m.pos else m.text
            for m in w.meanings
        )
        if not meanings_text:
            meanings_text = "（暂无释义，点击编辑补充）"
        mode_label = "写作" if w.learn_mode == "write" else "阅读"
        tile = ft.Card(
            content=ft.Container(
                padding=ft.Padding(12, 10, 6, 10),
                on_click=lambda e, wid=w.id: self.open_edit_dialog(wid),
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Row(
                            spacing=6,
                            controls=[
                                ft.Text(
                                    w.word,
                                    size=16,
                                    weight=ft.FontWeight.W_600,
                                    expand=True,
                                ),
                                ft.Container(
                                    content=ft.Text(
                                        mode_label,
                                        size=11,
                                        color=ft.Colors.WHITE,
                                    ),
                                    bgcolor=(
                                        "#5B67F1"
                                        if w.learn_mode == "write"
                                        else "#3E8BD9"
                                    ),
                                    padding=ft.Padding(6, 2, 6, 2),
                                    border_radius=8,
                                ),
                                ft.Text(
                                    phonetic,
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                )
                                if phonetic
                                else ft.Container(),
                                ft.IconButton(
                                    icon=ft.Icons.EDIT,
                                    icon_size=18,
                                    tooltip="编辑",
                                    on_click=lambda e, wid=w.id: self.open_edit_dialog(wid),
                                ),
                            ],
                        ),
                        ft.Text(
                            meanings_text,
                            size=13,
                            color=ft.Colors.GREY_800,
                        ),
                        ft.Text(
                            f"添加于 {w.created_at[:16]}",
                            size=11,
                            color=ft.Colors.GREY_600,
                        ),
                    ],
                ),
            )
        )
        return tile

    # ---------------- 编辑 / 删除 ----------------

    def open_edit_dialog(self, word_id: int) -> None:
        w = self.db.get_word(word_id)
        if w is None:
            return
        word_box = ft.TextField(label="单词", value=w.word)
        phonetic_box = ft.TextField(label="音标", value=uk_phonetic(w.phonetic))
        meanings_box = ft.TextField(
            label="释义（词性. 意思，每行一条）",
            value=meanings_to_text(w.meanings),
            multiline=True,
            min_lines=3,
            max_lines=8,
        )
        examples_box = ft.TextField(
            label="例句（英文 || 中文，每行一条）",
            value=examples_to_text(w.examples),
            multiline=True,
            min_lines=2,
            max_lines=8,
        )
        learn_mode_box = ft.Dropdown(
            label="学习类型",
            value=w.learn_mode or "write",
            options=[
                ft.dropdown.Option("write", "写作型（会拼写）"),
                ft.dropdown.Option("read", "阅读型（认识即可）"),
            ],
        )

        def save(_):
            ok = self.db.update_word(
                word_id,
                word_box.value,
                phonetic_box.value,
                parse_meaning_lines(meanings_box.value),
                parse_example_lines(examples_box.value),
                learn_mode_box.value or "write",
            )
            if not ok:
                self.ctx.snack("保存失败：单词为空或与已有单词重复", error=True)
                return
            self.page.pop_dialog()
            self.refresh_word_list()
            self.ctx.notify_data_changed()
            self.ctx.snack("已保存修改")

        def confirm_delete(_):
            self.page.pop_dialog()
            self.db.delete_word(word_id)
            self.page.pop_dialog()
            self.refresh_word_list()
            self.ctx.notify_data_changed()
            self.ctx.snack(f"已删除 {w.word}")

        def reset_progress(_):
            self.page.pop_dialog()
            self.db.reset_word_progress(word_id)
            self.ctx.snack("已重置学习进度，该词将按新词重新学习")

        confirm = ft.AlertDialog(
            modal=True,
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定删除「{w.word}」吗？其学习记录也会一并删除。"),
            actions=[
                ft.TextButton(
                    content=ft.Text("取消"),
                    on_click=lambda e: self.page.pop_dialog(),
                ),
                ft.FilledButton(
                    content=ft.Text("删除"),
                    style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700),
                    on_click=confirm_delete,
                ),
            ],
        )
        confirm_reset = ft.AlertDialog(
            modal=True,
            title=ft.Text("重置学习进度"),
            content=ft.Text("确定把该词的学习进度清零、按新词重新开始吗？"),
            actions=[
                ft.TextButton(
                    content=ft.Text("取消"),
                    on_click=lambda e: self.page.pop_dialog(),
                ),
                ft.FilledButton(
                    content=ft.Text("重置"),
                    on_click=reset_progress,
                ),
            ],
        )

        delete_button = ft.TextButton(
            content=ft.Text("删除"),
            on_click=lambda e: self.page.show_dialog(confirm),
        )
        reset_button = ft.TextButton(
            content=ft.Text("重置进度"),
            on_click=lambda e: self.page.show_dialog(confirm_reset),
        )
        cancel_button = ft.TextButton(
            content=ft.Text("取消"),
            on_click=lambda e: self.page.pop_dialog(),
        )
        save_button = ft.FilledButton(content=ft.Text("保存"), on_click=save)

        content_height = 480
        if self.page.height:
            content_height = min(max(int(self.page.height * 0.62), 360), 560)

        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text("编辑单词"),
            content=ft.Container(
                height=content_height,
                content=ft.Column(
                    scroll=ft.ScrollMode.AUTO,
                    spacing=10,
                    controls=[
                        word_box,
                        phonetic_box,
                        meanings_box,
                        examples_box,
                        learn_mode_box,
                        ft.Text(
                            f"添加时间：{w.created_at}",
                            size=12,
                            color=ft.Colors.GREY_700,
                        ),
                    ],
                ),
            ),
            actions=[
                ft.Row(
                    wrap=True,
                    spacing=8,
                    run_spacing=6,
                    controls=[
                        delete_button,
                        reset_button,
                        cancel_button,
                        save_button,
                    ],
                ),
            ],
        )
        self.page.show_dialog(dialog)

    # ---------------- 生命周期 ----------------

    def on_show(self) -> None:
        self.refresh_word_list()

    def on_data_changed(self) -> None:
        self.refresh_word_list()
