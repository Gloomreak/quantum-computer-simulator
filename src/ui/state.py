"""Состояние приложения и навигация между разделами.

Streamlit перезапускает скрипт при каждом взаимодействии, поэтому схема,
настройки и результаты хранятся в ``st.session_state``. Действия, которые
меняют состояние виджетов (например, загрузка демонстрационной схемы),
откладываются и применяются в начале следующего запуска — иначе
Streamlit запрещает изменять значение уже созданного виджета.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from ..demo import default_demo
from ..quantum.circuit import Circuit, circuit_from_operations
from ..quantum.noise import NoiseConfig
from ..quantum.simulator import SimulationResult
from ..experiments.runner import ExperimentResult

NAV_ARCHITECTURE = "Архитектура"
NAV_EDITOR = "Конструктор схем"
NAV_RESULTS = "Запуск и результаты"
NAV_NOISE = "Аппаратные ошибки"
NAV_EXPERIMENTS = "Эксперименты"
NAV_HELP = "Справка"

NAV_ITEMS = (
    NAV_ARCHITECTURE,
    NAV_EDITOR,
    NAV_RESULTS,
    NAV_NOISE,
    NAV_EXPERIMENTS,
    NAV_HELP,
)

DEFAULT_SHOTS = 1024
DEFAULT_SEED = 2024
DEFAULT_TARGET = "11"


def _fallback_circuit() -> Circuit:
    """Схема Белла на случай, если файл примеров недоступен."""

    circuit = circuit_from_operations(
        2, [("h", 0), ("cnot", 0, 1)], name="Состояние Белла"
    )
    return circuit


def _default_circuit() -> Circuit:
    try:
        return default_demo().circuit.copy()
    except (FileNotFoundError, ValueError, KeyError):
        return _fallback_circuit()


def init_state() -> None:
    """Заполнить состояние значениями по умолчанию."""

    defaults: Dict[str, Any] = {
        "nav": NAV_ARCHITECTURE,
        "circuit": _default_circuit(),
        "noise": NoiseConfig(
            enabled=False,
            bit_flip_enabled=True,
            phase_flip_enabled=True,
            readout_enabled=True,
            p_bit_flip=0.02,
            p_phase_flip=0.02,
            p_readout=0.02,
        ),
        "shots": DEFAULT_SHOTS,
        "seed": DEFAULT_SEED,
        "target": DEFAULT_TARGET,
        "result": None,
        "result_signature": None,
        "experiment_result": None,
        "notice": None,
        "arch_block": "all",
        "noise_compare_result": None,
        "uploader_version": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    circuit = st.session_state["circuit"]
    if "n_qubits" not in st.session_state:
        st.session_state["n_qubits"] = circuit.n_qubits
    if "measure_all" not in st.session_state:
        st.session_state["measure_all"] = circuit.measured == list(range(circuit.n_qubits))


def navigate(page: str) -> None:
    """Перейти в раздел.

    Значение радионавигации нельзя менять после того, как виджет уже
    создан, поэтому переход откладывается до начала следующего запуска
    скрипта — там радионавигация создаётся заново.
    """

    if page not in NAV_ITEMS:
        raise ValueError(f"Неизвестный раздел: {page}")
    st.session_state["_pending_action"] = {"type": "navigate", "page": page}
    st.rerun()


def request(action: Dict[str, Any]) -> None:
    """Отложить действие, меняющее состояние виджетов."""

    st.session_state["_pending_action"] = action
    st.rerun()


def set_notice(level: str, message: str) -> None:
    """Показать сообщение после следующего перезапуска."""

    st.session_state["notice"] = {"level": level, "message": message}


def apply_pending_action() -> None:
    """Применить отложенное действие (до создания виджетов)."""

    action: Optional[Dict[str, Any]] = st.session_state.get("_pending_action")
    if not action:
        return
    del st.session_state["_pending_action"]

    kind = action.get("type")
    if kind == "navigate":
        st.session_state["nav"] = action["page"]
    elif kind == "load_circuit":
        circuit: Circuit = action["circuit"]
        st.session_state["circuit"] = circuit.copy()
        st.session_state["n_qubits"] = circuit.n_qubits
        st.session_state["measure_all"] = circuit.measured == list(
            range(circuit.n_qubits)
        )
        st.session_state["target"] = action.get("target") or ""
        st.session_state["result"] = None
        st.session_state["result_signature"] = None
        st.session_state["noise_compare_result"] = None
        # Новый ключ загрузчика сбрасывает ранее выбранный файл, иначе
        # Streamlit повторно обработал бы его на следующем перезапуске.
        st.session_state["uploader_version"] = (
            int(st.session_state.get("uploader_version", 0)) + 1
        )
        message = action.get("message")
        if message:
            set_notice("info", message)
        if action.get("navigate"):
            st.session_state["nav"] = action["navigate"]
    elif kind == "set_target":
        st.session_state["target"] = action.get("target", "")
    else:  # pragma: no cover - защита от опечаток
        raise ValueError(f"Неизвестное отложенное действие: {kind}")


def show_notice() -> None:
    """Показать и очистить сообщение из состояния."""

    notice = st.session_state.get("notice")
    if not notice:
        return
    del st.session_state["notice"]
    level = notice.get("level", "info")
    message = notice.get("message", "")
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    elif level == "error":
        st.error(message)
    else:
        st.info(message)


def get_circuit() -> Circuit:
    return st.session_state["circuit"]


def set_circuit(circuit: Circuit) -> None:
    st.session_state["circuit"] = circuit


def get_noise() -> NoiseConfig:
    return st.session_state["noise"]


def set_noise(config: NoiseConfig) -> None:
    st.session_state["noise"] = config


def get_result() -> Optional[SimulationResult]:
    return st.session_state.get("result")


def set_result(result: Optional[SimulationResult], signature: Optional[str] = None) -> None:
    st.session_state["result"] = result
    st.session_state["result_signature"] = signature


def get_experiment() -> Optional[ExperimentResult]:
    return st.session_state.get("experiment_result")


def set_experiment(result: Optional[ExperimentResult]) -> None:
    st.session_state["experiment_result"] = result


def run_signature(
    circuit: Circuit, noise: NoiseConfig, shots: int, seed: int
) -> str:
    """Отпечаток параметров запуска для проверки актуальности результата."""

    operations = ";".join(
        f"{op.gate}:{op.control}:{op.target}" for op in circuit.operations
    )
    return (
        f"{circuit.n_qubits}|{operations}|{circuit.measured}|"
        f"{shots}|{seed}|{noise.enabled}|{noise.bit_flip_enabled}|"
        f"{noise.phase_flip_enabled}|{noise.readout_enabled}|"
        f"{noise.p_bit_flip:.4f}|{noise.p_phase_flip:.4f}|{noise.p_readout:.4f}"
    )


def measured_labels(circuit: Circuit) -> list[str]:
    """Все возможные битовые строки для текущей схемы."""

    width = circuit.measured_count
    return [format(index, f"0{width}b") for index in range(2**width)]


def ensure_target_valid(circuit: Circuit) -> str:
    """Привести целевую строку к допустимому виду (пустая, если нельзя)."""

    target = str(st.session_state.get("target", "") or "").strip()
    if target and target not in measured_labels(circuit):
        return ""
    return target
