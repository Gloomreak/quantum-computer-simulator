"""Раздел «Эксперименты»: серии запусков, графики и экспорт."""

from __future__ import annotations

import streamlit as st

from ..demo import load_demo_circuits
from ..experiments.export import (
    experiment_csv_bytes,
    experiment_raw_dataframe,
)
from ..experiments.runner import (
    DEFAULT_SHOTS_GRID,
    ExperimentSpec,
    estimate_total_runs,
    experiment_kinds,
    probability_grid,
    run_experiment,
)
from ..quantum.circuit import Circuit
from ..render import COLORS, LineSeries, ReferenceLine, line_chart
from .common import (
    chart_block,
    experiment_table,
    page_header,
    section,
    validation_messages,
)
from .state import get_circuit, get_experiment, set_experiment, show_notice

CURRENT_CIRCUIT_LABEL = "Текущая схема"


def _circuit_options(kind_default_demo: str) -> tuple[list[str], list[Circuit], int]:
    """Варианты схем для эксперимента и индекс рекомендуемой."""

    try:
        demos = load_demo_circuits()
    except (FileNotFoundError, ValueError):
        demos = ()

    names = [CURRENT_CIRCUIT_LABEL]
    circuits = [get_circuit().copy()]
    index = 0
    for demo in demos:
        names.append(demo.name)
        circuits.append(demo.circuit.copy())
        if demo.key == kind_default_demo:
            index = len(names) - 1
    return names, circuits, index



def _build_spec(info, circuit: Circuit, values) -> ExperimentSpec:
    """Собрать спецификацию эксперимента из текущих виджетов."""

    target = str(st.session_state.get("exp_target", "") or "").strip()
    allowed = {
        format(index, f"0{circuit.measured_count}b")
        for index in range(2 ** circuit.measured_count)
    }
    if target and target not in allowed:
        st.warning(
            f"Строка «{target}» не входит в возможные исходы схемы. "
            "Она будет проигнорирована."
        )
        target = ""

    shots_grid = tuple(
        sorted(
            int(value)
            for value in st.session_state.get("exp_shots_grid", DEFAULT_SHOTS_GRID)
        )
    )
    return ExperimentSpec(
        kind=info.key,
        circuit=circuit,
        shots=int(st.session_state["exp_shots"]),
        repeats=int(st.session_state["exp_repeats"]),
        seed=int(st.session_state["exp_seed"]),
        target=target or None,
        values=values,
        p_fixed=float(st.session_state.get("exp_p_fixed", 0.02)),
        max_operations=int(st.session_state.get("exp_depth_max", 20)),
        shots_grid=shots_grid,
    )


