"""Раздел «Аппаратные ошибки»: настройка каналов и сравнение режимов."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import streamlit as st

from ..experiments.metrics import metrics_for_result
from ..quantum.noise import CHANNEL_INFO, UI_MAX_PROBABILITY, channel_summary
from ..quantum.simulator import run_circuit
from ..render import BarSeries, bar_chart
from .common import (
    chart_block,
    metric_row,
    page_header,
    section,
    target_metrics,
    validation_messages,
)
from .state import (
    get_circuit,
    get_noise,
    set_noise,
    show_notice,
)

MODE_IDEAL_LABEL = "Идеальная модель"
MODE_NOISY_LABEL = "Модель с ошибками"


def _render_mode(noise):
    """Переключатель «идеально / с ошибками»."""

    section(
        "Режим исполнения",
        "Ошибки вентилей и считывания можно включать независимо.",
    )
    mode = st.radio(
        "Режим",
        options=[MODE_IDEAL_LABEL, MODE_NOISY_LABEL],
        index=1 if noise.enabled else 0,
        horizontal=True,
        key="noise_mode",
        label_visibility="collapsed",
    )
    enabled = mode == MODE_NOISY_LABEL
    if enabled != noise.enabled:
        noise = replace(noise, enabled=enabled)
        set_noise(noise)
    return noise, enabled


def _render_channels(noise, enabled: bool):
    """Флаги каналов и вероятности."""

    section(
        "Каналы ошибок",
        "Диапазон вероятностей в интерфейсе — от 0 до 0,2, как в техническом задании.",
    )
    columns = st.columns(3)

    with columns[0]:
        bit_flip = st.toggle(
            "Bit-flip (X)",
            value=noise.bit_flip_enabled,
            disabled=not enabled,
            key="noise_bit_flip_toggle",
            help="Случайный переворот бита после вентиля.",
        )
        p_bit_flip = st.slider(
            "Вероятность p (bit-flip)",
            min_value=0.0,
            max_value=UI_MAX_PROBABILITY,
            step=0.01,
            value=float(noise.p_bit_flip),
            disabled=not enabled or not bit_flip,
            key="noise_bit_flip_prob",
        )
    with columns[1]:
        phase_flip = st.toggle(
            "Phase-flip (Z)",
            value=noise.phase_flip_enabled,
            disabled=not enabled,
            key="noise_phase_flip_toggle",
            help="Случайная фазовая ошибка после вентиля.",
        )
        p_phase_flip = st.slider(
            "Вероятность p (phase-flip)",
            min_value=0.0,
            max_value=UI_MAX_PROBABILITY,
            step=0.01,
            value=float(noise.p_phase_flip),
            disabled=not enabled or not phase_flip,
            key="noise_phase_flip_prob",
        )
    with columns[2]:
        readout = st.toggle(
            "Ошибка считывания",
            value=noise.readout_enabled,
            disabled=not enabled,
            key="noise_readout_toggle",
            help="Инверсия измеренного бита с заданной вероятностью.",
        )
        p_readout = st.slider(
            "Вероятность p (считывание)",
            min_value=0.0,
            max_value=UI_MAX_PROBABILITY,
            step=0.01,
            value=float(noise.p_readout),
            disabled=not enabled or not readout,
            key="noise_readout_prob",
        )

    updated = replace(
        noise,
        bit_flip_enabled=bool(bit_flip),
        phase_flip_enabled=bool(phase_flip),
        readout_enabled=bool(readout),
        p_bit_flip=float(p_bit_flip),
        p_phase_flip=float(p_phase_flip),
        p_readout=float(p_readout),
    )
    if updated != noise:
        set_noise(updated)
    return updated


def _render_explanations() -> None:
    """Пояснения к моделям ошибок и их ограничениям."""

    st.markdown("**Что означает каждая модель**")
    for key in ("bit_flip", "phase_flip", "readout"):
        info = CHANNEL_INFO[key]
        with st.expander(info["name"], expanded=False):
            st.markdown(info["description"])
            st.caption(f"Ограничение модели: {info['limitations']}")

    st.info(
        "**Порядок применения ошибок.** Ошибки вентилей разыгрываются после "
        "применения вентиля: для однокубитного вентиля — к целевому кубиту, "
        "для CNOT — независимо к управляющему и целевому кубитам. Ошибка "
        "считывания применяется уже после измерения и не влияет на квантовое "
        "состояние. Все три модели — учебные упрощения: они не описывают "
        "амплитудное затухание, деполяризацию и корреляцию ошибок во времени."
    )


def _render_status(noise) -> None:
    """Таблица текущих настроек каналов."""

    rows = channel_summary(noise)
    frame = pd.DataFrame(rows).rename(
        columns={
            "name": "Канал",
            "status": "Статус",
            "probability": "Вероятность",
            "description": "Как действует",
            "limitations": "Ограничения",
        }
    )
    st.dataframe(
        frame,
        hide_index=True,
        column_config={
            "Канал": st.column_config.TextColumn(width="small"),
            "Статус": st.column_config.TextColumn(width="small"),
            "Как действует": st.column_config.TextColumn(width="medium"),
            "Ограничения": st.column_config.TextColumn(width="medium"),
        },
    )


def _render_comparison(noise, circuit, shots: int, seed: int) -> None:
    """Сравнить идеальное и шумовое исполнение на текущей схеме."""

    section(
        "Сравнение идеального и шумового исполнения",
        "Строится по текущей схеме и текущим shots/seed (они задаются в разделе "
        "«Запуск и результаты»).",
    )
    is_valid = validation_messages(circuit)
    if not is_valid:
        st.warning("Схема содержит ошибки: сравнение невозможно.")
        return

    ideal = run_circuit(circuit, shots=shots, seed=seed)
    noisy = run_circuit(circuit, shots=shots, seed=seed, noise=noise)

    if not noise.is_active:
        st.info(
            "Каналы ошибок не активны (режим «Идеальная модель» или все "
            "вероятности равны 0): шумовой запуск совпадает с идеальным."
        )

    labels = list(ideal.labels)
    observed = (
        noisy.probabilities_for("noisy")
        if noisy.noisy_counts is not None
        else noisy.ideal_observed_probabilities
    )
    observed_label = (
        "С ошибками (измерено)" if noisy.noisy_counts is not None else "Без ошибок (измерено)"
    )
    png = bar_chart(
        labels,
        [
            BarSeries("Идеально (теория)", ideal.ideal_probabilities, "#94A3B8"),
            BarSeries(observed_label, observed, "#2563EB"),
        ],
        "Идеальное и зашумлённое распределения",
        subtitle=f"{circuit.name} · shots = {shots} · seed = {seed}",
        x_label="Битовая строка",
        y_label="Вероятность",
        width=900,
    )
    chart_block(
        png,
        "Серые столбцы — теоретические вероятности идеального исполнения, "
        "синие — частоты при включённых ошибках.",
        "noise_comparison.png",
        "download_noise_comparison_png",
    )

    target = st.session_state.get("target", "").strip()
    if target and target not in labels:
        target = ""
    metrics = metrics_for_result(noisy, target or None)
    metric_row(
        [
            (
                "TVD(идеал, шум)",
                f"{metrics.tvd_ideal_vs_observed:.3f}",
                "TVD между идеальными вероятностями и измеренными частотами.",
            ),
            (
                "Статистический разброс",
                f"{metrics.tvd_noise_floor:.3f}",
                "TVD без ошибок при тех же shots — уровень шума выборки.",
            ),
            ("shots", str(shots), "Число измерений в каждом запуске."),
        ]
    )
    if target:
        target_metrics(noisy, target)


def render() -> None:
    page_header(
        "Модели аппаратных ошибок",
        "Ошибки переворота бита, фазовые ошибки и ошибки считывания: "
        "настройка, пояснения и сравнение режимов.",
    )
    show_notice()

    circuit = get_circuit()
    noise = get_noise()

    noise, enabled = _render_mode(noise)
    noise = _render_channels(noise, enabled)

    st.caption(f"Текущая конфигурация: **{noise.summary()}**")
    _render_status(noise)
    _render_explanations()

    st.divider()
    _render_comparison(
        noise,
        circuit,
        shots=int(st.session_state["shots"]),
        seed=int(st.session_state["seed"]),
    )


__all__ = ["render"]
