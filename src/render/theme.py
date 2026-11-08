"""Оформление графиков: палитра, шрифты и вспомогательные функции.

Графики рисуются собственным модулем на Pillow. Это осознанный выбор:

* нет тяжёлых зависимостей (Plotly/Matplotlib) — образ Docker меньше,
  запуск на слабом ноутбуке быстрее;
* PNG-файл, который видит пользователь, — это ровно те байты, которые
  сохраняются кнопкой «Скачать PNG» (без отличий в рендеринге);
* шрифт DejaVu Sans поставляется вместе с проектом, поэтому подписи на
  русском выглядят одинаково в Windows, Linux, macOS и в контейнере.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Tuple

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
REGULAR_FONT = FONT_DIR / "DejaVuSans.ttf"
BOLD_FONT = FONT_DIR / "DejaVuSans-Bold.ttf"

# Системные шрифты — резервный вариант, если каталог assets не скопирован.
FALLBACK_FONTS: Tuple[Path, ...] = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    Path("C:/Windows/Fonts/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
)
FALLBACK_BOLD_FONTS: Tuple[Path, ...] = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
)

# Единая палитра: сдержанные цвета с достаточным контрастом.
COLORS = {
    "background": "#FFFFFF",
    "surface": "#F8FAFC",
    "border": "#E2E8F0",
    "ink": "#0F172A",
    "muted": "#000000",
    "grid": "#E2E8F0",
    "axis": "#94A3B8",
    "ideal": "#94A3B8",
    "observed": "#2563EB",
    "accent": "#EA580C",
    "danger": "#DC2626",
    "success": "#059669",
    "series": (
        "#2563EB",  # синий
        "#DC2626",  # красный
        "#059669",  # зелёный
        "#7C3AED",  # фиолетовый
        "#D97706",  # оранжевый
        "#0891B2",  # бирюзовый
    ),
    "gate_x": "#1D4ED8",
    "gate_h": "#047857",
    "gate_z": "#7C3AED",
    "gate_cnot": "#B45309",
    "measurement": "#334155",
    "highlight": "#F59E0B",
    "wire": "#94A3B8",
}

SCALE = 2  # суперсэмплинг для сглаживания линий и текста


@dataclass(frozen=True)
class FontFamily:
    """Пара шрифтов (обычный и полужирный) для одного размера."""

    regular: ImageFont.FreeTypeFont | ImageFont.ImageFont
    bold: ImageFont.FreeTypeFont | ImageFont.ImageFont


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


@lru_cache(maxsize=1)
def font_paths() -> Tuple[str | None, str | None]:
    """Найти пути к обычному и полужирному шрифту."""

    regular = _first_existing((REGULAR_FONT,) + FALLBACK_FONTS)
    bold = _first_existing((BOLD_FONT,) + FALLBACK_BOLD_FONTS)
    if regular is None:
        return None, None
    return str(regular), str(bold or regular)


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False) -> FontFamily:
    """Шрифт заданного размера (в пикселях итогового изображения)."""

    regular_path, bold_path = font_paths()
    target = size * SCALE
    if regular_path is None:
        default = ImageFont.load_default(size=target)
        return FontFamily(default, default)
    regular = ImageFont.truetype(regular_path, target)
    bold_font = ImageFont.truetype(bold_path, target) if bold_path else regular
    return FontFamily(regular, bold_font)


def has_cyrillic() -> bool:
    """Содержит ли найденный шрифт кириллические глифы."""

    regular_path, _ = font_paths()
    if regular_path is None:
        return False
    try:
        reference = ImageFont.truetype(regular_path, 24)
        mask = reference.getmask("Я")
        return mask.getbbox() is not None
    except (OSError, ValueError):
        return False


_TRANSLITERATION = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def safe_text(text: str) -> str:
    """Заменить кириллицу латиницей, если шрифт её не поддерживает."""

    if has_cyrillic():
        return text
    result: List[str] = []
    for char in text:
        lower = char.lower()
        if lower in _TRANSLITERATION:
            replacement = _TRANSLITERATION[lower]
            result.append(replacement.upper() if char.isupper() and replacement else replacement)
        else:
            result.append(char)
    return "".join(result)


def text_size(
    draw: ImageDraw.ImageDraw, text: str, font_family: FontFamily, bold: bool = False
) -> Tuple[int, int]:
    """Размер текста в пикселях."""

    chosen = font_family.bold if bold else font_family.regular
    box = draw.textbbox((0, 0), text, font=chosen)
    return box[2] - box[0], box[3] - box[1]


def draw_text(
    draw: ImageDraw.ImageDraw,
    position: Tuple[float, float],
    text: str,
    font_family: FontFamily,
    fill: str = COLORS["ink"],
    bold: bool = False,
    anchor: str = "lt",
) -> Tuple[int, int]:
    """Нарисовать текст и вернуть его размер."""

    chosen = font_family.bold if bold else font_family.regular
    draw.text(position, safe_text(text), font=chosen, fill=fill, anchor=anchor)
    return text_size(draw, safe_text(text), font_family, bold)


def new_canvas(width: int, height: int) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    """Создать изображение с суперсэмплингом."""

    image = Image.new("RGB", (width * SCALE, height * SCALE), COLORS["background"])
    return image, ImageDraw.Draw(image)


def finish_canvas(image: Image.Image, width: int, height: int) -> bytes:
    """Уменьшить изображение и вернуть PNG-байты."""

    resized = image.resize((width, height), Image.LANCZOS)
    return to_png_bytes(resized)


def to_png_bytes(image: Image.Image) -> bytes:
    """Сериализовать изображение в PNG."""

    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def dashed_line(
    draw: ImageDraw.ImageDraw,
    start: Tuple[float, float],
    end: Tuple[float, float],
    fill: str,
    dash: int = 6,
    gap: int = 5,
    thickness: int = 1,
) -> None:
    """Нарисовать пунктирную линию."""

    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return
    step = dash + gap
    position = 0.0
    while position < length:
        end_position = min(position + dash, length)
        start_point = (x1 + dx * position / length, y1 + dy * position / length)
        end_point = (x1 + dx * end_position / length, y1 + dy * end_position / length)
        draw.line([start_point, end_point], fill=fill, width=thickness)
        position += step


def nice_ticks(maximum: float, count: int = 5) -> List[float]:
    """Подобрать «круглые» отметки от 0 до ближайшего значения выше максимума."""

    if maximum <= 0:
        return [0.0, 1.0]
    raw_step = maximum / max(1, count)
    magnitude = 10 ** int(_floor_log10(raw_step))
    normalized = raw_step / magnitude
    for candidate in (1, 2, 2.5, 5, 10):
        if normalized <= candidate:
            step = candidate * magnitude
            break
    else:  # pragma: no cover - защита от нечисловых значений
        step = magnitude * 10
    ticks = [0.0]
    value = step
    while value < maximum + step * 0.999:
        ticks.append(round(value, 10))
        value += step
    return ticks


def _floor_log10(value: float) -> float:
    import math

    return math.floor(math.log10(value)) if value > 0 else 0


def format_number(value: float) -> str:
    """Компактный формат чисел для подписей осей."""

    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 1:
        return f"{value:g}"
    if value == 0:
        return "0"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def format_percent(value: float) -> str:
    """Вероятность в процентах с разумной точностью."""

    percent = value * 100
    if percent >= 10:
        return f"{percent:.0f}%"
    if percent >= 1:
        return f"{percent:.1f}%"
    return f"{percent:.2f}%"


__all__ = [
    "COLORS",
    "FONT_DIR",
    "FontFamily",
    "SCALE",
    "dashed_line",
    "draw_text",
    "finish_canvas",
    "font",
    "format_number",
    "format_percent",
    "has_cyrillic",
    "new_canvas",
    "nice_ticks",
    "safe_text",
    "text_size",
    "to_png_bytes",
]
