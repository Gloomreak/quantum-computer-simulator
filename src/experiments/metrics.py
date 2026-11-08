"""Метрики сравнения распределений результатов измерения.

Основная метрика — полное вариационное расстояние (TVD):

.. math::

    \\mathrm{TVD}(P, Q) = \\frac{1}{2} \\sum_x |P(x) - Q(x)|

TVD лежит в диапазоне от 0 до 1 и имеет простой смысл: это доля
вероятностной массы, которую нужно «перенести», чтобы одно
распределение стало другим. Для распределения результатов измерения
TVD удобнее, чем, например, KL-дивергенция, потому что он симметричен
и определён для нулевых вероятностей.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

from ..quantum.simulator import MODE_NOISY, SimulationResult

TVD_TOLERANCE: float = 1e-9


def as_distribution(values: Sequence[float]) -> np.ndarray:
    """Проверить, что массив является распределением вероятностей."""

    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or array.size == 0:
        raise ValueError("Ожидался непустой одномерный массив вероятностей.")
    if np.any(array < -TVD_TOLERANCE):
        raise ValueError("Вероятности не могут быть отрицательными.")
    array = np.clip(array, 0.0, None)
    total = float(array.sum())
    if total <= 0.0:
        raise ValueError("Сумма вероятностей должна быть положительной.")
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"Сумма вероятностей должна быть равна 1 (получено {total:.6f})."
        )
    return array / total


def total_variation_distance(
    ideal: Sequence[float], observed: Sequence[float]
) -> float:
    """Полное вариационное расстояние между двумя распределениями."""

    first = as_distribution(ideal)
    second = as_distribution(observed)
    if first.shape != second.shape:
        raise ValueError(
            "Распределения должны иметь одинаковую длину: "
            f"{first.size} и {second.size}."
        )
    return float(0.5 * np.sum(np.abs(first - second)))


def target_probability(
    probabilities: Sequence[float], labels: Sequence[str], target: str
) -> float:
    """Вероятность указанной битовой строки."""

    labels_list = list(labels)
    if target not in labels_list:
        raise ValueError(
            f"Строка {target!r} недоступна: допустимые варианты — "
            + ", ".join(labels_list)
            + "."
        )
    return float(np.asarray(probabilities, dtype=float)[labels_list.index(target)])


def success_rate(counts: Dict[str, int], target: str) -> float:
    """Доля запусков, в которых получена целевая битовая строка."""

    total = sum(counts.values())
    if total <= 0:
        raise ValueError("Сумма частот должна быть положительной.")
    return counts.get(target, 0) / total


@dataclass(frozen=True)
class RunMetrics:
    """Сводные показатели одного запуска схемы."""

    mode: str
    tvd_ideal_vs_observed: float
    tvd_noise_floor: float
    tvd_ideal_sample_vs_observed: float | None
    target: str | None
    target_probability_ideal: float | None
    target_probability_observed: float | None
    success_rate: float | None
    shots: int

    @property
    def is_noisy(self) -> bool:
        return self.mode == MODE_NOISY


def metrics_for_result(
    result: SimulationResult,
    target: str | None = None,
) -> RunMetrics:
    """Вычислить метрики запуска.

    ``tvd_ideal_vs_observed`` сравнивает теоретические вероятности
    идеального исполнения с наблюдаемыми частотами выбранного режима.
    ``tvd_noise_floor`` — уровень, создаваемый конечным числом измерений:
    сравнение тех же теоретических вероятностей с идеальной выборкой.
    Он полезен, чтобы отделить вклад квантовых ошибок от статистического
    разброса.
    """

    ideal = result.ideal_probabilities
    observed = result.observed_probabilities
    ideal_sample = result.ideal_observed_probabilities

    tvd_observed = total_variation_distance(ideal, observed)
    floor = total_variation_distance(ideal, ideal_sample)
    tvd_between_runs = None
    if result.noisy_counts is not None:
        tvd_between_runs = total_variation_distance(ideal_sample, observed)

    target_ideal: float | None = None
    target_observed: float | None = None
    target_success: float | None = None
    normalized_target: str | None = None
    if target:
        normalized_target = target.strip()
        if normalized_target:
            labels = list(result.labels)
            if normalized_target not in labels:
                raise ValueError(
                    f"Целевая строка {normalized_target!r} не входит в набор "
                    "возможных исходов: " + ", ".join(labels) + "."
                )
            target_ideal = float(ideal[labels.index(normalized_target)])
            target_observed = float(observed[labels.index(normalized_target)])
            target_success = success_rate(result.counts, normalized_target)

    return RunMetrics(
        mode=result.mode,
        tvd_ideal_vs_observed=tvd_observed,
        tvd_noise_floor=floor,
        tvd_ideal_sample_vs_observed=tvd_between_runs,
        target=normalized_target,
        target_probability_ideal=target_ideal,
        target_probability_observed=target_observed,
        success_rate=target_success,
        shots=result.shots,
    )


def mean_std(values: Iterable[float]) -> Tuple[float, float]:
    """Среднее и (несмещённое) стандартное отклонение выборки."""

    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        raise ValueError("Нельзя вычислить статистику по пустому набору.")
    if array.size == 1:
        return float(array[0]), 0.0
    return float(array.mean()), float(array.std(ddof=1))


def confidence_interval_95(values: Iterable[float]) -> Tuple[float, float, float]:
    """Среднее значение и 95 % доверительный интервал (нормальное приближение).

    Возвращает ``(mean, low, high)``. Для выборки из одного повтора
    интервал вырождается в точку.
    """

    array = np.asarray(list(values), dtype=float)
    mean, std = mean_std(array)
    if array.size < 2:
        return mean, mean, mean
    half_width = 1.96 * std / np.sqrt(array.size)
    return mean, float(mean - half_width), float(mean + half_width)


def distribution_table(
    labels: Sequence[str],
    ideal: Sequence[float],
    counts: Dict[str, int] | None = None,
) -> List[dict]:
    """Таблица распределения для интерфейса.

    Столбцы: битовая строка, теоретическая вероятность, число измерений
    и наблюдаемая частота (если частоты переданы).
    """

    total = sum(counts.values()) if counts else 0
    rows: List[dict] = []
    for index, label in enumerate(labels):
        row = {"Битовая строка": label, "Теоретическая вероятность": round(float(ideal[index]), 6)}
        if counts is not None:
            count = int(counts.get(label, 0))
            row["Число измерений"] = count
            row["Наблюдаемая частота"] = round(count / total, 6) if total else 0.0
        rows.append(row)
    return rows


__all__ = [
    "RunMetrics",
    "as_distribution",
    "confidence_interval_95",
    "distribution_table",
    "mean_std",
    "metrics_for_result",
    "success_rate",
    "target_probability",
    "total_variation_distance",
]
