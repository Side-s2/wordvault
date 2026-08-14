"""界面三：详细统计（总学习量、趋势、正确率、熟练度分布、队列概况）。"""

from __future__ import annotations

from datetime import datetime

import flet as ft
import flet.canvas as cv

from wordvault.theme import INFO, PRIMARY, SUCCESS, TIER_COLORS


class StatsView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page = ctx.page
        self.db = ctx.db
        self.content = ft.Container(expand=True, padding=8)
        self.root = self.content
        self.refresh()

    def refresh(self) -> None:
        volume = self.db.total_volume()
        series = self.db.daily_series(30)
        streak = self.db.streak()
        dist = self.db.proficiency_distribution()
        overview = self.db.due_overview()
        total_words = self.db.count_words()

        today = series[-1]
        today_accuracy = (
            today["correct"] / today["reviews"] * 100 if today["reviews"] else 0.0
        )
        all_accuracy = (
            volume["correct"] / volume["total"] * 100 if volume["total"] else 0.0
        )
        added_30 = sum(d["added"] for d in series)

        self.content.content = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=10,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            "学习统计",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            tooltip="刷新",
                            on_click=lambda e: self.refresh(),
                        ),
                    ]
                ),
                ft.Row(
                    controls=[
                        self._metric("总学习量", str(volume["total"]), PRIMARY),
                        self._metric(
                            "累计正确率",
                            f"{all_accuracy:.0f}%",
                            INFO,
                        ),
                        self._metric("连续打卡", f"{streak} 天", SUCCESS),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    controls=[
                        self._metric("今日复习", str(today["reviews"]), PRIMARY),
                        self._metric(
                            "今日正确率", f"{today_accuracy:.0f}%", INFO
                        ),
                        self._metric("词库总数", str(total_words), SUCCESS),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    controls=[
                        self._metric("近30天新增", str(added_30), "#E8A13D"),
                        self._metric(
                            "今日待复习",
                            str(overview["due_today"]),
                            "#D9534F",
                        ),
                        self._metric(
                            "新词待学习",
                            str(overview["new_today"]),
                            "#3E8BD9",
                        ),
                    ],
                    spacing=8,
                ),
                self._section_card(
                    "近 30 天复习量",
                    self._bar_chart(series),
                ),
                self._section_card(
                    "近 30 天正确率（%）",
                    self._line_chart(series),
                ),
                self._section_card(
                    "熟练度分布",
                    self._distribution_chart(dist),
                ),
                self._section_card(
                    "复习队列",
                    ft.Column(
                        spacing=6,
                        controls=[
                            self._kv_row(
                                "未来 7 天预计到期", f"{overview['due_next_week']} 个"
                            ),
                            self._kv_row(
                                "今日到期复习", f"{overview['due_today']} 个"
                            ),
                            self._kv_row(
                                "未开始的新词", f"{overview['new_today']} 个"
                            ),
                            ft.Text(
                                "数据实时更新；未复习的词会自动顺延，不会丢失。",
                                size=12,
                                color=ft.Colors.GREY_600,
                            ),
                        ],
                    ),
                ),
            ],
        )
        self.page.update()

    # ---------------- 小部件 ----------------

    def _metric(self, title: str, value: str, color: str) -> ft.Control:
        return ft.Card(
            expand=True,
            content=ft.Container(
                padding=10,
                content=ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(title, size=11, color=ft.Colors.GREY_600),
                        ft.Text(
                            value,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                            color=color,
                        ),
                    ],
                ),
            ),
        )

    def _section_card(self, title: str, child: ft.Control) -> ft.Control:
        return ft.Card(
            content=ft.Container(
                padding=12,
                content=ft.Column(
                    spacing=10,
                    controls=[
                        ft.Text(
                            title,
                            size=15,
                            weight=ft.FontWeight.BOLD,
                        ),
                        child,
                    ],
                ),
            )
        )

    def _kv_row(self, label: str, value: str) -> ft.Control:
        return ft.Row(
            controls=[
                ft.Text(label, size=13, color=ft.Colors.GREY_700, expand=True),
                ft.Text(value, size=13, weight=ft.FontWeight.W_600),
            ]
        )

    def _bar_chart(self, series: list[dict]) -> ft.Control:
        max_value = max((d["reviews"] for d in series), default=0)
        if max_value <= 0:
            return ft.Text("暂无复习数据，先添加单词开始学习吧", size=13)
        bars = []
        for i, day in enumerate(series):
            value = day["reviews"]
            height = max(4.0, value / max_value * 96.0) if value else 2.0
            color = PRIMARY if value else ft.Colors.GREY_300
            label = f"{day['date'][5:]}：{value} 个"
            bars.append(
                ft.Container(
                    width=8,
                    height=height,
                    bgcolor=color,
                    border_radius=ft.BorderRadius.only(
                        top_left=3, top_right=3
                    ),
                    tooltip=label,
                )
            )
        start = series[0]["date"][5:]
        end = series[-1]["date"][5:]
        return ft.Column(
            spacing=4,
            controls=[
                ft.Row(
                    controls=bars,
                    alignment=ft.MainAxisAlignment.START,
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                ),
                ft.Row(
                    controls=[
                        ft.Text(start, size=10, color=ft.Colors.GREY_600),
                        ft.Text(
                            f"最多 {max_value} 个",
                            size=10,
                            color=ft.Colors.GREY_600,
                            expand=True,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(end, size=10, color=ft.Colors.GREY_600),
                    ]
                ),
            ],
        )

    def _line_chart(self, series: list[dict]) -> ft.Control:
        points = [
            (i, d["correct"] / d["reviews"] * 100)
            for i, d in enumerate(series)
            if d["reviews"] > 0
        ]
        if len(points) < 2:
            return ft.Text("数据不足，暂无法绘制趋势", size=13)

        width, height = 340, 150
        left, right, top, bottom = 8, 332, 12, 132
        n = len(series)

        def x_of(i: int) -> float:
            return left + i * (right - left) / max(n - 1, 1)

        def y_of(acc: float) -> float:
            return bottom - (acc / 100.0) * (bottom - top)

        shapes: list = []
        for y_pct in (0, 50, 100):
            y = y_of(y_pct)
            shapes.append(
                cv.Line(
                    left,
                    y,
                    right,
                    y,
                    paint=ft.Paint(
                        color="#E5E7EB",
                        stroke_width=1,
                        style=ft.PaintingStyle.STROKE,
                    ),
                )
            )

        for a, b in zip(points, points[1:]):
            shapes.append(
                cv.Line(
                    x_of(a[0]),
                    y_of(a[1]),
                    x_of(b[0]),
                    y_of(b[1]),
                    paint=ft.Paint(
                        color=INFO,
                        stroke_width=2,
                        style=ft.PaintingStyle.STROKE,
                        anti_alias=True,
                    ),
                )
            )
        for i, acc in points:
            shapes.append(
                cv.Circle(
                    x_of(i),
                    y_of(acc),
                    3,
                    paint=ft.Paint(
                        color=INFO,
                        style=ft.PaintingStyle.FILL,
                        anti_alias=True,
                    ),
                )
            )

        best = max(p[1] for p in points)
        worst = min(p[1] for p in points)
        canvas = cv.Canvas(shapes=shapes, width=width, height=height)
        return ft.Column(
            spacing=4,
            controls=[
                canvas,
                ft.Text(
                    f"最高 {best:.0f}% · 最低 {worst:.0f}% · 仅统计有复习的天数",
                    size=10,
                    color=ft.Colors.GREY_600,
                ),
            ],
        )

    def _distribution_chart(self, dist: dict[str, int]) -> ft.Control:
        total = sum(dist.values())
        if total <= 0:
            return ft.Text("词库为空", size=13)
        order = ["已掌握", "熟练", "学习中", "生疏", "未开始"]
        segments = []
        for name in order:
            count = dist.get(name, 0)
            if count <= 0:
                continue
            width = max(2.0, count / total * 300.0)
            segments.append(
                ft.Container(
                    width=width,
                    height=16,
                    bgcolor=TIER_COLORS[name],
                )
            )
        legend = []
        for name in order:
            count = dist.get(name, 0)
            pct = count / total * 100 if total else 0.0
            legend.append(
                ft.Row(
                    controls=[
                        ft.Container(
                            width=10,
                            height=10,
                            bgcolor=TIER_COLORS[name],
                            border_radius=5,
                        ),
                        ft.Text(name, size=12, expand=True),
                        ft.Text(
                            f"{count} 个 · {pct:.0f}%",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                    ]
                )
            )
        return ft.Column(
            spacing=8,
            controls=[
                ft.Row(controls=segments, spacing=0),
                ft.Column(controls=legend, spacing=4),
            ],
        )

    def on_show(self) -> None:
        self.refresh()

    def on_data_changed(self) -> None:
        pass