def _render_parameters(info, circuit: Circuit):
    """Виджеты параметров серии."""

    st.markdown("**Параметры серии**")
    if info.value_kind == "shots":
        selection = st.multiselect(
            "Число измерений в точках серии (shots)",
            options=list(DEFAULT_SHOTS_GRID),
            default=list(DEFAULT_SHOTS_GRID),
            key="exp_shots_grid",
            help="Каждая точка серии — отдельное число измерений.",
        )
        values = ()
        if selection:
            st.caption(
                "Точек в серии: "
                f"{len(selection)} (от {min(selection)} до {max(selection)} shots)."
            )
        else:
            st.error("Выберите хотя бы одно значение shots.")
    elif info.value_kind == "probability":
        col_min, col_max, col_step = st.columns(3)
        with col_min:
            st.number_input(
                "Минимальная вероятность",
                min_value=0.0,
                max_value=0.2,
                step=0.01,
                value=0.0,
                key="exp_p_min",
            )
        with col_max:
            st.number_input(
                "Максимальная вероятность",
                min_value=0.0,
                max_value=0.2,
                step=0.01,
                value=0.2,
                key="exp_p_max",
            )
        with col_step:
            st.number_input(
                "Шаг сетки",
                min_value=0.005,
                max_value=0.1,
                step=0.005,
                value=0.01,
                format="%.3f",
                key="exp_p_step",
            )
        try:
            values = probability_grid(
                float(st.session_state["exp_p_min"]),
                float(st.session_state["exp_p_max"]),
                float(st.session_state["exp_p_step"]),
            )
        except ValueError as exc:
            st.error(f"Проверьте сетку вероятностей: {exc}")
            values = ()
        else:
            st.caption(f"Точек в серии: {len(values)}.")
    else:
        col_depth, col_prob = st.columns(2)
        base = max(2, circuit.gate_count)
        with col_depth:
            st.number_input(
                "Максимальное число операций",
                min_value=base + 2,
                max_value=40,
                step=2,
                value=max(base + 2, min(20, base + 20)),
                key="exp_depth_max",
                help="К базовой схеме добавляются пары CNOT; шаг серии — 2 операции.",
            )
        with col_prob:
            st.number_input(
                "Вероятность ошибки (фиксированная)",
                min_value=0.0,
                max_value=0.2,
                step=0.01,
                value=0.02,
                key="exp_p_fixed",
            )
        values = ()
        st.caption(
            f"Базовая схема: {circuit.gate_count} операций. Серия: "
            f"от {base} до {int(st.session_state['exp_depth_max'])} операций."
        )

    col_shots, col_repeats, col_seed = st.columns(3)
    with col_shots:
        st.number_input(
            "shots на запуск",
            min_value=100,
            max_value=20000,
            step=100,
            value=1000,
            key="exp_shots",
            help="Рекомендация ТЗ: 1000 измерений на запуск.",
        )
    with col_repeats:
        st.number_input(
            "Число повторов",
            min_value=1,
            max_value=50,
            step=1,
            value=10,
            key="exp_repeats",
            help="Для каждой точки выполняется несколько независимых запусков.",
        )
    with col_seed:
        st.number_input(
            "Базовый seed",
            min_value=0,
            max_value=2**32 - 1,
            step=1,
            value=2024,
            key="exp_seed",
            help="Повторный запуск с тем же seed воспроизводит результат.",
        )

    st.text_input(
        "Целевая битовая строка (необязательно)",
        value="",
        key="exp_target",
        placeholder="например, 11",
        help="Если задана, в таблицу добавится средняя вероятность целевого "
        "результата. Не влияет на TVD.",
    )
    return values


def _render_result(result) -> None:
    """График, таблица и экспорт для выполненной серии."""

    st.caption(
        f"{result.circuit_name} · {result.params_note} · всего запусков: "
        f"{result.total_runs} · время: {result.duration_s:.2f} с · "
        f"создано: {result.created_at}"
    )

    colors = COLORS["series"]
    chart_series = []
    for index, series in enumerate(result.series):
        chart_series.append(
            LineSeries(
                name=series.label,
                x=[point.value for point in series.points],
                y=[point.mean for point in series.points],
                color=colors[index % len(colors)],
                low=[point.ci_low for point in series.points],
                high=[point.ci_high for point in series.points],
            )
        )
    floor = (
        sum(point.floor_mean for point in result.series[0].points)
        / max(1, len(result.series[0].points))
        if result.series
        else 0.0
    )
    reference = ReferenceLine(floor, "шумовой уровень выборки")
    if result.kind == "shots" and result.series:
        first = result.series[0]
        chart_series.append(
            LineSeries(
                name="Шумовой уровень (p = 0)",
                x=[point.value for point in first.points],
                y=[point.floor_mean for point in first.points],
                color=COLORS["accent"],
                markers=True,
            )
        )
        reference = None
    png = line_chart(
        chart_series,
        result.title,
        subtitle=f"{result.circuit_name} · {result.params_note}",
        x_label=result.x_label,
        y_label=result.y_label,
        reference=reference,
    )
    chart_block(
        png,
        "Точки — среднее TVD по повторам, вертикальные отрезки — 95 % "
        "доверительный интервал. Пунктир — уровень, создаваемый конечным "
        "числом измерений (TVD идеальной выборки при тех же shots).",
        f"experiment_{result.kind}.png",
        f"download_experiment_{result.kind}_png",
    )

    st.dataframe(
        experiment_table(result),
        hide_index=True,
        column_config={
            "Параметр": st.column_config.NumberColumn(format="%.3g"),
            "Средний TVD": st.column_config.NumberColumn(format="%.4f"),
            "Стандартное отклонение": st.column_config.NumberColumn(format="%.4f"),
            "95% ДИ (низ)": st.column_config.NumberColumn(format="%.4f"),
            "95% ДИ (верх)": st.column_config.NumberColumn(format="%.4f"),
            "Шумовой уровень": st.column_config.NumberColumn(format="%.4f"),
        },
    )

    col_raw, col_agg, col_png = st.columns(3)
    with col_raw:
        st.download_button(
            "Скачать CSV (все запуски)",
            data=experiment_csv_bytes(result),
            file_name=f"experiment_{result.kind}_raw.csv",
            mime="text/csv",
            key=f"download_{result.kind}_raw_csv",
        )
    with col_agg:
        st.download_button(
            "Скачать CSV (средние)",
            data=experiment_csv_bytes(result, aggregated=True),
            file_name=f"experiment_{result.kind}_mean.csv",
            mime="text/csv",
            key=f"download_{result.kind}_mean_csv",
        )
    with col_png:
        st.download_button(
            "Скачать график (PNG)",
            data=png,
            file_name=f"experiment_{result.kind}.png",
            mime="image/png",
            key=f"download_{result.kind}_png",
        )

    with st.expander("Все отдельные запуски (сырые данные)"):
        st.dataframe(experiment_raw_dataframe(result), hide_index=True)
        st.caption(
            "Столбцы «Повтор» и «seed» позволяют воспроизвести любую точку: "
            "запуск с тем же seed и параметрами даёт те же значения."
        )

    st.info(
        "**Как читать результат.** Программа не делает вывод за вас и не "
        "объявляет гипотезу подтверждённой. Сравните наклон кривых, разброс "
        "между повторами и положение относительно шумового уровня: если "
        "кривая лежит заметно выше пунктира и растёт с параметром, отклонение "
        "от идеального распределения связано с ошибками, а не со случайностью "
        "выборки."
    )
    st.caption(result.notes)


