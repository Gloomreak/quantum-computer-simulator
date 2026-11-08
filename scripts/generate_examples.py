"""Сформировать демонстрационные данные: схемы, CSV и PNG.

Запуск (из каталога проекта):

.. code-block:: bash

    python scripts/generate_examples.py

Скрипт выполняет **реальные** расчёты симулятором и сохраняет результаты
в ``examples/results/``. Параметры (shots, seed, сетка вероятностей)
фиксированы, поэтому файлы воспроизводимы: повторный запуск даёт те же
числа.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.demo import demo_by_key  # noqa: E402
from src.experiments.export import (  # noqa: E402
    experiment_csv_bytes,
    run_csv_bytes,
    save_bytes,
)
from src.experiments.metrics import metrics_for_result  # noqa: E402
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

OUT = ROOT / "examples" / "results"
SHOTS = 1000
SEED = 2024
REPEATS = 10
COLORS = ("#2563EB", "#DC2626", "#059669", "#7C3AED", "#D97706")


def _experiment_png(result) -> bytes:
    series = []
    for index, item in enumerate(result.series):
        series.append(
            LineSeries(
                name=item.label,
                x=[point.value for point in item.points],
                y=[point.mean for point in item.points],
                color=COLORS[index % len(COLORS)],
                low=[point.ci_low for point in item.points],
                high=[point.ci_high for point in item.points],
            )
        )
    floor = sum(point.floor_mean for point in result.series[0].points) / len(
        result.series[0].points
    )
    reference = ReferenceLine(floor, "шумовой уровень выборки")
    if result.kind == "shots" and result.series:
        first = result.series[0]
        series.append(
            LineSeries(
                name="Шумовой уровень (p = 0)",
                x=[point.value for point in first.points],
                y=[point.floor_mean for point in first.points],
                color="#D97706",
                markers=True,
            )
        )
        reference = None
    return line_chart(
        series,
        result.title,
        subtitle=f"{result.circuit_name} · {result.params_note}",
        x_label=result.x_label,
        y_label=result.y_label,
        reference=reference,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bell = demo_by_key("bell").circuit
    ghz = demo_by_key("ghz3").circuit

    # Схемы в PNG.
    save_bytes(circuit_diagram(bell), OUT / "circuit_bell.png")
    save_bytes(circuit_diagram(ghz), OUT / "circuit_ghz.png")

    # Идеальное исполнение состояния Белла.
    ideal = run_circuit(bell, shots=SHOTS, seed=SEED)
    save_bytes(run_csv_bytes(ideal), OUT / "run_bell_ideal.csv")
    save_bytes(
        bar_chart(
            ideal.labels,
            [BarSeries("Идеально (теория)", ideal.ideal_probabilities, "#94A3B8")],
            "Теоретические вероятности идеального исполнения",
            subtitle=f"Состояние Белла · shots = {SHOTS} · seed = {SEED}",
            x_label="Битовая строка (q0 q1)",
            y_label="Вероятность",
            show_value_labels=True,
        ),
        OUT / "distribution_bell_ideal.png",
    )

    # Зашумлённое исполнение и сравнение.
    noise = NoiseConfig(
        enabled=True,
        bit_flip_enabled=True,
        phase_flip_enabled=True,
        readout_enabled=True,
        p_bit_flip=0.05,
        p_phase_flip=0.03,
        p_readout=0.04,
    )
    noisy = run_circuit(bell, shots=SHOTS, seed=SEED, noise=noise)
    save_bytes(run_csv_bytes(noisy), OUT / "run_bell_noisy.csv")
    save_bytes(
        bar_chart(
            ideal.labels,
            [
                BarSeries("Идеально (теория)", ideal.ideal_probabilities, "#94A3B8"),
                BarSeries("С ошибками (измерено)", noisy.probabilities_for("noisy"), "#2563EB"),
            ],
            "Идеальное и зашумлённое распределения",
            subtitle=(
                f"Состояние Белла · bit-flip 0,05 · phase-flip 0,03 · "
                f"readout 0,04 · shots = {SHOTS}"
            ),
            x_label="Битовая строка (q0 q1)",
            y_label="Вероятность",
        ),
        OUT / "comparison_bell_noise.png",
    )
    metrics = metrics_for_result(noisy, "11")
    print(
        f"Белл с ошибками: TVD = {metrics.tvd_ideal_vs_observed:.4f}, "
        f"шумовой уровень = {metrics.tvd_noise_floor:.4f}"
    )

    # Эксперименты.
    experiments = {
        "bitflip": ExperimentSpec(
            kind="bitflip",
            circuit=bell,
            shots=SHOTS,
            repeats=REPEATS,
            seed=SEED,
            target="11",
            values=tuple(round(index * 0.01, 2) for index in range(21)),
        ),
        "readout": ExperimentSpec(
            kind="readout",
            circuit=bell,
            shots=SHOTS,
            repeats=REPEATS,
            seed=SEED,
            target="11",
            values=tuple(round(index * 0.01, 2) for index in range(21)),
        ),
        "depth": ExperimentSpec(
            kind="depth",
            circuit=bell,
            shots=SHOTS,
            repeats=REPEATS,
            seed=SEED,
            target="11",
            p_fixed=0.02,
            max_operations=20,
        ),
        "compare": ExperimentSpec(
            kind="compare",
            circuit=bell,
            shots=SHOTS,
            repeats=REPEATS,
            seed=SEED,
            target="11",
            values=tuple(round(index * 0.01, 2) for index in range(21)),
        ),
        "shots": ExperimentSpec(
            kind="shots",
            circuit=bell,
            repeats=REPEATS,
            seed=SEED,
            target="11",
            p_fixed=0.05,
            shots_grid=(100, 250, 500, 1000, 2000, 5000, 10000),
        ),
    }

    for key, spec in experiments.items():
        result = run_experiment(spec)
        save_bytes(experiment_csv_bytes(result), OUT / f"experiment_{key}.csv")
        save_bytes(
            experiment_csv_bytes(result, aggregated=True),
            OUT / f"experiment_{key}_mean.csv",
        )
        save_bytes(_experiment_png(result), OUT / f"experiment_{key}.png")
        first = result.series[0].points[0]
        last = result.series[0].points[-1]
        print(
            f"{key}: {result.total_runs} запусков, "
            f"TVD от {first.mean:.3f} до {last.mean:.3f} за {result.duration_s:.2f} с"
        )

    manifest = [
        "# Примеры результатов, полученных симулятором",
        "",
        f"Параметры: shots = {SHOTS}, seed = {SEED}, повторов = {REPEATS}.",
        "Схемы: состояние Белла (2 кубита) и GHZ-3 (3 кубита).",
        "",
        "Файлы:",
        "- circuit_bell.png, circuit_ghz.png — изображения схем;",
        "- run_bell_ideal.csv, run_bell_noisy.csv — распределения одного запуска;",
        "- distribution_bell_ideal.png — теоретические вероятности;",
        "- comparison_bell_noise.png — сравнение идеального и шумового режимов;",
        "- experiment_*.csv — сырые данные серий (по строкам на каждый запуск);",
        "- experiment_*_mean.csv — средние значения по точкам;",
        "- experiment_*.png — графики серий.",
        "",
        "Все файлы получены запуском scripts/generate_examples.py; "
        "повторный запуск с теми же параметрами воспроизводит числа.",
    ]
    (OUT / "README.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"Готово: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
