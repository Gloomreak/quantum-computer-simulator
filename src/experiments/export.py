"""Экспорт результатов: CSV с данными и PNG с графиками.

CSV сохраняется в кодировке UTF-8 с BOM, чтобы русские заголовки
корректно открывались в Excel. Таблицы имеют «аккуратный» вид: одна
строка — одно измерение или одна точка эксперимента, все параметры
запуска присутствуют в виде столбцов или в имени файла.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from ..quantum.simulator import MODE_NOISY, SimulationResult
from .runner import ExperimentResult

RUN_COLUMNS: List[str] = [
    "Битовая строка",
    "Теоретическая вероятность",
    "Идеально: число измерений",
    "Идеально: частота",
    "С шумом: число измерений",
    "С шумом: частота",
]

AGGREGATED_COLUMNS: List[str] = [
    "Серия",
    "Параметр",
    "Средний TVD",
    "Стандартное отклонение",
    "95% ДИ (низ)",
    "95% ДИ (верх)",
    "Шумовой уровень",
    "Средняя целевая вероятность",
    "Повторов",
]

RAW_COLUMNS: List[str] = [
    "Вид эксперимента",
    "Серия",
    "Параметр",
    "Повтор",
    "TVD",
    "Шумовой уровень",
    "Целевая вероятность",
    "shots",
    "seed",
]


def run_rows(result: SimulationResult) -> List[dict]:
    """Строки таблицы распределения для одного запуска."""

    ideal_total = max(1, sum(result.ideal_counts.values()))
    noisy_total = (
        max(1, sum(result.noisy_counts.values())) if result.noisy_counts is not None else 0
    )
    rows: List[dict] = []
    for index, label in enumerate(result.labels):
        row = {
            "Битовая строка": label,
            "Теоретическая вероятность": round(
                float(result.ideal_probabilities[index]), 8
            ),
            "Идеально: число измерений": int(result.ideal_counts.get(label, 0)),
            "Идеально: частота": round(
                result.ideal_counts.get(label, 0) / ideal_total, 8
            ),
        }
        if result.noisy_counts is not None:
            row["С шумом: число измерений"] = int(result.noisy_counts.get(label, 0))
            row["С шумом: частота"] = round(
                result.noisy_counts.get(label, 0) / noisy_total, 8
            )
        else:
            row["С шумом: число измерений"] = None
            row["С шумом: частота"] = None
        rows.append(row)
    return rows


def run_dataframe(result: SimulationResult) -> pd.DataFrame:
    """Таблица распределения запуска (pandas DataFrame)."""

    return pd.DataFrame(run_rows(result), columns=RUN_COLUMNS)


def run_csv_bytes(result: SimulationResult) -> bytes:
    """CSV с распределением одного запуска."""

    frame = run_dataframe(result)
    header = (
        f"# Режим: {'модель с ошибками' if result.mode == MODE_NOISY else 'идеальная модель'}; "
        f"shots = {result.shots}; seed = {result.seed}; "
        f"ошибки: {result.noise.summary()}; "
        f"кубиты измерения: {', '.join('q' + str(q) for q in result.measured_qubits)}\n"
    )
    return (header + frame.to_csv(index=False)).encode("utf-8-sig")


def experiment_aggregated_rows(result: ExperimentResult) -> List[dict]:
    """Агрегированные по повторам строки эксперимента."""

    rows: List[dict] = []
    for series in result.series:
        for point in series.points:
            rows.append(
                {
                    "Серия": series.label,
                    "Параметр": point.value,
                    "Средний TVD": round(point.mean, 8),
                    "Стандартное отклонение": round(point.std, 8),
                    "95% ДИ (низ)": round(point.ci_low, 8),
                    "95% ДИ (верх)": round(point.ci_high, 8),
                    "Шумовой уровень": round(point.floor_mean, 8),
                    "Средняя целевая вероятность": (
                        None
                        if point.target_probability_mean is None
                        else round(point.target_probability_mean, 8)
                    ),
                    "Повторов": point.repeats,
                }
            )
    return rows


def experiment_aggregated_dataframe(result: ExperimentResult) -> pd.DataFrame:
    """Агрегированная таблица эксперимента."""

    return pd.DataFrame(experiment_aggregated_rows(result), columns=AGGREGATED_COLUMNS)


def experiment_raw_dataframe(result: ExperimentResult) -> pd.DataFrame:
    """Таблица всех отдельных запусков эксперимента."""

    return pd.DataFrame(result.raw_rows(), columns=RAW_COLUMNS)


def experiment_csv_bytes(result: ExperimentResult, aggregated: bool = False) -> bytes:
    """CSV с результатами эксперимента.

    ``aggregated=False`` выгружает все отдельные запуски (по ним можно
    пересчитать статистику самостоятельно), ``aggregated=True`` — только
    средние значения по точкам.
    """

    frame = (
        experiment_aggregated_dataframe(result)
        if aggregated
        else experiment_raw_dataframe(result)
    )
    header = (
        f"# {result.title}; {result.params_note}; "
        f"создано: {result.created_at}; всего запусков: {result.total_runs}\n"
    )
    return (header + frame.to_csv(index=False)).encode("utf-8-sig")


def save_bytes(data: bytes, path: str | Path) -> Path:
    """Сохранить байты в файл, создав каталоги при необходимости."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def save_experiment_csv(
    result: ExperimentResult, path: str | Path, aggregated: bool = False
) -> Path:
    """Сохранить результаты эксперимента в CSV."""

    return save_bytes(experiment_csv_bytes(result, aggregated=aggregated), path)


def save_run_csv(result: SimulationResult, path: str | Path) -> Path:
    """Сохранить распределение одного запуска в CSV."""

    return save_bytes(run_csv_bytes(result), path)


def save_png(png_bytes: bytes, path: str | Path) -> Path:
    """Сохранить PNG-изображение."""

    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Переданные данные не являются PNG-изображением.")
    return save_bytes(png_bytes, path)


__all__ = [
    "AGGREGATED_COLUMNS",
    "RAW_COLUMNS",
    "RUN_COLUMNS",
    "experiment_aggregated_dataframe",
    "experiment_aggregated_rows",
    "experiment_csv_bytes",
    "experiment_raw_dataframe",
    "run_csv_bytes",
    "run_dataframe",
    "run_rows",
    "save_bytes",
    "save_experiment_csv",
    "save_png",
    "save_run_csv",
]
