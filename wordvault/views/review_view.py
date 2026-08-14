"""界面二：单词复习（四选一为主，词库不足时降级为自评）。"""

from __future__ import annotations

import random
import time

import flet as ft

from wordvault.db import Database, Word
from wordvault.dict_provider import uk_phonetic
from wordvault.scheduler import apply_review, build_queue, tier_of
from wordvault.theme import SUCCESS, DANGER


class ReviewView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page = ctx.page
        self.db: Database = ctx.db

        self.mode = "idle"  # idle / session / finish
        self.queue: list[int] = []
        self.index = 0
        self.requeued: set[int] = set()
        self.correct_cnt = 0
        self.wrong_cnt = 0
        self.answered = False
        self.correct_text = ""
        self.options: list[str] | None = None
        self.last_choice = ""
        self.last_answer_text = ""
        self.question_at = 0.0

        self.content = ft.Container(expand=True, padding=8)
        self.root = self.content
        self._render_idle()

    # ---------------- 渲染 ----------------

    def _render_idle(self) -> None:
        overview = self.db.due_overview()
        new_limit = self.db.get_int_setting("new_daily_limit", 20)
        total_limit = self.db.get_int_setting("review_daily_limit", 100)
        streak = self.db.streak()
        pending = min(overview["new_today"], new_limit) + overview["due_today"]
        pending = min(pending, total_limit) if overview["new_today"] else min(
            overview["due_today"], total_limit
        )

        start_button = ft.FilledButton(
            content=ft.Text("开始复习"),
            icon=ft.Icons.ARROW_FORWARD,
            height=52,
            on_click=lambda e: self.start_session(),
            disabled=pending <= 0,
        )
        self.content.content = ft.Column(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.SCHOOL, size=64, color=ft.Colors.PRIMARY),
                ft.Text("今日复习", size=28, weight=ft.FontWeight.BOLD),
                ft.Text(
                    f"待复习 {overview['due_today']} 个 · 新词 {min(overview['new_today'], new_limit)} 个",
                    size=15,
                    color=ft.Colors.GREY_700,
                ),
                ft.Text(
                    f"连续打卡 {streak} 天",
                    size=13,
                    color=ft.Colors.GREY_600,
                ),
                ft.Container(height=16),
                start_button,
                ft.Container(
                    content=ft.Text(
                        f"每日上限：新词 {new_limit} · 复习 {total_limit}（可在设置中调整）",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    margin=ft.Margin(0, 12, 0, 0),
                ),
            ],
        )
        self.page.update()

    def start_session(self) -> None:
        new_limit = self.db.get_int_setting("new_daily_limit", 20)
        total_limit = self.db.get_int_setting("review_daily_limit", 100)
        queue = build_queue(self.db, new_limit, total_limit)
        self.queue = queue["new"] + queue["review"]
        if not self.queue:
            self.ctx.snack("今天没有需要复习的单词")
            return
        self.mode = "session"
        self.index = 0
        self.requeued = set()
        self.correct_cnt = 0
        self.wrong_cnt = 0
        self._render_question()

    def _render_question(self) -> None:
        self.answered = False
        self.last_choice = ""
        self.question_at = time.monotonic()
        word_id = self.queue[self.index]
        word, _state = self.db.word_with_state(word_id)
        self.current_word = word
        self.options = self._make_options(word)
        self.correct_text = self._correct_option_text(word)

        header = ft.Column(
            spacing=6,
            controls=[
                ft.Text(
                    f"第 {self.index + 1} / {len(self.queue)} 题",
                    size=13,
                    color=ft.Colors.GREY_700,
                ),
                ft.ProgressBar(
                    value=self.index / max(len(self.queue), 1),
                    bar_height=6,
                ),
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Text(
                                f"✓ {self.correct_cnt}",
                                size=13,
                                color=SUCCESS,
                                weight=ft.FontWeight.BOLD,
                            ),
                            padding=ft.Padding(10, 3, 10, 3),
                            border_radius=10,
                            bgcolor="#E6F4EC",
                        ),
                        ft.Container(
                            content=ft.Text(
                                f"✗ {self.wrong_cnt}",
                                size=13,
                                color=DANGER,
                                weight=ft.FontWeight.BOLD,
                            ),
                            padding=ft.Padding(10, 3, 10, 3),
                            border_radius=10,
                            bgcolor="#FBE9E7",
                        ),
                    ],
                    spacing=8,
                ),
            ],
        )

        question = ft.Container(
            padding=ft.Padding(16, 26, 16, 26),
            alignment=ft.Alignment.CENTER,
            content=ft.Text(
                word.word,
                size=30,
                weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER,
            ),
        )

        if self.options:
            option_buttons = []
            for option in self.options:
                option_buttons.append(
                    ft.OutlinedButton(
                        content=ft.Text(
                            option, size=14, text_align=ft.TextAlign.CENTER
                        ),
                        expand=True,
                        data=option,
                        on_click=lambda e, opt=option: self.on_answer(opt),
                    )
                )
            option_buttons.append(
                ft.TextButton(
                    content=ft.Text("不认识", size=13),
                    expand=True,
                    data="__dont__",
                    on_click=lambda e: self.on_answer("__dont__"),
                )
            )
            answer_area = ft.Column(controls=option_buttons, spacing=8)
        else:
            answer_area = ft.Row(
                controls=[
                    ft.FilledButton(
                        content=ft.Text("认识"),
                        expand=True,
                        height=46,
                        style=ft.ButtonStyle(bgcolor=SUCCESS),
                        on_click=lambda e: self.on_answer("__know__"),
                    ),
                    ft.OutlinedButton(
                        content=ft.Text("不认识"),
                        expand=True,
                        height=46,
                        on_click=lambda e: self.on_answer("__dont__"),
                    ),
                ],
                spacing=10,
            )

        self.prompt_text = (
            ft.Text("请选择正确的中文意思", size=13, color=ft.Colors.GREY_600)
            if self.options
            else ft.Text("这个词你认识吗？", size=13, color=ft.Colors.GREY_600)
        )
        self.reveal_area = ft.Container(
            expand=True, padding=ft.Padding(12, 10, 12, 10)
        )
        self.summary_area = ft.Container(visible=False)
        self.next_button = ft.FilledButton(
            content=ft.Text("下一个 ▶"),
            height=48,
            visible=False,
            on_click=lambda e: self.next_question(),
        )
        self.answer_buttons = answer_area
        self.content.content = ft.Column(
            expand=True,
            spacing=8,
            controls=[
                header,
                question,
                self.prompt_text,
                answer_area,
                self.summary_area,
                self.reveal_area,
                self.next_button,
            ],
        )
        self.page.update()

    @staticmethod
    def _correct_option_text(word: Word) -> str:
        parts = []
        for m in word.meanings[:3]:
            label = f"{m.pos} {m.text}".strip() if m.pos else m.text
            if label:
                parts.append(label)
        return "；".join(parts)

    def _make_options(self, word: Word) -> list[str] | None:
        """构造同构的四个选项：正确答案保留完整释义，干扰项也拼接多条
        其他单词的“词性+释义”，使长度和结构相近，避免一眼看出答案。"""
        labels = []
        for m in word.meanings[:3]:
            label = f"{m.pos} {m.text}".strip() if m.pos else m.text
            if label:
                labels.append(label)
        if not labels:
            return None
        correct = "；".join(labels)
        correct_texts = {m.text.strip() for m in word.meanings}

        pool: list[str] = []
        for other in self.db.list_words():
            if other.id == word.id:
                continue
            for m in other.meanings:
                text = m.text.strip()
                if not text or text in correct_texts:
                    continue
                label = f"{m.pos} {m.text}".strip() if m.pos else m.text
                if label and label not in pool:
                    pool.append(label)
        if len(pool) < 3:
            return None

        random.shuffle(pool)
        n = len(labels)
        target = len(correct)
        distractors: list[str] = []
        used: set[str] = set()
        attempts = 0
        while len(distractors) < 3 and attempts < 300:
            attempts += 1
            avail = [p for p in pool if p not in used] or pool
            k = min(n, len(avail))
            combo = random.sample(avail, k)
            text = "；".join(combo)
            if text == correct or text in distractors:
                continue
            total = sum(len(p) for p in combo) + max(k - 1, 0)
            if abs(total - target) <= 24 or attempts > 180:
                distractors.append(text)
                used.update(combo)
        if len(distractors) < 3:
            return None

        options = [correct] + distractors
        random.shuffle(options)
        return options

    # ---------------- 作答 ----------------

    def on_answer(self, choice: str) -> None:
        if self.answered:
            return
        self.answered = True
        self.last_choice = choice

        if self.options:
            if choice == "__dont__":
                is_correct = False
                answer_text = "不认识"
            else:
                is_correct = choice == self.correct_text
                answer_text = choice
            result = "correct" if is_correct else "wrong"
        else:
            is_correct = choice == "__know__"
            result = "correct" if is_correct else "wrong"
            answer_text = "认识" if is_correct else "不认识"

        self.last_answer_text = answer_text
        if is_correct:
            self.correct_cnt += 1
        else:
            self.wrong_cnt += 1

        word_id = self.queue[self.index]
        state = self.db.ensure_state(word_id)
        new_state = apply_review(state, result)
        ms = int((time.monotonic() - self.question_at) * 1000)
        self.db.save_review(
            word_id=word_id,
            state=new_state,
            result=result,
            answer=answer_text,
            correct_answer=self.correct_text or answer_text,
            ms=ms,
            mode="choice" if self.options else "self",
            reviewed_at=new_state["last_reviewed_at"],
        )

        if not is_correct and word_id not in self.requeued:
            self.requeued.add(word_id)
            self.queue.append(word_id)

        self._show_reveal(is_correct)

    def _show_reveal(self, is_correct: bool) -> None:
        word = self.current_word
        banner = ft.Container(
            padding=ft.Padding(14, 10, 14, 10),
            border_radius=12,
            bgcolor="#E6F4EC" if is_correct else "#FBE9E7",
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if is_correct else ft.Icons.CANCEL,
                        color=SUCCESS if is_correct else DANGER,
                        size=22,
                    ),
                    ft.Column(
                        spacing=1,
                        controls=[
                            ft.Text(
                                "答对了！" if is_correct else "答错了",
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=SUCCESS if is_correct else DANGER,
                            ),
                            *(
                                [
                                    ft.Text(
                                        f"你的选择：{self.last_answer_text}",
                                        size=12,
                                        color=ft.Colors.GREY_700,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    )
                                ]
                                if not is_correct
                                else []
                            ),
                        ],
                    ),
                ]
            ),
        )

        meaning_lines = [
            ft.Text(
                f"{m.pos} {m.text}".strip() if m.pos else m.text,
                size=16,
            )
            for m in word.meanings
        ]
        if not meaning_lines:
            meaning_lines = [ft.Text("（暂无释义，可到单词页补充）", size=14)]

        reveal_controls: list[ft.Control] = []
        if word.phonetic:
            reveal_controls.append(
                ft.Text(
                    uk_phonetic(word.phonetic),
                    size=14,
                    color=ft.Colors.GREY_600,
                )
            )
        reveal_controls.append(
            ft.Text(
                "释义",
                size=13,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREY_700,
            )
        )
        reveal_controls.extend(meaning_lines)
        if word.examples:
            reveal_controls.append(
                ft.Text(
                    "例句",
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREY_700,
                )
            )
            for ex in word.examples[:3]:
                reveal_controls.append(
                    ft.Text(
                        f"{ex.en}\n{ex.zh}",
                        size=14,
                        color=ft.Colors.GREY_800,
                    )
                )

        self.reveal_area.content = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=8,
            controls=reveal_controls,
        )
        self.summary_area.content = banner
        self.summary_area.visible = True
        self.answer_buttons.visible = False
        self.prompt_text.visible = False
        self.next_button.content = ft.Text(
            "下一个 ▶" if self.index + 1 < len(self.queue) else "查看结果"
        )
        self.next_button.visible = True

        self.page.update()

    def next_question(self) -> None:
        self.index += 1
        if self.index >= len(self.queue):
            self._render_finish()
        else:
            self._render_question()

    def _render_finish(self) -> None:
        self.mode = "finish"
        total = self.correct_cnt + self.wrong_cnt
        accuracy = (self.correct_cnt / total * 100) if total else 0.0
        overview = self.db.due_overview()
        remaining = overview["due_today"] + overview["new_today"]
        self.content.content = ft.Column(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            controls=[
                ft.Icon(ft.Icons.EMOJI_EVENTS, size=64, color="#E8A13D"),
                ft.Text("本次复习完成！", size=24, weight=ft.FontWeight.BOLD),
                ft.Text(f"共 {total} 题", size=16),
                ft.Text(
                    f"正确 {self.correct_cnt} · 错误 {self.wrong_cnt} · "
                    f"正确率 {accuracy:.0f}%",
                    size=16,
                ),
                ft.Text(
                    f"今日队列还剩约 {remaining} 个（超额部分已顺延）",
                    size=13,
                    color=ft.Colors.GREY_600,
                ),
                ft.Container(height=8),
                ft.FilledButton(
                    content=ft.Text("再来一组"),
                    icon=ft.Icons.REFRESH,
                    height=48,
                    on_click=lambda e: self.start_session(),
                ),
                ft.OutlinedButton(
                    content=ft.Text("回到今日概览"),
                    height=44,
                    on_click=lambda e: self._go_idle(),
                ),
            ],
        )
        self.page.update()
        self.ctx.notify_data_changed()

    def _go_idle(self) -> None:
        self.mode = "idle"
        self._render_idle()

    # ---------------- 生命周期 ----------------

    def on_show(self) -> None:
        if self.mode == "idle":
            self._render_idle()

    def on_data_changed(self) -> None:
        if self.mode == "idle":
            self._render_idle()
