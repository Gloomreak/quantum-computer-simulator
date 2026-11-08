"""Столбчатые и линейные графики в PNG (Pillow).

Функции возвращают готовые PNG-байты. Изображение рисуется с
двукратным суперсэмплингом и уменьшается методом LANCZOS, поэтому
линии и подписи выглядят сглаженными без внешних библиотек.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from PIL import Image, ImageDraw

from .theme import (
    COLORS,
    SCALE,
    dashed_line,
    draw_text,
    finish_canvas,
    font,
    format_number,
    format_percent,
    nice_ticks,
    text_size,
)


@dataclass
class BarSeries:
    """Набор столбцов с общим набором категорий."""

    name: str
    values: Sequence[float]
    color: str
    value_format: str = "percent"  # "percent" | "count" | "number"


@dataclass
class LineSeries:
    """Кривая с необязательными границами доверительного интервала."""

    name: str
    x: Sequence[float]
    y: Sequence[float]
    color: str
    low: Sequence[float] | None = None
    high: Sequence[float] | None = None
    markers: bool = True


@dataclass
class ReferenceLine:
    """Горизонтальная пунктирная линия (например, шумовой уровень)."""

    value: float
    label: str
    color: str = COLORS["accent"]


@dataclass
class ChartBox:
    """Границы области построения в пикселях итогового изображения."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _mix(color: str, other: str = "#FFFFFF", ratio: float = 0.5) -> str:
    """Смешать два цвета: ``ratio`` — доля первого цвета."""

    first = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
    second = tuple(int(other[index : index + 2], 16) for index in (1, 3, 5))
    mixed = tuple(int(first[i] * ratio + second[i] * (1 - ratio)) for i in range(3))
    return "#" + "".join(f"{value:02X}" for value in mixed)


def _draw_vertical_text(
    image: Image.Image,
    text: str,
    center: tuple[float, float],
    size: int,
    color: str,
    bold: bool = False,
) -> None:
    """Нарисовать повёрнутый на 90° текст (подпись оси Y)."""

    family = font(size, bold)
    chosen = family.bold if bold else family.regular
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    box = probe.textbbox((0, 0), text, font=chosen)
    width = box[2] - box[0] + 8 * SCALE
    height = box[3] - box[1] + 8 * SCALE
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.text(
        (4 * SCALE - box[0], 4 * SCALE - box[1]),
        text,
        font=chosen,
        fill=color,
    )
    rotated = layer.rotate(90, expand=True, resample=Image.BICUBIC)
    position = (
        int(center[0] * SCALE - rotated.width / 2),
        int(center[1] * SCALE - rotated.height / 2),
    )
    image.paste(rotated, position, rotated)


def _legend(
    draw: ImageDraw.ImageDraw,
    items: Sequence[tuple[str, str, bool]],
    right: float,
    top: float,
    size: int = 11,
) -> float:
    """Нарисовать горизонтальную легенду справа сверху.

    ``items`` — пары (подпись, цвет). Возвращает левую границу легенды.
    """

    family = font(size)
    x = right
    padding = 14 * SCALE
    for label, color, dashed in reversed(list(items)):
        width, height = text_size(draw, label, family)
        x -= width
        draw_text(
            draw,
            (x, top * SCALE + 1 * SCALE),
            label,
            family,
            fill=COLORS["muted"],
        )
        x -= 8 * SCALE
        if dashed:
            dashed_line(
                draw,
                (x - 14 * SCALE, top * SCALE + 8 * SCALE),
                (x, top * SCALE + 8 * SCALE),
                fill=color,
                dash=4 * SCALE,
                gap=3 * SCALE,
                thickness=2 * SCALE,
            )
        else:
            draw.rounded_rectangle(
                [x - 10 * SCALE, top * SCALE + 3 * SCALE, x, top * SCALE + 13 * SCALE],
                radius=2 * SCALE,
                fill=color,
            )
        x -= padding
    return x


