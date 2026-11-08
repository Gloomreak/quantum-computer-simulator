"""Схема квантовой схемы в PNG.

Кубит 0 — верхняя линия. Вентили размещаются по слоям, поэтому операции,
которые могут выполняться одновременно, попадают в один столбец.
Последний столбец — измерение.
"""

from __future__ import annotations

from typing import Dict, List

from PIL import Image, ImageDraw

from ..quantum.circuit import Circuit
from ..quantum.gates import get_gate
from .theme import (
    COLORS,
    SCALE,
    draw_text,
    finish_canvas,
    font,
    text_size,
)

GATE_COLORS: Dict[str, str] = {
    "x": COLORS["gate_x"],
    "h": COLORS["gate_h"],
    "z": COLORS["gate_z"],
    "cnot": COLORS["gate_cnot"],
}


def circuit_diagram(circuit: Circuit, width: int = 900) -> bytes:
    """Нарисовать квантовую схему.

    Кубит 0 — верхняя линия. Вентили размещаются по слоям: операции на
    разных кубитах, которые могут выполняться одновременно, попадают в
    один столбец. Последний столбец — измерение.
    """

    n_qubits = circuit.n_qubits
    layers = circuit.layers()
    layer_count = max(layers) if layers else 0
    columns = layer_count + (1 if circuit.measured_count else 0)
    row_height = 58
    top_margin = 86
    bottom_margin = 54
    height = top_margin + row_height * n_qubits + bottom_margin

    image = Image.new("RGB", (width * SCALE, height * SCALE), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        [0, 0, width * SCALE - 1, height * SCALE - 1],
        outline=COLORS["border"],
        width=1 * SCALE,
    )

    title = f"Схема: {circuit.name}"
    draw_text(draw, (24 * SCALE, 16 * SCALE), title, font(15, True), COLORS["ink"], bold=True)

    measured_text = (
        "все кубиты"
        if circuit.measured_count == n_qubits
        else ", ".join(f"q{q}" for q in circuit.measured)
    )
    subtitle = (
        f"Кубитов: {n_qubits} · Операций: {circuit.gate_count} · "
        f"Глубина: {circuit.depth()} · Измеряются: {measured_text}"
    )
    draw_text(draw, (24 * SCALE, 42 * SCALE), subtitle, font(10), COLORS["muted"])

    left_label_width = 86
    line_start = left_label_width + 16
    line_end = width - 28
    available = line_end - line_start - 22
    column_width = available / max(1, columns) if columns else 0.0
    column_width = min(column_width, 78.0)
    start_x = line_start + 10

    row_centers: List[float] = []
    for qubit in range(n_qubits):
        y = top_margin + row_height * qubit + row_height / 2
        row_centers.append(y)
        draw.line(
            [(line_start * SCALE, y * SCALE), (line_end * SCALE, y * SCALE)],
            fill=COLORS["wire"],
            width=2 * SCALE,
        )
        draw_text(
            draw,
            (16 * SCALE, (y - 6) * SCALE),
            f"q{qubit}",
            font(11, True),
            COLORS["ink"],
            bold=True,
        )
        draw_text(
            draw,
            ((left_label_width - 12) * SCALE, (y - 5) * SCALE),
            "|0>",
            font(9),
            COLORS["muted"],
            anchor="rt",
        )

    if not circuit.operations:
        message = "Схема не содержит вентилей: измеряется начальное состояние |00…0⟩"
        draw_text(
            draw,
            (
                ((line_start + line_end) / 2) * SCALE,
                (top_margin + row_height * n_qubits + 16) * SCALE,
            ),
            message,
            font(9),
            COLORS["muted"],
            anchor="mt",
        )

    box_width = min(46.0, column_width * 0.66)
    box_height = 34.0

    for operation, layer in zip(circuit.operations, layers):
        center_x = start_x + (layer - 0.5) * column_width
        if operation.gate == "cnot":
            control_y = row_centers[operation.control]
            target_y = row_centers[operation.target]
            color = GATE_COLORS["cnot"]
            draw.line(
                [(center_x * SCALE, control_y * SCALE), (center_x * SCALE, target_y * SCALE)],
                fill=color,
                width=3 * SCALE,
            )
            radius = 6 * SCALE
            draw.ellipse(
                [
                    (center_x * SCALE - radius, control_y * SCALE - radius),
                    (center_x * SCALE + radius, control_y * SCALE + radius),
                ],
                fill=color,
            )
            ring = 12 * SCALE
            draw.ellipse(
                [
                    (center_x * SCALE - ring, target_y * SCALE - ring),
                    (center_x * SCALE + ring, target_y * SCALE + ring),
                ],
                fill=COLORS["background"],
                outline=color,
                width=3 * SCALE,
            )
            draw.line(
                [(center_x * SCALE - ring, target_y * SCALE), (center_x * SCALE + ring, target_y * SCALE)],
                fill=color,
                width=3 * SCALE,
            )
            draw.line(
                [(center_x * SCALE, target_y * SCALE - ring), (center_x * SCALE, target_y * SCALE + ring)],
                fill=color,
                width=3 * SCALE,
            )
            continue

        y = row_centers[operation.target]
        color = GATE_COLORS.get(operation.gate, COLORS["ink"])
        draw.rounded_rectangle(
            [
                ((center_x - box_width / 2) * SCALE, (y - box_height / 2) * SCALE),
                ((center_x + box_width / 2) * SCALE, (y + box_height / 2) * SCALE),
            ],
            radius=7 * SCALE,
            fill=color,
            outline=color,
            width=2 * SCALE,
        )
        draw_text(
            draw,
            (center_x * SCALE, (y - 1) * SCALE),
            get_gate(operation.gate).symbol,
            font(12, True),
            "#FFFFFF",
            bold=True,
            anchor="mm",
        )

    if circuit.measured_count:
        measurement_x = start_x + (layer_count + 0.5) * column_width
        for qubit in circuit.measured:
            y = row_centers[qubit]
            draw.rounded_rectangle(
                [
                    ((measurement_x - 19) * SCALE, (y - 19) * SCALE),
                    ((measurement_x + 19) * SCALE, (y + 19) * SCALE),
                ],
                radius=7 * SCALE,
                fill=COLORS["background"],
                outline=COLORS["measurement"],
                width=2 * SCALE,
            )
            draw_text(
                draw,
                (measurement_x * SCALE, (y - 1) * SCALE),
                "M",
                font(12, True),
                COLORS["measurement"],
                bold=True,
                anchor="mm",
            )

    legend_y = height - 30
    legend_x = 24.0
    items = [
        ("X", GATE_COLORS["x"]),
        ("H", GATE_COLORS["h"]),
        ("Z", GATE_COLORS["z"]),
        ("CNOT", GATE_COLORS["cnot"]),
        ("измерение", COLORS["measurement"]),
    ]
    for label, color in items:
        if label == "измерение":
            draw.rounded_rectangle(
                [
                    (legend_x * SCALE, (legend_y - 8) * SCALE),
                    ((legend_x + 14) * SCALE, (legend_y + 6) * SCALE),
                ],
                radius=2 * SCALE,
                outline=color,
                width=1 * SCALE,
            )
            draw_text(
                draw,
                ((legend_x + 7) * SCALE, (legend_y - 1) * SCALE),
                "M",
                font(7, True),
                color,
                bold=True,
                anchor="mm",
            )
            draw_text(
                draw,
                ((legend_x + 20) * SCALE, legend_y * SCALE),
                label,
                font(9),
                COLORS["muted"],
                anchor="lm",
            )
            width_label = text_size(draw, label, font(9))[0] / SCALE + 20
        else:
            draw.rectangle(
                [
                    (legend_x * SCALE, (legend_y - 5) * SCALE),
                    ((legend_x + 10) * SCALE, (legend_y + 5) * SCALE),
                ],
                fill=color,
            )
            draw_text(
                draw,
                ((legend_x + 15) * SCALE, legend_y * SCALE),
                label,
                font(9),
                COLORS["muted"],
                anchor="lm",
            )
            width_label = text_size(draw, label, font(9))[0] / SCALE + 15
        legend_x += width_label + 22

    return finish_canvas(image, width, height)


__all__ = ["GATE_COLORS", "circuit_diagram"]
