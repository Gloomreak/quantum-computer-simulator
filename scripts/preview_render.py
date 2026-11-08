"""Служебный скрипт: отрисовать примеры графиков для визуальной проверки.

Запуск: python scripts/preview_render.py
Результат: PNG-файлы в каталоге build/preview/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.demo import demo_by_key  # noqa: E402
from src.experiments.runner import (  # noqa: E402
    ExperimentSpec,
    run_experiment,
)
from src.quantum.noise import NoiseConfig  # noqa: E402
from src.quantum.simulator import run_circuit  # noqa: E402
from src.render import (  # noqa: E402
    BarSeries,
    LineSeries,
    ReferenceLine,
    bar_chart,
    circuit_diagram,
    line_chart,
)

OUT = ROOT / "build" / "preview"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bell = demo_by_key("bell").circuit
    (OUT / "circuit_bell.png").write_bytes(circuit_diagram(bell))
    (OUT / "circuit_ghz.png").write_bytes(
        circuit_diagram(demo_by_key("ghz3").circuit)
    )
    (OUT / "circuit_empty.png").write_bytes(
        circuit_diagram(demo_by_key("readout_only").circuit)
    )

    ideal = run_circuit(bell, shots=1000, seed=11)
    noisy = run_circuit(
        bell,
        shots=1000,
        seed=11,
        noise=NoiseConfig(enabled=True, p_bit_flip=0.05, p_readout=0.03),
    )
    (OUT / "bars_ideal.png").write_bytes(
        bar_chart(
            ideal.labels,
            [BarSeries("Идеально (теория)", ideal.ideal_probabilities, "#94A3B8")],
            "Теоретические вероятности идеального исполнения",
            subtitle="Схема: состояние Белла · 2 кубита · 1000 измерений",
            x_label="Битовая строка (q0 q1)",
            y_label="Вероятность",
            show_value_labels=True,
        )
    )
    (OUT / "bars_compare.png").write_bytes(
        bar_chart(
            ideal.labels,
            [
                BarSeries("Идеально (теория)", ideal.ideal_probabilities, "#94A3B8"),
                BarSeries("С ошибками", noisy.probabilities_for("noisy"), "#2563EB"),
            ],
            "Сравнение идеального и шумового распределений",
            subtitle="bit-flip p = 0,05 · ошибка считывания p = 0,03",
            x_label="Битовая строка (q0 q1)",
            y_label="Вероятность",
        )
    )
    (OUT / "bars_counts.png").write_bytes(
        bar_chart(
            ideal.labels,
            [
                BarSeries(
                    "Число измерений",
                    [ideal.counts[label] for label in ideal.labels],
                    "#2563EB",
                    value_format="count",
                )
            ],
            "Гистограмма результатов измерения",
            subtitle="shots = 1000, seed = 11",
            x_label="Битовая строка",
            y_label="Число измерений",
            show_value_labels=True,
        )
    )

    spec = ExperimentSpec(
        kind="compare",
        circuit=bell,
        shots=600,
        repeats=10,
        seed=2024,
        target="11",
        values=tuple(round(index * 0.01, 2) for index in range(21)),
    )
    comparison = run_experiment(spec)
    colors = {"bit_flip": "#2563EB", "phase_flip": "#DC2626", "readout": "#059669"}
    (OUT / "lines_compare.png").write_bytes(
        line_chart(
            [
                LineSeries(
                    series.label,
                    [point.value for point in series.points],
                    [point.mean for point in series.points],
                    colors.get(series.key, "#2563EB"),
                    [point.ci_low for point in series.points],
                    [point.ci_high for point in series.points],
                )
                for series in comparison.series
            ],
            "Сравнение влияния каналов ошибок",
            subtitle="Состояние Белла · 600 shots · 10 повторов · 95% ДИ",
            x_label="Вероятность ошибки p",
            y_label="TVD",
            reference=ReferenceLine(
                comparison.series[0].points[0].floor_mean,
                "шумовой уровень",
            ),
        )
    )
    (OUT / "lines_bitflip.png").write_bytes(
        line_chart(
            [
                LineSeries(
                    "Bit-flip (X)",
                    [point.value for point in comparison.series[0].points],
                    [point.mean for point in comparison.series[0].points],
                    "#2563EB",
                    [point.ci_low for point in comparison.series[0].points],
                    [point.ci_high for point in comparison.series[0].points],
                )
            ],
            "TVD от вероятности bit-flip",
            subtitle="Состояние Белла · 600 shots · 10 повторов",
            x_label="Вероятность bit-flip p",
            y_label="TVD (идеальное ↔ измеренное)",
        )
    )
    print("Готово:", OUT)


if __name__ == "__main__":
    main()