def _legend_size(
    draw: ImageDraw.ImageDraw,
    items: Sequence[tuple[str, str, bool]],
    size: int = 11,
) -> float:
    """Ширина горизонтальной легенды в пикселях (до суперсэмплинга)."""

    family = font(size)
    total = 0.0
    for label, _color, dashed in items:
        total += text_size(draw, label, family)[0] / SCALE
        total += (14 if dashed else 10) + 8 + 14
    return total


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    family,
    max_width: float,
) -> str:
    """Обрезать текст многоточием, чтобы он поместился по ширине."""

    if not text:
        return text
    if text_size(draw, text, family)[0] <= max_width:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = text[:middle] + ellipsis
        if text_size(draw, candidate, family)[0] <= max_width:
            low = middle
        else:
            high = middle - 1
    return text[:low] + ellipsis if low > 0 else ""


def _empty_chart(width: int, height: int, title: str, message: str) -> bytes:
    """Заглушка для пустых данных."""

    image = Image.new("RGB", (width * SCALE, height * SCALE), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw_text(draw, (24 * SCALE, 20 * SCALE), title, font(16, True), COLORS["ink"], bold=True)
    draw_text(
        draw,
        (width * SCALE / 2, height * SCALE / 2),
        message,
        font(12),
        COLORS["muted"],
        anchor="mm",
    )
    return finish_canvas(image, width, height)


def bar_chart(
    categories: Sequence[str],
    series: Sequence[BarSeries],
    title: str,
    subtitle: str = "",
    x_label: str = "",
    y_label: str = "",
    width: int = 900,
    height: int = 430,
    show_value_labels: bool = False,
    y_max: float | None = None,
) -> bytes:
    """Сгруппированная столбчатая диаграмма.

    Parameters
    ----------
    categories : Sequence[str]
        Подписи категорий (например, битовые строки).
    series : Sequence[BarSeries]
        Один или несколько рядов данных (идеально / с шумом).
    show_value_labels : bool
        Подписывать ли значения над столбцами (уместно для одного ряда).
    """

    if not categories or not series:
        return _empty_chart(width, height, title, "Нет данных для отображения")

    image = Image.new("RGB", (width * SCALE, height * SCALE), COLORS["background"])
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        [0, 0, width * SCALE - 1, height * SCALE - 1],
        outline=COLORS["border"],
        width=1 * SCALE,
    )
    draw_text(draw, (24 * SCALE, 18 * SCALE), title, font(16, True), COLORS["ink"], bold=True)

    legend_items = [(item.name, item.color, False) for item in series if item.name]
    legend_width = _legend_size(draw, legend_items) if legend_items else 0.0
    if subtitle:
        available = (width - 24 - legend_width - 24) * SCALE
        draw_text(
            draw,
            (24 * SCALE, 44 * SCALE),
            _fit_text(draw, subtitle, font(10), available),
            font(10),
            COLORS["muted"],
        )
    if legend_items:
        _legend(draw, legend_items, (width - 24) * SCALE, 22 * SCALE)

    box = ChartBox(left=72, top=84, right=width - 26, bottom=height - 62)

    maximum = max(max(item.values) if len(item.values) else 0.0 for item in series)
    if y_max is not None:
        maximum = max(maximum, y_max)
    ticks = nice_ticks(maximum * 1.08 if maximum > 0 else 1.0)
    top_value = ticks[-1] if ticks[-1] > 0 else 1.0

    for tick in ticks:
        y = box.bottom - (tick / top_value) * box.height
        draw.line(
            [(box.left * SCALE, y * SCALE), (box.right * SCALE, y * SCALE)],
            fill=COLORS["grid"],
            width=1 * SCALE,
        )
        draw_text(
            draw,
            ((box.left - 10) * SCALE, y * SCALE),
            format_number(tick),
            font(9),
            COLORS["muted"],
            anchor="rm",
        )

    slot = box.width / len(categories)
    group_width = slot * 0.72
    gap = 2.0 if len(series) > 1 else 0.0
    bar_width = max(2.0, (group_width - gap * (len(series) - 1)) / len(series))
    label_size = 10
    while label_size > 7:
        widest = max(
            text_size(draw, label, font(label_size))[0] for label in categories
        )
        if widest <= slot * 0.92 * SCALE:
            break
        label_size -= 1
    label_family = font(label_size)

    for category_index, category in enumerate(categories):
        group_left = box.left + category_index * slot + (slot - group_width) / 2
        for series_index, item in enumerate(series):
            value = float(item.values[category_index]) if category_index < len(item.values) else 0.0
            bar_left = group_left + series_index * (bar_width + gap)
            bar_top = box.bottom - (value / top_value) * box.height
            if value > 0:
                draw.rectangle(
                    [
                        (bar_left * SCALE, bar_top * SCALE),
                        ((bar_left + bar_width) * SCALE, box.bottom * SCALE),
                    ],
                    fill=item.color,
                )
            else:
                draw.line(
                    [
                        (bar_left * SCALE, (box.bottom - 1) * SCALE),
                        ((bar_left + bar_width) * SCALE, (box.bottom - 1) * SCALE),
                    ],
                    fill=COLORS["border"],
                    width=2 * SCALE,
                )
            if show_value_labels and len(series) == 1 and value > 0:
                label = (
                    format_percent(value)
                    if item.value_format == "percent"
                    else (
                        f"{value:.0f}"
                        if item.value_format == "count"
                        else format_number(value)
                    )
                )
                draw_text(
                    draw,
                    (
                        (bar_left + bar_width / 2) * SCALE,
                        (bar_top - 5) * SCALE,
                    ),
                    label,
                    font(9),
                    COLORS["muted"],
                    anchor="ms",
                )

        draw_text(
            draw,
            (
                (box.left + category_index * slot + slot / 2) * SCALE,
                (box.bottom + 8) * SCALE,
            ),
            category,
            label_family,
            COLORS["muted"],
            anchor="mt",
        )

    draw.line(
        [(box.left * SCALE, box.bottom * SCALE), (box.right * SCALE, box.bottom * SCALE)],
        fill=COLORS["axis"],
        width=1 * SCALE,
    )

    if x_label:
        draw_text(
            draw,
            (box.left * SCALE + box.width * SCALE / 2, (height - 24) * SCALE),
            x_label,
            font(11),
            COLORS["muted"],
            anchor="mm",
        )
    if y_label:
        _draw_vertical_text(
            image,
            y_label,
            (20, (box.top + box.bottom) / 2),
            11,
            COLORS["muted"],
        )
    return finish_canvas(image, width, height)


