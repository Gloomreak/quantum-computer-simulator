"""Раздел «Запуск и результаты»: параметры, распределения, сравнение."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..experiments.export import run_csv_bytes
from ..experiments.metrics import metrics_for_result
from ..quantum.simulator import (
    described_state,
    memory_estimate,
    run_circuit,
)
from ..quantum.statevector import QuantumState
from ..render import BarSeries, bar_chart, circuit_diagram
from .common import (
    chart_block,
    metric_row,
    page_header,
    run_distribution_frame,
    run_parameters_text,
    section,
    target_metrics,
    validation_messages,
)
from .state import (
    NAV_NOISE,
    get_circuit,
    get_noise,
    get_result,
    navigate,
    run_signature,
    set_result,
    show_notice,
)

CHART_WIDTH = 900


def _execute(circuit, shots: int, seed: int, noise) -> None:
    """Выполнить схему, сохранить результат и показать ошибку при сбое."""

    try:
        result = run_circuit(circuit, shots=int(shots), seed=int(seed), noise=noise)
    except (ValueError, MemoryError) as exc:
        st.error(f"Запуск не выполнен: {exc}")
        return
    set_result(result, run_signature(circuit, noise, int(shots), int(seed)))


def _render_controls(circuit, noise) -> bool:
    """Панель параметров запуска. Возвращает True, если нажата кнопка запуска."""

    section(
        "Параметры запуска",
        "shots — число измерений; seed — зерно генератора для воспроизводимости.",
    )
    col_shots, col_seed, col_target = st.columns([1, 1, 2])
    with col_shots:
        st.number_input(
            "Число измерений (shots)",
            min_value=100,
            max_value=20000,
            step=100,
            key="shots",
            help="Точность частот растёт как 1/√shots.",
        )
    with col_seed:
        st.number_input(
            "Random seed",
            min_value=0,
            max_value=2**32 - 1,
            step=1,
            key="seed",
            help="При одинаковых схеме, параметрах и seed результат повторяется.",
        )
    with col_target:
        st.text_input(
            "Целевая битовая строка",
            key="target",
            placeholder="например, 11",
            help="Необязательно. Если задана, приложение покажет вероятность "
            "и долю успешных запусков.",
        )

    if noise.enabled:
        st.info(f"Текущий режим: **{noise.summary()}**.")
    else:
        st.caption(
            "Текущий режим: **идеальная модель** (ошибки отключены). "
            "Настройка каналов — в разделе «Аппаратные ошибки»."
        )

    col_run, col_noise, col_info = st.columns([1, 1, 3])
    with col_run:
        triggered = st.button(
            "▶ Запустить схему", key="run_circuit_button", type="primary"
        )
    with col_noise:
        if st.button("Настроить ошибки", key="goto_noise_button"):
            navigate(NAV_NOISE)
    with col_info:
        st.caption(
            f"Оценка памяти на запуск: "
            f"{memory_estimate(circuit.n_qubits, int(st.session_state['shots']), noise.enabled) / 1024:.0f} КБ"
        )
    return triggered


def _render_circuit_preview(circuit) -> None:
    """Показать схему и её параметры до запуска."""

    with st.expander("Схема запуска и её параметры", expanded=False):
        st.image(
            circuit_diagram(circuit),
            caption="Схема, которая будет выполнена. Кубит 0 — верхняя линия, "
            "«M» — измерение; битовая строка читается слева направо.",
        )
        columns = st.columns(4)
        columns[0].metric("Кубитов", circuit.n_qubits)
        columns[1].metric("Операций", circuit.gate_count)
        columns[2].metric("Глубина", circuit.depth())
        columns[3].metric(
            "Измеряются",
            ", ".join(f"q{q}" for q in circuit.measured) or "—",
        )


def _render_distributions(result) -> None:
    """Теоретические вероятности и фактическая гистограмма."""

    labels = list(result.labels)
    show_labels = len(labels) <= 8

    theory_png = bar_chart(
        labels,
        [BarSeries("Идеально (теория)", result.ideal_probabilities, "#94A3B8")],
        "Теоретические вероятности базисных состояний",
        subtitle=(
            f"Идеальное исполнение · кубиты: {', '.join(f'q{q}' for q in result.measured_qubits)}"
        ),
        x_label="Битовая строка (слева — первый измеряемый кубит)",
        y_label="Вероятность",
        show_value_labels=show_labels,
        width=CHART_WIDTH,
    )
    chart_block(
        theory_png,
        "Рис. 1. Теоретические вероятности идеального исполнения. "
        "По вертикали — вероятность (доля от 1), по горизонтали — битовые строки.",
        "probabilities.png",
        "download_theory_png",
    )

    observed_counts = result.counts
    histogram_png = bar_chart(
        labels,
        [
            BarSeries(
                "Число измерений",
                [observed_counts.get(label, 0) for label in labels],
                "#2563EB",
                value_format="count",
            )
        ],
        "Гистограмма фактических результатов измерения",
        subtitle=f"shots = {result.shots} · seed = {result.seed}",
        x_label="Битовая строка",
        y_label="Число измерений (из shots)",
        show_value_labels=show_labels,
        width=CHART_WIDTH,
    )
    chart_block(
        histogram_png,
        "Рис. 2. Фактические результаты: число выпадений каждой битовой строки "
        "из общего числа измерений. Единица измерения — количество измерений.",
        "histogram.png",
        "download_histogram_png",
    )

    metrics = metrics_for_result(result)
    metric_row(
        [
            (
                "TVD(теория, выборка)",
                f"{metrics.tvd_ideal_vs_observed:.3f}",
                "Полное вариационное расстояние между теоретическими "
                "вероятностями и наблюдаемыми частотами. Даже без шума оно "
                "не равно нулю из-за конечного числа измерений.",
            ),
            (
                "Статистический разброс",
                f"{metrics.tvd_noise_floor:.3f}",
                "TVD между теорией и идеальной выборкой при тех же shots — "
                "ориентир, ниже которого различия неотличимы от случайности.",
            ),
            ("Измерений", str(result.shots), "Число shots в запуске."),
        ]
    )

    target = st.session_state.get("target", "").strip()
    if target and target in labels:
        target_metrics(result, target)
    elif target:
        st.warning(
            f"Целевая строка «{target}» не входит в возможные исходы "
            f"({', '.join(labels)}). Вероятность не рассчитана."
        )

    with st.expander("Пояснения к графикам и таблице"):
        st.markdown(
            f"- Битовые строки записаны слева направо: **слева — кубит с "
            f"минимальным номером** среди измеряемых "
            f"({', '.join(f'q{q}' for q in result.measured_qubits)}).\n"
            "- Теоретические вероятности — это |a|² для базисных состояний "
            "идеального исполнения без ошибок.\n"
            "- Наблюдаемые частоты получены случайным измерением с заданным "
            "числом shots, поэтому они колеблются вокруг теоретических значений.\n"
            "- Единицы: вероятность — безразмерная доля от 0 до 1 "
            "(на графике гистограммы — число измерений).\n"
            "- При увеличении shots наблюдаемые частоты приближаются к "
            "теоретическим, но не совпадают с ними точно."
        )

    st.dataframe(
        run_distribution_frame(result),
        hide_index=True,
        column_config={
            "Битовая строка": st.column_config.TextColumn(width="small"),
        },
    )


def _render_comparison(result) -> None:
    """Сравнение идеального и шумового распределений."""

    if result.noisy_counts is None:
        st.info(
            "Сравнение доступно в режиме «Модель с ошибками». Включите ошибки "
            "в разделе «Аппаратные ошибки» и выполните запуск заново."
        )
        if st.button("Перейти к настройке ошибок", key="compare_goto_noise"):
            navigate(NAV_NOISE)
        return

    labels = list(result.labels)
    comparison_png = bar_chart(
        labels,
        [
            BarSeries("Идеально (теория)", result.ideal_probabilities, "#94A3B8"),
            BarSeries("С ошибками (измерено)", result.probabilities_for("noisy"), "#2563EB"),
        ],
        "Идеальное и зашумлённое распределения",
        subtitle=f"shots = {result.shots} · {result.noise.summary()}",
        x_label="Битовая строка",
        y_label="Вероятность",
        width=CHART_WIDTH,
    )
    chart_block(
        comparison_png,
        "Рис. 3. Серые столбцы — идеальные вероятности, синие — наблюдаемые "
        "частоты при включённых ошибках.",
        "comparison.png",
        "download_comparison_png",
    )

    target = st.session_state.get("target", "").strip()
    if target and target not in labels:
        st.warning(
            f"Целевая строка «{target}» не входит в возможные исходы "
            f"({', '.join(labels)}). Вероятность не рассчитана."
        )
        target = ""

    metrics = metrics_for_result(result, target or None)
    metric_row(
        [
            (
                "TVD(идеал, шум)",
                f"{metrics.tvd_ideal_vs_observed:.3f}",
                "TVD = 0,5 × Σ|P_ideal(x) − P_noisy(x)|. 0 — распределения "
                "совпадают, 1 — не пересекаются.",
            ),
            (
                "Статистический разброс",
                f"{metrics.tvd_noise_floor:.3f}",
                "Уровень TVD, возникающий только из-за конечного числа "
                "измерений (без ошибок).",
            ),
            (
                "Измерений",
                str(result.shots),
                "Каждое распределение построено по этому числу shots.",
            ),
        ]
    )

    target_metrics(result, target)

    st.caption(
        "TVD — симметричная метрика от 0 до 1. Она показывает, какую долю "
        "вероятностной массы нужно «перенести», чтобы одно распределение "
        "превратилось в другое. Значения TVD, близкие к статистическому "
        "разбросу, означают, что эффект ошибок сопоставим со случайным "
        "разбросом выборки."
    )

    st.dataframe(
        run_distribution_frame(result),
        hide_index=True,
        column_config={
            "Битовая строка": st.column_config.TextColumn(width="small"),
        },
    )


def _render_state(result) -> None:
    """Амплитуды и вероятности идеального состояния."""

    state = QuantumState(result.n_qubits, result.ideal_state)
    st.caption(
        "Вектор состояния после всех вентилей, но **до** измерения. "
        "Амплитуды — комплексные числа; вероятность состояния равна |a|²."
    )
    metric_row(
        [
            ("Амплитуд", str(2**result.n_qubits), "Для n кубитов — 2^n амплитуд."),
            ("Норма", f"{state.norm():.6f}", "Для корректного состояния норма равна 1."),
            (
                "Сумма вероятностей",
                f"{state.total_probability():.6f}",
                "Проверка нормировки с учётом численной погрешности.",
            ),
        ]
    )
    frame = pd.DataFrame(described_state(state))
    st.dataframe(
        frame,
        hide_index=True,
        column_config={
            "Индекс": st.column_config.NumberColumn(width="small"),
            "Состояние": st.column_config.TextColumn(width="small"),
            "Вероятность": st.column_config.NumberColumn(format="%.6f"),
        },
    )
    st.caption(
        "Порядок битов: крайний левый символ соответствует кубиту 0. "
        "Например, для двух кубитов 10 — это q0 = 1, q1 = 0."
    )


def _render_downloads(result) -> None:
    """Экспорт данных запуска."""

    st.caption(
        "CSV содержит битовые строки, теоретические вероятности и частоты. "
        "В первой строке файла записаны режим, shots, seed и модель ошибок."
    )
    st.download_button(
        "Скачать распределение (CSV)",
        data=run_csv_bytes(result),
        file_name=f"run_{result.n_qubits}q_{result.shots}shots.csv",
        mime="text/csv",
        key="download_run_csv",
    )


def render() -> None:
    page_header(
        "Запуск и результаты",
        "Идеальное исполнение всегда показывается рядом с шумовым: так видно, "
        "что именно меняют ошибки.",
    )
    show_notice()

    circuit = get_circuit()
    noise = get_noise()
    is_valid = validation_messages(circuit)

    _render_circuit_preview(circuit)
    triggered = _render_controls(circuit, noise)

    if triggered and is_valid:
        _execute(circuit, st.session_state["shots"], st.session_state["seed"], noise)

    result = get_result()
    if result is None and is_valid:
        _execute(circuit, st.session_state["shots"], st.session_state["seed"], noise)
        result = get_result()

    if not is_valid:
        st.warning("Схема содержит ошибки: запуск невозможен. Исправьте их в конструкторе.")
        return

    if result is None:
        st.info("Результат появится после запуска схемы.")
        return

    current_shots = int(st.session_state["shots"])
    current_seed = int(st.session_state["seed"])
    expected_signature = run_signature(circuit, noise, current_shots, current_seed)
    if st.session_state.get("result_signature") != expected_signature:
        st.warning(
            "Параметры изменились после последнего запуска. Показан прежний "
            "результат — нажмите «Запустить схему», чтобы пересчитать."
        )

    st.caption(run_parameters_text(result))

    tab_distributions, tab_comparison, tab_state, tab_data = st.tabs(
        ["Распределения", "Сравнение идеального и шумового", "Состояние", "Данные и экспорт"]
    )
    with tab_distributions:
        _render_distributions(result)
    with tab_comparison:
        _render_comparison(result)
    with tab_state:
        _render_state(result)
    with tab_data:
        st.dataframe(
            run_distribution_frame(result),
            hide_index=True,
        )
        _render_downloads(result)
        if result.noisy_counts is not None:
            st.caption(
                "График сравнения доступен на вкладке «Сравнение идеального "
                "и шумового» — там же кнопка сохранения PNG."
            )


__all__ = ["render"]
