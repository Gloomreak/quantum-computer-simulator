"""Серии экспериментов: запуск схем при разных параметрах и сбор метрик.

Каждая точка эксперимента — несколько независимых запусков (``repeats``)
с разными, но воспроизводимыми seed. Для точки сохраняются среднее TVD,
стандартное отклонение и 95 % доверительный интервал.

Seed для повтора вычисляется детерминированно:

.. code-block:: text

    seed_повтора = (базовый_seed + номер_повтора * 7919) mod 2**32

Поэтому повторный запуск эксперимента с теми же параметрами даёт те же
числа.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np

from ..quantum.circuit import Circuit, Operation
from ..quantum.measurement import validate_seed, validate_shots
from ..quantum.noise import NoiseConfig
from ..quantum.simulator import run_circuit
from .metrics import confidence_interval_95, mean_std, metrics_for_result

MAX_REPEATS: int = 50
MAX_POINTS: int = 101
MAX_TOTAL_RUNS: int = 20_000

#: Сетка числа измерений для эксперимента «TVD от shots».
DEFAULT_SHOTS_GRID: Tuple[int, ...] = (100, 250, 500, 1000, 2000, 5000, 10000)

CHANNEL_BIT_FLIP: str = "bit_flip"
CHANNEL_PHASE_FLIP: str = "phase_flip"
CHANNEL_READOUT: str = "readout"

CHANNEL_LABELS: Dict[str, str] = {
    CHANNEL_BIT_FLIP: "Bit-flip (X)",
    CHANNEL_PHASE_FLIP: "Phase-flip (Z)",
    CHANNEL_READOUT: "Ошибка считывания",
}


def probability_grid(
    minimum: float = 0.0, maximum: float = 0.2, step: float = 0.01
) -> Tuple[float, ...]:
    """Равномерная сетка вероятностей, включая правую границу."""

    if step <= 0:
        raise ValueError("Шаг сетки вероятностей должен быть положительным.")
    if minimum < 0 or maximum > 1 or minimum > maximum:
        raise ValueError("Некорректный диапазон вероятностей.")
    count = int(round((maximum - minimum) / step)) + 1
    if count > MAX_POINTS:
        raise ValueError(
            f"Слишком много точек: {count}. Увеличьте шаг или уменьшите диапазон."
        )
    values = tuple(round(minimum + index * step, 10) for index in range(count))
    return values


@dataclass(frozen=True)
class ExperimentKindInfo:
    """Описание вида эксперимента для интерфейса."""

    key: str
    title: str
    short: str
    description: str
    x_label: str
    y_label: str
    value_kind: str
    default_demo: str
    default_target: str | None
    default_channel: str | None
    notes: str


EXPERIMENT_KINDS: Dict[str, ExperimentKindInfo] = {
    "bitflip": ExperimentKindInfo(
        key="bitflip",
        title="TVD от вероятности bit-flip",
        short="Влияние ошибок переворота бита на распределение.",
        description=(
            "Схема выполняется при разных вероятностях bit-flip ошибки "
            "вентилей. Для каждой точки измеряется TVD между идеальным "
            "распределением и наблюдаемыми частотами."
        ),
        x_label="Вероятность bit-flip p",
        y_label="TVD (идеальное ↔ измеренное)",
        value_kind="probability",
        default_demo="bell",
        default_target="11",
        default_channel=CHANNEL_BIT_FLIP,
        notes=(
            "Ожидаемое поведение: с ростом p распределение уходит от "
            "идеального, TVD растёт. Точка p = 0 показывает шумовой уровень "
            "конечного числа измерений."
        ),
    ),
    "phaseflip": ExperimentKindInfo(
        key="phaseflip",
        title="TVD от вероятности phase-flip",
        short="Влияние фазовых ошибок на распределение.",
        description=(
            "Схема выполняется при разных вероятностях phase-flip ошибки. "
            "Фазовая ошибка не меняет вероятности в вычислительном базисе "
            "напрямую, поэтому её влияние зависит от того, есть ли в схеме "
            "вентили, меняющие базис после места ошибки."
        ),
        x_label="Вероятность phase-flip p",
        y_label="TVD (идеальное ↔ измеренное)",
        value_kind="probability",
        default_demo="phase_demo",
        default_target="1",
        default_channel=CHANNEL_PHASE_FLIP,
        notes=(
            "Для схемы без H после места ошибки TVD может оставаться почти "
            "нулевым: Z-ошибка не видна при измерении в Z-базисе. Это не "
            "ошибка симулятора, а свойство выбранной схемы и базиса "
            "измерения."
        ),
    ),
    "readout": ExperimentKindInfo(
        key="readout",
        title="TVD от вероятности ошибки считывания",
        short="Влияние ошибок измерения на распределение.",
        description=(
            "Вероятность ошибки считывания меняется, схема и ошибки "
            "вентилей остаются нулевыми. Видно, как искажается даже простое "
            "детерминированное распределение."
        ),
        x_label="Вероятность ошибки считывания p",
        y_label="TVD (идеальное ↔ измеренное)",
        value_kind="probability",
        default_demo="bit_flip",
        default_target="1",
        default_channel=CHANNEL_READOUT,
        notes=(
            "Ошибка считывания действует уже после измерения, поэтому она "
            "искажает распределение даже для схемы без вентилей."
        ),
    ),
    "depth": ExperimentKindInfo(
        key="depth",
        title="TVD от числа операций (глубины)",
        short="Накопление ошибок с ростом длины схемы.",
        description=(
            "К базовой схеме добавляются пары CNOT, которые в идеале "
            "взаимно уничтожаются (CNOT·CNOT = I). Идеальное распределение "
            "не меняется, а число операций растёт, поэтому рост TVD "
            "отражает накопление ошибок."
        ),
        x_label="Число операций в схеме",
        y_label="TVD (идеальное ↔ измеренное)",
        value_kind="operations",
        default_demo="bell",
        default_target="11",
        default_channel=CHANNEL_BIT_FLIP,
        notes=(
            "Такой приём (повторение взаимно обратных операций) позволяет "
            "изучать накопление ошибок при неизменном идеальном результате."
        ),
    ),
    "compare": ExperimentKindInfo(
        key="compare",
        title="Сравнение каналов ошибок",
        short="Bit-flip, phase-flip и считывание на одной схеме.",
        description=(
            "Одна и та же схема запускается с тремя разными каналами "
            "ошибок. Сравнение показывает, что характер влияния зависит от "
            "типа ошибки и структуры схемы."
        ),
        x_label="Вероятность ошибки p",
        y_label="TVD (идеальное ↔ измеренное)",
        value_kind="probability",
        default_demo="bell",
        default_target="11",
        default_channel=None,
        notes=(
            "Каналы сравниваются при одинаковых shots, seed и числе "
            "повторов. Разные наклоны кривых — наблюдаемый факт, а не "
            "заранее заданный вывод."
        ),
    ),
    "shots": ExperimentKindInfo(
        key="shots",
        title="TVD от числа измерений (shots)",
        short="Статистическая точность и шумовой уровень выборки.",
        description=(
            "Одна и та же шумовая схема измеряется разным числом shots. "
            "TVD считается относительно теоретического распределения, "
            "поэтому при малом числе измерений в метрику входит вклад "
            "статистического разброса."
        ),
        x_label="Число измерений (shots)",
        y_label="TVD (идеальное ↔ измеренное)",
        value_kind="shots",
        default_demo="bell",
        default_target="11",
        default_channel=CHANNEL_BIT_FLIP,
        notes=(
            "При p = 0 кривая показывает чисто статистическую точность и "
            "убывает примерно как 1/√shots. При p > 0 TVD перестаёт убывать, "
            "когда статистический вклад становится меньше вклада ошибки: "
            "кривая выходит на плато. Поэтому на графике дополнительно "
            "показан шумовой уровень (идеальная выборка при тех же shots)."
        ),
    ),
}


def experiment_kinds() -> List[ExperimentKindInfo]:
    """Список видов экспериментов в порядке отображения."""

    return list(EXPERIMENT_KINDS.values())


def kind_info(key: str) -> ExperimentKindInfo:
    """Описание вида эксперимента."""

    try:
        return EXPERIMENT_KINDS[key]
    except KeyError as exc:
        raise KeyError(f"Неизвестный вид эксперимента: {key!r}") from exc


def derive_seed(base_seed: int, repeat_index: int) -> int:
    """Детерминированный seed для повтора эксперимента."""

    return int((validate_seed(base_seed) + (repeat_index + 1) * 7919) % (2**32))


def depth_values(base_operations: int, max_operations: int) -> Tuple[float, ...]:
    """Числа операций для эксперимента с глубиной (шаг — 2 операции)."""

    if max_operations <= base_operations:
        raise ValueError(
            "Максимальное число операций должно быть больше базовой схемы."
        )
    values: List[float] = []
    extra = base_operations
    while extra <= max_operations:
        values.append(float(extra))
        extra += 2
    if len(values) > MAX_POINTS:
        raise ValueError("Слишком много точек для эксперимента с глубиной.")
    return tuple(values)


def circuit_with_depth(base: Circuit, total_operations: int) -> Circuit:
    """Дополнить схему парами CNOT, не меняющими идеальное состояние.

    Пары CNOT(control=0, target=1) взаимно уничтожаются, поэтому
    идеальное распределение базовой схемы сохраняется, а число операций
    растёт.
    """

    if total_operations < base.gate_count:
        raise ValueError(
            "Число операций не может быть меньше числа операций базовой схемы."
        )
    extra = int(total_operations) - base.gate_count
    if extra % 2 != 0:
        raise ValueError("Число добавленных операций должно быть чётным.")
    if base.n_qubits < 2:
        raise ValueError(
            "Для эксперимента с глубиной нужна схема как минимум из 2 кубитов."
        )
    circuit = base.copy()
    for _ in range(extra // 2):
        circuit.add(Operation(gate="cnot", control=0, target=1))
        circuit.add(Operation(gate="cnot", control=0, target=1))
    return circuit


@dataclass(frozen=True)
class ExperimentSpec:
    """Параметры запуска серии экспериментов."""

    kind: str
    circuit: Circuit
    shots: int = 1000
    repeats: int = 10
    seed: int = 2024
    target: str | None = None
    values: Tuple[float, ...] = ()
    p_fixed: float = 0.02
    max_operations: int = 20
    shots_grid: Tuple[int, ...] = ()

    def validate(self) -> None:
        kind_info(self.kind)
        validate_shots(self.shots)
        validate_seed(self.seed)
        if isinstance(self.repeats, bool) or not isinstance(self.repeats, int):
            raise ValueError("Число повторов должно быть целым.")
        if not 1 <= self.repeats <= MAX_REPEATS:
            raise ValueError(
                f"Число повторов должно быть от 1 до {MAX_REPEATS}, "
                f"получено {self.repeats}."
            )
        if self.kind in ("bitflip", "phaseflip", "readout", "compare"):
            if not self.values:
                raise ValueError("Не задана сетка вероятностей эксперимента.")
            if len(self.values) > MAX_POINTS:
                raise ValueError(f"Слишком много точек: {len(self.values)}.")
            for value in self.values:
                if not 0.0 <= float(value) <= 1.0:
                    raise ValueError(
                        f"Вероятность {value} вне диапазона 0…1."
                    )
        if self.kind in ("depth", "shots"):
            if not 0.0 <= float(self.p_fixed) <= 1.0:
                raise ValueError("Фиксированная вероятность должна быть от 0 до 1.")
        if self.kind == "depth" and self.circuit.n_qubits < 2:
            raise ValueError(
                "Для эксперимента с глубиной нужна схема минимум из 2 кубитов."
            )
        if self.kind == "shots":
            if not self.shots_grid:
                raise ValueError("Не задана сетка числа измерений (shots).")
            if len(self.shots_grid) > MAX_POINTS:
                raise ValueError("Слишком много точек в сетке shots.")
            if len(set(self.shots_grid)) != len(self.shots_grid):
                raise ValueError("Значения shots не должны повторяться.")
            for value in self.shots_grid:
                validate_shots(int(value))
        if self.target:
            width = self.circuit.measured_count
            labels = {format(index, f"0{width}b") for index in range(2**width)}
            if self.target not in labels:
                raise ValueError(
                    f"Целевая строка {self.target!r} не входит в набор "
                    "возможных исходов схемы."
                )
        if estimate_total_runs(self) > MAX_TOTAL_RUNS:
            raise ValueError(
                "Слишком много запусков в серии. Уменьшите число точек, "
                "повторов или shots."
            )


def estimate_total_runs(spec: ExperimentSpec) -> int:
    """Оценка числа запусков симулятора в серии."""

    if spec.kind == "compare":
        series_count = 3
        point_count = len(spec.values)
    elif spec.kind == "depth":
        series_count = 1
        point_count = max(1, len(range(spec.circuit.gate_count, spec.max_operations + 1, 2)))
    elif spec.kind == "shots":
        series_count = 1
        point_count = len(spec.shots_grid)
    else:
        series_count = 1
        point_count = len(spec.values)
    return series_count * point_count * spec.repeats


def _noise_for_channel(channel: str, probability: float) -> NoiseConfig:
    """Настройки ошибок только для выбранного канала."""

    return NoiseConfig(
        enabled=True,
        bit_flip_enabled=(channel == CHANNEL_BIT_FLIP),
        phase_flip_enabled=(channel == CHANNEL_PHASE_FLIP),
        readout_enabled=(channel == CHANNEL_READOUT),
        p_bit_flip=probability if channel == CHANNEL_BIT_FLIP else 0.0,
        p_phase_flip=probability if channel == CHANNEL_PHASE_FLIP else 0.0,
        p_readout=probability if channel == CHANNEL_READOUT else 0.0,
    )


@dataclass
class ExperimentPoint:
    """Одна точка эксперимента (агрегированная по повторам)."""

    value: float
    mean: float
    std: float
    ci_low: float
    ci_high: float
    floor_mean: float
    target_probability_mean: float | None
    repeats: int

    @property
    def value_label(self) -> str:
        return f"{self.value:g}"


@dataclass
class ExperimentSeries:
    """Набор точек для одной кривой."""

    key: str
    label: str
    points: List[ExperimentPoint] = field(default_factory=list)
    raw_rows: List[dict] = field(default_factory=list)


@dataclass
class ExperimentResult:
    """Результат выполненной серии экспериментов."""

    kind: str
    title: str
    description: str
    x_label: str
    y_label: str
    series: List[ExperimentSeries]
    shots: int
    repeats: int
    seed: int
    target: str | None
    circuit_name: str
    params_note: str
    notes: str
    created_at: str
    duration_s: float

    @property
    def total_runs(self) -> int:
        return sum(len(series.raw_rows) for series in self.series)

    def series_by_key(self, key: str) -> ExperimentSeries:
        for series in self.series:
            if series.key == key:
                return series
        raise KeyError(f"Серия {key!r} не найдена.")

    def point_values(self) -> List[float]:
        if not self.series:
            return []
        return [point.value for point in self.series[0].points]

    def raw_rows(self) -> List[dict]:
        rows: List[dict] = []
        for series in self.series:
            rows.extend(series.raw_rows)
        return rows


ProgressCallback = Callable[[int, int, str], None]


def run_experiment(
    spec: ExperimentSpec, progress: ProgressCallback | None = None
) -> ExperimentResult:
    """Выполнить серию экспериментов и собрать агрегированные метрики."""

    spec.validate()
    info = kind_info(spec.kind)

    if spec.kind == "compare":
        series_plan = [
            (CHANNEL_BIT_FLIP, CHANNEL_LABELS[CHANNEL_BIT_FLIP]),
            (CHANNEL_PHASE_FLIP, CHANNEL_LABELS[CHANNEL_PHASE_FLIP]),
            (CHANNEL_READOUT, CHANNEL_LABELS[CHANNEL_READOUT]),
        ]
        values = tuple(spec.values)
    elif spec.kind == "depth":
        channel = info.default_channel or CHANNEL_BIT_FLIP
        series_plan = [(channel, f"{CHANNEL_LABELS[channel]}, p = {spec.p_fixed:g}")]
        values = depth_values(spec.circuit.gate_count, spec.max_operations)
    elif spec.kind == "shots":
        channel = info.default_channel or CHANNEL_BIT_FLIP
        series_plan = [(channel, f"{CHANNEL_LABELS[channel]}, p = {spec.p_fixed:g}")]
        values = tuple(float(value) for value in spec.shots_grid)
    else:
        channel = info.default_channel or CHANNEL_BIT_FLIP
        series_plan = [(channel, CHANNEL_LABELS[channel])]
        values = tuple(spec.values)

    total = len(series_plan) * len(values) * spec.repeats
    done = 0
    started = time.perf_counter()
    series_results: List[ExperimentSeries] = []

    for channel, label in series_plan:
        series = ExperimentSeries(key=channel, label=label)
        for value in values:
            if spec.kind == "depth":
                circuit = circuit_with_depth(spec.circuit, int(value))
                noise = _noise_for_channel(channel, spec.p_fixed)
                shots_used = spec.shots
            elif spec.kind == "shots":
                circuit = spec.circuit
                noise = _noise_for_channel(channel, spec.p_fixed)
                shots_used = int(value)
            else:
                circuit = spec.circuit
                noise = _noise_for_channel(channel, float(value))
                shots_used = spec.shots

            tvd_values: List[float] = []
            floor_values: List[float] = []
            target_values: List[float] = []
            for repeat in range(spec.repeats):
                seed = derive_seed(spec.seed, repeat)
                result = run_circuit(circuit, shots=shots_used, seed=seed, noise=noise)
                metrics = metrics_for_result(result, spec.target)
                tvd_values.append(metrics.tvd_ideal_vs_observed)
                floor_values.append(metrics.tvd_noise_floor)
                if metrics.target_probability_observed is not None:
                    target_values.append(metrics.target_probability_observed)
                series.raw_rows.append(
                    {
                        "Вид эксперимента": info.title,
                        "Серия": label,
                        "Параметр": float(value),
                        "Повтор": repeat + 1,
                        "TVD": metrics.tvd_ideal_vs_observed,
                        "Шумовой уровень": metrics.tvd_noise_floor,
                        "Целевая вероятность": metrics.target_probability_observed,
                        "shots": shots_used,
                        "seed": seed,
                    }
                )
                done += 1
                if progress is not None:
                    progress(
                        done,
                        total,
                        f"{label}: параметр {value:g}, повтор {repeat + 1}/{spec.repeats}",
                    )

            mean, std = mean_std(tvd_values)
            ci_low, ci_high = _confidence_bounds(tvd_values)
            series.points.append(
                ExperimentPoint(
                    value=float(value),
                    mean=mean,
                    std=std,
                    ci_low=ci_low,
                    ci_high=ci_high,
                    floor_mean=float(np.mean(floor_values)),
                    target_probability_mean=(
                        float(np.mean(target_values)) if target_values else None
                    ),
                    repeats=spec.repeats,
                )
            )
        series_results.append(series)

    duration = time.perf_counter() - started
    params_note = _params_note(spec)
    return ExperimentResult(
        kind=spec.kind,
        title=info.title,
        description=info.description,
        x_label=info.x_label,
        y_label=info.y_label,
        series=series_results,
        shots=0 if spec.kind == "shots" else spec.shots,
        repeats=spec.repeats,
        seed=spec.seed,
        target=spec.target,
        circuit_name=spec.circuit.name,
        params_note=params_note,
        notes=info.notes,
        created_at=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        duration_s=duration,
    )


def _confidence_bounds(values: Sequence[float]) -> Tuple[float, float]:
    """Границы 95 % доверительного интервала для среднего."""
    _, low, high = confidence_interval_95(values)
    return low, high


def _params_note(spec: ExperimentSpec) -> str:
    if spec.kind == "shots":
        shots_text = ", ".join(f"{int(value)}" for value in spec.shots_grid)
        parts = [
            f"shots: {shots_text}",
            f"повторов = {spec.repeats}",
            f"seed = {spec.seed}",
        ]
        channel = kind_info(spec.kind).default_channel or CHANNEL_BIT_FLIP
        parts.append(f"p = {spec.p_fixed:g} ({CHANNEL_LABELS[channel]})")
        if spec.target:
            parts.append(f"целевая строка = {spec.target}")
        return "; ".join(parts)

    parts = [
        f"shots = {spec.shots}",
        f"повторов = {spec.repeats}",
        f"seed = {spec.seed}",
    ]
    if spec.kind == "depth":
        channel = kind_info(spec.kind).default_channel or CHANNEL_BIT_FLIP
        parts.append(f"p = {spec.p_fixed:g} ({CHANNEL_LABELS[channel]})")
    if spec.target:
        parts.append(f"целевая строка = {spec.target}")
    return "; ".join(parts)


__all__ = [
    "CHANNEL_BIT_FLIP",
    "DEFAULT_SHOTS_GRID",
    "CHANNEL_LABELS",
    "CHANNEL_PHASE_FLIP",
    "CHANNEL_READOUT",
    "EXPERIMENT_KINDS",
    "ExperimentKindInfo",
    "ExperimentPoint",
    "ExperimentResult",
    "ExperimentSeries",
    "ExperimentSpec",
    "MAX_REPEATS",
    "circuit_with_depth",
    "depth_values",
    "derive_seed",
    "estimate_total_runs",
    "experiment_kinds",
    "kind_info",
    "probability_grid",
    "run_experiment",
]
