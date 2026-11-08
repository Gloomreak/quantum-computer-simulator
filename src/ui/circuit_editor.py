"""Раздел «Конструктор схем»: сборка, проверка, сохранение схемы."""

from __future__ import annotations

import streamlit as st

from ..demo import load_demo_circuits
from ..quantum.circuit import Circuit
from ..quantum.gates import GATES
from ..quantum.statevector import MAX_QUBITS, state_memory_bytes
from ..render import circuit_diagram
from .common import page_header, section, validation_messages
from .state import (
    NAV_RESULTS,
    get_circuit,
    navigate,
    request,
    set_notice,
    show_notice,
)

MAX_INTERACTIVE_QUBITS = 5


def _resize_circuit(circuit: Circuit, n_qubits: int) -> None:
    """Привести схему к новому числу кубитов, отбросив невозможные операции."""

    if n_qubits == circuit.n_qubits:
        return
    dropped = [
        operation
        for operation in circuit.operations
        if max(operation.involved_qubits()) >= n_qubits
    ]
    circuit.n_qubits = n_qubits
    circuit.operations = [
        operation
        for operation in circuit.operations
        if max(operation.involved_qubits()) < n_qubits
    ]
    measured = [qubit for qubit in circuit.measured if qubit < n_qubits]
    circuit.measured_qubits = measured or list(range(n_qubits))
    if dropped:
        st.warning(
            f"При уменьшении числа кубитов удалено операций: {len(dropped)}. "
            "Проверьте схему перед запуском."
        )
    st.session_state["result"] = None
    st.session_state["result_signature"] = None


def _render_demo_loader() -> None:
    """Выбор готовой демонстрационной схемы."""

    try:
        demos = load_demo_circuits()
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Не удалось загрузить демонстрационные схемы: {exc}")
        return

    names = [demo.name for demo in demos]
    col_select, col_button = st.columns([4, 1])
    with col_select:
        choice = st.selectbox(
            "Готовая демонстрационная схема",
            options=names,
            key="demo_choice",
            help="Схемы из файла examples/demo_circuits.json",
        )
    demo = demos[names.index(choice)]
    with col_button:
        st.write("")
        st.write("")
        if st.button("Загрузить", key="load_demo_button"):
            request(
                {
                    "type": "load_circuit",
                    "circuit": demo.circuit,
                    "target": demo.default_target,
                    "message": f"Загружена схема «{demo.name}».",
                }
            )
    st.caption(f"**Что демонстрирует:** {demo.description}")
    st.caption(f"**Ожидаемый результат:** {demo.purpose}")


def _render_gate_form(circuit: Circuit) -> None:
    """Форма добавления одной операции."""

    st.markdown("**Добавить операцию**")
    gate_key = st.selectbox(
        "Вентиль",
        options=list(GATES.keys()),
        format_func=lambda key: GATES[key].name,
        key="add_gate_key",
    )
    st.caption(GATES[gate_key].description)

    col_target, col_control = st.columns(2)
    with col_target:
        target = st.selectbox(
            "Целевой кубит",
            options=list(range(circuit.n_qubits)),
            format_func=lambda qubit: f"q{qubit}",
        )
    if gate_key == "cnot":
        with col_control:
            control = st.selectbox(
                "Управляющий кубит",
                options=list(range(circuit.n_qubits)),
                format_func=lambda qubit: f"q{qubit}",
            )
    else:
        control = None
        with col_control:
            st.caption("У однокубитного вентиля управляющего кубита нет.")

    if st.button("Добавить операцию", key="add_operation_button", type="primary"):
        if gate_key == "cnot" and control == target:
            st.error(
                "Для CNOT управляющий и целевой кубиты должны различаться. "
                "Выберите другой кубит."
            )
        else:
            circuit.add_gate(gate_key, target=target, control=control)
            st.rerun()


def _render_operations(circuit: Circuit) -> None:
    """Список операций с изменением порядка и удалением."""

    st.markdown(f"**Операции схемы** — {circuit.gate_count}")
    if not circuit.operations:
        st.caption("Операций пока нет. Добавьте вентиль или загрузите готовую схему.")
        return

    header = st.columns([0.5, 4.4, 0.8, 0.8, 1.2])
    header[0].caption("№")
    header[1].caption("Операция")
    header[2].caption("Порядок")

    for index, operation in enumerate(circuit.operations):
        columns = st.columns([0.5, 4.4, 0.8, 0.8, 1.2])
        columns[0].write(f"{index + 1}")
        columns[1].write(operation.describe())
        if columns[2].button(
            "↑",
            key=f"move_up_{index}",
            disabled=index == 0,
            help="Переместить операцию раньше",
        ):
            circuit.move(index, -1)
            st.rerun()
        if columns[3].button(
            "↓",
            key=f"move_down_{index}",
            disabled=index == len(circuit.operations) - 1,
            help="Переместить операцию позже",
        ):
            circuit.move(index, 1)
            st.rerun()
        if columns[4].button("Удалить", key=f"delete_{index}"):
            circuit.remove(index)
            st.rerun()

    st.caption(
        "Порядок операций влияет на результат, если они действуют на одни и те "
        "же кубиты: например, H · Z ≠ Z · H. Проверка корректности выполняется "
        "после каждого изменения."
    )


