"""Приёмочная проверка проекта без запуска интерфейса.

Скрипт проходит по критериям приёмки технического задания и проверяет,
что основные функции реально работают: схемы, вентили, измерение, три
модели ошибок, сравнение режимов, серии экспериментов, экспорт CSV/PNG и
наличие документации.

Запуск (из каталога проекта):

.. code-block:: bash

    python scripts/smoke_test.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.demo import demo_by_key, load_demo_circuits  # noqa: E402
from src.experiments.export import (  # noqa: E402
    experiment_csv_bytes,
    run_csv_bytes,
)
from src.experiments.metrics import metrics_for_result  # noqa: E402
from src.experiments.runner import (  # noqa: E402
    ExperimentSpec,
    run_experiment,
)
from src.quantum.circuit import circuit_from_operations  # noqa: E402
from src.quantum.noise import NoiseConfig  # noqa: E402
from src.quantum.simulator import run_circuit  # noqa: E402
from src.render import (  # noqa: E402
    BarSeries,
    bar_chart,
    circuit_diagram,
)

RESULTS = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))
    mark = "OK  " if condition else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{mark}] {name}{suffix}")


def main() -> int:
    print("Проверка критериев приёмки технического задания\n")

    # 1. Демонстрационные схемы.
    demos = load_demo_circuits()
    check("Не менее трёх демонстрационных схем", len(demos) >= 3, f"{len(demos)} схем")
    check(
        "Есть схема Белла",
        any(demo.key == "bell" for demo in demos),
    )
    check(
        "Все схемы корректны",
        all(demo.circuit.is_valid() for demo in demos),
    )

    # 2. Вентили X, H, Z, CNOT на 1–5 кубитах.
    runs_ok = True
    for n_qubits in range(1, 6):
        operations = [("x", n_qubits - 1), ("h", 0), ("z", 0)]
        if n_qubits >= 2:
            operations.append(("cnot", 0, 1))
        circuit = circuit_from_operations(n_qubits, operations)
        result = run_circuit(circuit, shots=200, seed=1)
        runs_ok = runs_ok and sum(result.counts.values()) == 200
    check("Схемы на 1–5 кубитах выполняются", runs_ok)

    # 3. Идеальное распределение и измерение.
    bell = demo_by_key("bell").circuit
    ideal = run_circuit(bell, shots=4000, seed=2024)
    probabilities = ideal.ideal_probabilities
    check(
        "Белл: только 00 и 11",
        ideal.counts["01"] == 0 and ideal.counts["10"] == 0,
        f"{ideal.counts}",
    )
    check(
        "Белл: вероятности 0,5/0,5",
        np.allclose(probabilities, [0.5, 0.0, 0.0, 0.5], atol=1e-12),
    )
    check(
        "Сумма вероятностей равна 1",
        abs(float(np.sum(probabilities)) - 1.0) < 1e-12,
    )
    check(
        "shot-выборка воспроизводима",
        run_circuit(bell, shots=500, seed=7).counts
        == run_circuit(bell, shots=500, seed=7).counts,
    )

    # 4. Три модели ошибок.
    bit_flip = run_circuit(
        bell,
        shots=3000,
        seed=5,
        noise=NoiseConfig(
            enabled=True,
            bit_flip_enabled=True,
            phase_flip_enabled=False,
            readout_enabled=False,
            p_bit_flip=0.1,
        ),
    )
    check(
        "Bit-flip создаёт запрещённые комбинации",
        bit_flip.counts["01"] + bit_flip.counts["10"] > 0,
    )

    phase_circuit = demo_by_key("phase_demo").circuit
    phase = run_circuit(
        phase_circuit,
        shots=3000,
        seed=5,
        noise=NoiseConfig(
            enabled=True,
            bit_flip_enabled=False,
            phase_flip_enabled=True,
            readout_enabled=False,
            p_phase_flip=0.1,
        ),
    )
    check(
        "Phase-flip виден в схеме H–Z–H",
        phase.counts["0"] > 0,
    )

    readout_circuit = circuit_from_operations(1, [])
    readout = run_circuit(
        readout_circuit,
        shots=20000,
        seed=17,
        noise=NoiseConfig(
            enabled=True,
            bit_flip_enabled=False,
            phase_flip_enabled=False,
            readout_enabled=True,
            p_readout=0.5,
        ),
    )
    share = readout.counts["0"] / 20000
    check("Readout p = 0,5 даёт около 50 % нулей", abs(share - 0.5) < 0.02, f"{share:.3f}")

    zero_noise = run_circuit(
        bell,
        shots=500,
        seed=11,
        noise=NoiseConfig(enabled=True, p_bit_flip=0.0, p_phase_flip=0.0, p_readout=0.0),
    )
    check(
        "При p = 0 результат совпадает с идеальным",
        zero_noise.counts == run_circuit(bell, shots=500, seed=11).counts,
    )

    # 5. Сравнение идеального и шумового режимов.
    noisy = run_circuit(
        bell,
        shots=4000,
        seed=2024,
        noise=NoiseConfig(enabled=True, p_bit_flip=0.05, p_readout=0.04),
    )
    metrics = metrics_for_result(noisy, "11")
    check("TVD между идеалом и шумом вычисляется", metrics.tvd_ideal_vs_observed > 0)
    check(
        "Шумовой уровень меньше TVD с ошибками",
        metrics.tvd_noise_floor < metrics.tvd_ideal_vs_observed,
        f"{metrics.tvd_noise_floor:.4f} < {metrics.tvd_ideal_vs_observed:.4f}",
    )

    # 6. Серии экспериментов.
    spec = ExperimentSpec(
        kind="bitflip",
        circuit=bell,
        shots=300,
        repeats=3,
        seed=2024,
        target="11",
        values=(0.0, 0.05, 0.1, 0.2),
    )
    experiment = run_experiment(spec)
    points = experiment.series[0].points
    check("Серия экспериментов выполняется", len(points) == 4)
    check(
        "TVD растёт с вероятностью ошибки",
        points[-1].mean > points[0].mean,
        f"{points[0].mean:.3f} → {points[-1].mean:.3f}",
    )
    check(
        "Эксперимент воспроизводим по seed",
        run_experiment(spec).series[0].points[0].mean
        == experiment.series[0].points[0].mean,
    )
    compare_spec = ExperimentSpec(
        kind="compare",
        circuit=bell,
        shots=200,
        repeats=2,
        seed=7,
        values=(0.0, 0.1),
    )
    compare = run_experiment(compare_spec)
    check("Сравнение каналов даёт три серии", len(compare.series) == 3)

    # 7. Экспорт CSV и PNG.
    csv_payload = experiment_csv_bytes(experiment)
    check(
        "CSV начинается с параметров и содержит данные",
        csv_payload.startswith(b"\xef\xbb\xbf#") and b"TVD" in csv_payload,
    )
    run_csv = run_csv_bytes(noisy)
    check("CSV одного запуска содержит распределение", b"00" in run_csv)

    # Файлы пишем во временный каталог проекта: это работает и в песочнице,
    # и на машине без прав на системный /tmp.
    directory_path = ROOT / "build" / "smoke"
    shutil.rmtree(directory_path, ignore_errors=True)
    directory_path.mkdir(parents=True, exist_ok=True)
    (directory_path / "experiment.csv").write_bytes(csv_payload)
    png = bar_chart(
        list(noisy.labels),
        [BarSeries("Идеально", noisy.ideal_probabilities, "#94A3B8")],
        "Проверка",
        x_label="Битовая строка",
        y_label="Вероятность",
    )
    (directory_path / "chart.png").write_bytes(png)
    check(
        "PNG создаётся и является корректным файлом",
        png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) > 1000,
    )
    check(
        "Файлы сохраняются на диск",
        (directory_path / "experiment.csv").stat().st_size > 0
        and (directory_path / "chart.png").stat().st_size > 0,
    )
    shutil.rmtree(directory_path, ignore_errors=True)

    # 8. Диаграммы схемы и архитектуры.
    circuit_png = circuit_diagram(bell)
    check("Схема рисуется в PNG", circuit_png.startswith(b"\x89PNG"))
    architecture_image = ROOT / "assets" / "architecture.png"
    check(
        "Схема архитектуры — изображение PNG",
        architecture_image.exists()
        and architecture_image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n",
    )

    # 9. Документация и примеры.
    required_files = [
        "README.md",
        "LICENSE",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "docs/ARCHITECTURE.md",
        "docs/MATH_MODEL.md",
        "docs/EXPERIMENTS.md",
        "docs/DEMO_SCRIPT.md",
        "docs/SOURCES.md",
        "assets/architecture.png",
        "examples/demo_circuits.json",
        "examples/results/experiment_bitflip.csv",
        "examples/results/experiment_compare.png",
    ]
    missing = [name for name in required_files if not (ROOT / name).exists()]
    check("Все обязательные файлы на месте", not missing, ", ".join(missing))

    failed = [name for name, ok, _ in RESULTS if not ok]
    print()
    if failed:
        print(f"Не пройдено проверок: {len(failed)} из {len(RESULTS)}")
        for name in failed:
            print(" -", name)
        return 1
    print(f"Все проверки пройдены ({len(RESULTS)} из {len(RESULTS)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
