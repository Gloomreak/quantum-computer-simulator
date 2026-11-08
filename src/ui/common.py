"""Общие элементы интерфейса: заголовки, карточки метрик, экспорт."""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import streamlit as st

from ..experiments.metrics import metrics_for_result
from ..quantum.circuit import Circuit
from ..quantum.noise import NoiseConfig
from ..quantum.simulator import MODE_NOISY, SimulationResult


def page_header(title: str, subtitle: str = "") -> None:
    """Заголовок страницы с пояснением."""

    st.title(title)
    if subtitle:
        st.caption(subtitle)


def section(title: str, subtitle: str = "") -> None:
    """Подзаголовок раздела."""

    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def chart_block(
    png_bytes: bytes,
    caption: str,
    file_name: str,
    download_key: str,
    download_label: str = "Скачать график (PNG)",
) -> None:
    """Показать график и кнопку сохранения PNG."""

    st.image(png_bytes, caption=caption)
    st.download_button(
        download_label,
        data=png_bytes,
        file_name=file_name,
        mime="image/png",
        key=download_key,
    )


def metric_row(items: Sequence[tuple[str, str, str | None]]) -> None:
    """Ряд карточек с метриками.

    ``items`` — тройки (подпись, значение, пояснение).
    """

    columns = st.columns(len(items))
    for column, (label, value, help_text) in zip(columns, items):
        with column:
            st.metric(label, value, help=help_text)


def validation_messages(circuit: Circuit) -> bool:
    """Показать замечания к схеме. Вернуть ``True``, если схему можно запускать."""

    issues = circuit.validate()
    errors = [issue for issue in issues if issue.is_error]
    warnings = [issue for issue in issues if not issue.is_error]
    for issue in errors:
        st.error(issue.message)
    for issue in warnings:
        st.warning(issue.message)
    return not errors


def noise_summary(noise: NoiseConfig) -> str:
    """Краткое описание текущей модели ошибок."""

    return noise.summary()


def run_parameters_text(result: SimulationResult) -> str:
    """Строка параметров выполненного запуска."""

    mode = "модель с ошибками" if result.mode == MODE_NOISY else "идеальная модель"
    measured = ", ".join(f"q{q}" for q in result.measured_qubits) or "—"
    parts = [
        f"Режим: {mode}",
        f"shots = {result.shots}",
        f"seed = {result.seed}",
        f"измеряются: {measured}",
    ]
    if result.mode == MODE_NOISY:
        parts.append(f"ошибки: {result.noise.summary()}")
    parts.append(f"время расчёта: {result.duration_s * 1000:.0f} мс")
    return " · ".join(parts)


def run_distribution_frame(result: SimulationResult) -> pd.DataFrame:
    """Таблица распределения с подписями для интерфейса."""

    rows = []
    ideal_total = max(1, sum(result.ideal_counts.values()))
    observed_total = max(1, sum(result.counts.values()))
    for index, label in enumerate(result.labels):
        rows.append(
            {
                "Битовая строка": label,
                "Теоретическая вероятность": round(
                    float(result.ideal_probabilities[index]), 6
                ),
                "Идеально: число": result.ideal_counts.get(label, 0),
                "Идеально: частота": round(
                    result.ideal_counts.get(label, 0) / ideal_total, 6
                ),
                "Измерено: число": result.counts.get(label, 0),
                "Измерено: частота": round(
                    result.counts.get(label, 0) / observed_total, 6
                ),
            }
        )
    return pd.DataFrame(rows)


def target_metrics(result: SimulationResult, target: str) -> None:
    """Показать метрики по целевой битовой строке."""

    if not target:
        st.caption(
            "Целевая битовая строка не задана. Укажите её в параметрах запуска, "
            "чтобы отслеживать вероятность успеха."
        )
        return
    metrics = metrics_for_result(result, target)
    metric_row(
        [
            (
                f"P({target}) в идеальной модели",
                f"{metrics.target_probability_ideal:.4f}",
                "Теоретическая вероятность выбранного результата.",
            ),
            (
                f"P({target}) в текущем запуске",
                f"{metrics.target_probability_observed:.4f}",
                "Наблюдаемая частота выбранного результата.",
            ),
            (
                "Доля успешных запусков",
                f"{(metrics.success_rate or 0.0) * 100:.1f}%",
                "Доля измерений, в которых получена целевая строка.",
            ),
        ]
    )


def experiment_table(result) -> pd.DataFrame:
    """Агрегированная таблица эксперимента для отображения."""

    rows = []
    for series in result.series:
        for point in series.points:
            rows.append(
                {
                    "Серия": series.label,
                    "Параметр": point.value,
                    "Средний TVD": round(point.mean, 4),
                    "Стандартное отклонение": round(point.std, 4),
                    "95% ДИ (низ)": round(point.ci_low, 4),
                    "95% ДИ (верх)": round(point.ci_high, 4),
                    "Шумовой уровень": round(point.floor_mean, 4),
                    "Повторов": point.repeats,
                }
            )
    return pd.DataFrame(rows)


__all__ = [
    "chart_block",
    "experiment_table",
    "metric_row",
    "noise_summary",
    "page_header",
    "run_distribution_frame",
    "run_parameters_text",
    "section",
    "target_metrics",
    "validation_messages",
]