def line_chart(
    series: Sequence[LineSeries],
    title: str,
    subtitle: str = "",
    x_label: str = "",
    y_label: str = "",
    reference: ReferenceLine | None = None,
    width: int = 900,
    height: int = 460,
    x_ticks: Sequence[float] | None = None,
    y_max: float | None = None,
) -> bytes:
    """Линейный график с маркерами и доверительными интервалами."""

    if not series or not any(len(item.x) for item in series):
        return _empty_chart(width, height, title, "Нет данных для отображения")

    image = Image.new("RGB", (width * SCALE, height * SCALE), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        [0, 0, width * SCALE - 1, height * SCALE - 1],
        outline=COLORS["border"],
        width=1 * SCALE,
    )
    draw_text(draw, (24 * SCALE, 18 * SCALE), title, font(16, True), COLORS["ink"], bold=True)

    legend_items = [(item.name, item.color, False) for item in series]
    if reference is not None:
        legend_items.append(
            (reference.label, _mix(reference.color, "#FFFFFF", 0.65), True)
        )
    legend_width = _legend_size(draw, legend_items)
    if subtitle:
        available = (width - 24 - legend_width - 24) * SCALE
        draw_text(
            draw,
            (24 * SCALE, 44 * SCALE),
            _fit_text(draw, subtitle, font(10), available),
            font(10),
            COLORS["muted"],
        )
    _legend(draw, legend_items, (width - 24) * SCALE, 22 * SCALE)

    box = ChartBox(left=76, top=92, right=width - 30, bottom=height - 66)

    all_x = [value for item in series for value in item.x]
    all_y = [value for item in series for value in item.y]
    if reference is not None:
        all_y.append(reference.value)
    for item in series:
        if item.high is not None:
            all_y.extend(item.high)
    x_min, x_max = min(all_x), max(all_x)
    if x_max == x_min:
        x_max = x_min + 1.0
    y_high = max(all_y) if all_y else 1.0
    if y_max is not None:
        y_high = max(y_high, y_max)
    ticks = nice_ticks(y_high * 1.12 if y_high > 0 else 1.0)
    top_value = ticks[-1] if ticks[-1] > 0 else 1.0

    for tick in ticks:
        y = box.bottom - (tick / top_value) * box.height
        draw.line(
            [(box.left * SCALE, y * SCALE), (box.right * SCALE, y * SCALE)],
            fill=COLORS["grid"],
            width=1 * SCALE,
        )
        draw_text(
            draw,
            ((box.left - 10) * SCALE, y * SCALE),
            format_number(tick),
            font(9),
            COLORS["muted"],
            anchor="rm",
        )

    tick_values: List[float]
    if x_ticks is not None and len(x_ticks) > 0:
        tick_values = list(x_ticks)
    elif len(all_x) <= 12:
        tick_values = sorted(set(all_x))
    else:
        tick_values = nice_ticks(x_max)

    def x_position(value: float) -> float:
        return box.left + (value - x_min) / (x_max - x_min) * box.width

    for tick in tick_values:
        if tick < x_min - 1e-12 or tick > x_max + 1e-12:
            continue
        x = x_position(tick)
        draw.line(
            [(x * SCALE, box.bottom * SCALE), (x * SCALE, (box.bottom + 4) * SCALE)],
            fill=COLORS["axis"],
            width=1 * SCALE,
        )
        draw_text(
            draw,
            (x * SCALE, (box.bottom + 8) * SCALE),
            format_number(tick),
            font(9),
            COLORS["muted"],
            anchor="mt",
        )

    if reference is not None and reference.value <= top_value:
        y = box.bottom - (reference.value / top_value) * box.height
        dashed_line(
            draw,
            (box.left * SCALE, y * SCALE),
            (box.right * SCALE, y * SCALE),
            fill=_mix(reference.color, "#FFFFFF", 0.8),
            dash=7 * SCALE,
            gap=5 * SCALE,
            thickness=2 * SCALE,
        )

    for item in series:
        points = [
            (x_position(x) * SCALE, (box.bottom - (y / top_value) * box.height) * SCALE)
            for x, y in zip(item.x, item.y)
        ]
        if item.low is not None and item.high is not None:
            error_color = _mix(item.color, "#FFFFFF", 0.55)
            cap = 4 * SCALE
            for x, low, high in zip(item.x, item.low, item.high):
                x_pixel = x_position(x) * SCALE
                low_pixel = (box.bottom - (low / top_value) * box.height) * SCALE
                high_pixel = (box.bottom - (high / top_value) * box.height) * SCALE
                draw.line(
                    [(x_pixel, low_pixel), (x_pixel, high_pixel)],
                    fill=error_color,
                    width=2 * SCALE,
                )
                draw.line(
                    [(x_pixel - cap, low_pixel), (x_pixel + cap, low_pixel)],
                    fill=error_color,
                    width=2 * SCALE,
                )
                draw.line(
                    [(x_pixel - cap, high_pixel), (x_pixel + cap, high_pixel)],
                    fill=error_color,
                    width=2 * SCALE,
                )
        if len(points) > 1:
            draw.line(points, fill=item.color, width=2 * SCALE, joint="curve")
        if item.markers:
            radius = 3.2 * SCALE
            for x_pixel, y_pixel in points:
                draw.ellipse(
                    [
                        (x_pixel - radius, y_pixel - radius),
                        (x_pixel + radius, y_pixel + radius),
                    ],
                    fill=item.color,
                    outline=COLORS["background"],
                    width=1 * SCALE,
                )

    draw.line(
        [(box.left * SCALE, box.bottom * SCALE), (box.right * SCALE, box.bottom * SCALE)],
        fill=COLORS["axis"],
        width=1 * SCALE,
    )

    if x_label:
        draw_text(
            draw,
            (box.left * SCALE + box.width * SCALE / 2, (height - 26) * SCALE),
            x_label,
            font(11),
            COLORS["muted"],
            anchor="mm",
        )
    if y_label:
        _draw_vertical_text(
            image,
            y_label,
            (20, (box.top + box.bottom) / 2),
            11,
            COLORS["muted"],
        )
    return finish_canvas(image, width, height)


__all__ = [
    "BarSeries",
    "LineSeries",
    "ReferenceLine",
    "bar_chart",
    "line_chart",
]