def _render_measurement_settings(circuit: Circuit) -> None:
    """Настройка того, какие кубиты измеряются."""

    n_qubits = circuit.n_qubits
    measure_all = st.checkbox(
        "Измерять все кубиты в конце схемы",
        key="measure_all",
        help="По умолчанию измеряются все кубиты. Частичное измерение "
        "допускается как дополнительная функция.",
    )
    if measure_all:
        circuit.measured_qubits = list(range(n_qubits))
        st.caption(
            f"Будут измерены кубиты: {', '.join(f'q{q}' for q in range(n_qubits))}."
        )
        return

    selection = st.multiselect(
        "Какие кубиты измерять",
        options=list(range(n_qubits)),
        default=circuit.measured,
        format_func=lambda qubit: f"q{qubit}",
    )
    circuit.measured_qubits = sorted(int(qubit) for qubit in selection)
    if not selection:
        st.error(
            "Не выбран ни один кубит: результат измерения будет пустым. "
            "Выберите хотя бы один кубит или включите измерение всех кубитов."
        )
    else:
        st.caption(
            "Биты результата будут записаны в порядке возрастания номеров "
            "измеряемых кубитов (слева — меньший номер)."
        )


def render() -> None:
    page_header(
        "Конструктор квантовой схемы",
        "Соберите схему из вентилей X, H, Z и CNOT, проверьте её и запустите. "
        "Кубит 0 — верхняя линия схемы.",
    )
    show_notice()

    circuit = get_circuit()

    section("1. Параметры схемы", "Интерактивный режим — от 1 до 5 кубитов.")
    col_qubits, col_measure = st.columns([1, 2])
    with col_qubits:
        n_qubits = st.selectbox(
            "Число кубитов",
            options=list(range(1, MAX_INTERACTIVE_QUBITS + 1)),
            key="n_qubits",
        )
    _resize_circuit(circuit, int(n_qubits))
    with col_measure:
        _render_measurement_settings(circuit)

    st.caption(
        f"Вектор состояния: {2 ** circuit.n_qubits} комплексных амплитуд "
        f"(~{state_memory_bytes(circuit.n_qubits) / 1024:.1f} КБ). "
        f"Предел модели — {MAX_QUBITS} кубитов."
    )

    section("2. Демонстрационные схемы", "Готовые сценарии из ТЗ и дополнительные примеры.")
    _render_demo_loader()

    section("3. Редактор операций")
    _render_gate_form(circuit)
    st.divider()
    _render_operations(circuit)

    col_clear, col_export = st.columns([1, 3])
    with col_clear:
        if st.button("Очистить схему", key="clear_circuit_button"):
            circuit.clear()
            st.session_state["result"] = None
            st.session_state["result_signature"] = None
            set_notice("info", "Схема очищена: измеряется начальное состояние |00…0⟩.")
            st.rerun()
    with col_export:
        st.caption(
            "Схему можно сохранить в JSON и загрузить позже: файл содержит "
            "вентили и измеряемые кубиты."
        )

    png = circuit_diagram(circuit)
    section("4. Схема и проверка", "Схема перерисовывается при каждом изменении.")
    metric_columns = st.columns(4)
    metric_columns[0].metric("Кубитов", str(circuit.n_qubits))
    metric_columns[1].metric("Операций", str(circuit.gate_count))
    metric_columns[2].metric("Глубина", str(circuit.depth()))
    metric_columns[3].metric(
        "Измеряются",
        ", ".join(f"q{q}" for q in circuit.measured) if circuit.measured else "—",
    )

    is_valid = validation_messages(circuit)
    st.image(
        png,
        caption="Рис. 1. Схема. Последний столбец «M» — измерение; "
        "битовая строка читается слева направо (слева — кубит 0).",
    )

    col_json, col_save = st.columns(2)
    with col_json:
        st.download_button(
            "Скачать схему (JSON)",
            data=circuit.to_json().encode("utf-8"),
            file_name=f"circuit_{circuit.n_qubits}q.json",
            mime="application/json",
            key="download_circuit_json",
        )
        st.download_button(
            "Скачать схему (PNG)",
            data=png,
            file_name=f"circuit_{circuit.n_qubits}q.png",
            mime="image/png",
            key="download_circuit_png",
        )
    with col_save:
        uploaded = st.file_uploader(
            "Загрузить схему из JSON",
            type=["json"],
            key=f"circuit_uploader_{st.session_state.get('uploader_version', 0)}",
        )
        if uploaded is not None:
            try:
                loaded = Circuit.from_json(uploaded.getvalue().decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                st.error(f"Не удалось загрузить схему: {exc}")
            else:
                request(
                    {
                        "type": "load_circuit",
                        "circuit": loaded,
                        "target": "",
                        "message": f"Загружена схема «{loaded.name}».",
                    }
                )

    st.divider()
    col_run, col_hint = st.columns([1, 3])
    with col_run:
        if st.button(
            "Перейти к запуску →",
            key="goto_results_button",
            type="primary",
            disabled=not is_valid,
        ):
            navigate(NAV_RESULTS)
    with col_hint:
        st.caption(
            "Запуск выполняется на странице «Запуск и результаты»: там задаются "
            "shots, seed и целевая битовая строка."
        )


__all__ = ["render"]