def render() -> None:
    page_header(
        "Эксперименты",
        "Серия запусков при разных вероятностях ошибки или глубине схемы: "
        "таблица, график с доверительными интервалами и экспорт.",
    )
    show_notice()

    kinds = experiment_kinds()
    labels = [info.title for info in kinds]
    kind_label = st.selectbox(
        "Вид эксперимента",
        options=labels,
        key="exp_kind",
    )
    info = kinds[labels.index(kind_label)]
    st.caption(info.description)

    section("Схема эксперимента")
    names, circuits, default_index = _circuit_options(info.default_demo)
    circuit_name = st.selectbox(
        "Схема",
        options=names,
        index=default_index,
        help="Можно выбрать готовую схему или текущую схему из конструктора.",
    )
    circuit = circuits[names.index(circuit_name)]
    st.caption(
        f"{circuit.n_qubits} кубит(ов) · {circuit.gate_count} операций · "
        f"глубина {circuit.depth()} · измеряются: "
        f"{', '.join(f'q{q}' for q in circuit.measured) or '—'}"
    )
    if not validation_messages(circuit):
        st.warning("Схема содержит ошибки: серия экспериментов невозможна.")
        return

    values = _render_parameters(info, circuit)
    spec = _build_spec(info, circuit, values)

    try:
        spec.validate()
    except ValueError as exc:
        st.error(f"Проверьте параметры серии: {exc}")
        return

    total_runs = estimate_total_runs(spec)
    st.caption(
        f"Оценка объёма: {total_runs} запусков симулятора. "
        "При необходимости уменьшите число точек, повторов или shots."
    )

    if st.button("▶ Выполнить серию", key="run_experiment_button", type="primary"):
        progress = st.progress(0.0, text="Подготовка серии…")

        def update(done: int, total: int, message: str) -> None:
            progress.progress(
                min(1.0, done / max(1, total)),
                text=f"{message} · выполнено {done} из {total}",
            )

        try:
            result = run_experiment(spec, progress=update)
        except (ValueError, MemoryError) as exc:
            st.error(f"Серия не выполнена: {exc}")
        else:
            set_experiment(result)
        finally:
            progress.empty()

    result = get_experiment()
    if result is None:
        st.info(
            "Результатов пока нет. Настройте параметры и нажмите "
            "«Выполнить серию»."
        )
        return

    section("Результаты серии")
    shots_changed = info.value_kind != "shots" and result.shots != spec.shots
    if (
        result.kind != info.key
        or shots_changed
        or result.repeats != spec.repeats
        or result.seed != spec.seed
        or result.circuit_name != spec.circuit.name
    ):
        st.warning(
            "Показаны результаты предыдущей серии с другими параметрами. "
            "Нажмите «Выполнить серию», чтобы пересчитать."
        )
    _render_result(result)


__all__ = ["render"]
