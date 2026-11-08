"""Исполнение квантовой схемы: идеальный режим и режим с ошибками.

Идеальный режим
    Состояние эволюционирует под действием матриц вентилей; после этого
    вычисляются точные вероятности и выполняется стохастическое
    измерение с заданным числом ``shots``.

Режим с ошибками
    Для каждого измерения (shot) строится отдельная «траектория»:
    состояние проходит те же вентили, но после каждой операции к
    затронутым кубитам с заданными вероятностями применяются случайные
    паулиевские ошибки (X или Z). Затем траектория измеряется, и к
    результату применяется ошибка считывания. Частоты, полученные по
    всем траекториям, образуют наблюдаемое распределение.

Все траектории обрабатываются одним пакетом (массив формы
``(shots, 2**n)``), что сохраняет смысл модели, но избавляет от
медленного цикла по shots на Python.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List

import numpy as np

from .circuit import Circuit
from .measurement import (
    apply_readout_error,
    counts_from_outcomes,
    make_generators,
    measured_distribution,
    sample_outcomes,
    validate_seed,
    validate_shots,
)
from .noise import NoiseConfig
from .statevector import (
    QuantumState,
    apply_gate_to_array,
    bitstrings_from_indices,
    marginal_probabilities,
    probabilities,
    state_memory_bytes,
)

MAX_SIMULATION_BYTES: int = 1_500_000_000
"""Ограничение памяти на один запуск (вектор состояния + вероятности)."""

MODE_IDEAL: str = "ideal"
MODE_NOISY: str = "noisy"


@dataclass
class SimulationResult:
    """Результат одного запуска схемы."""

    circuit: Circuit
    shots: int
    seed: int
    noise: NoiseConfig
    ideal_state: np.ndarray
    measured_qubits: List[int]
    labels: List[str]
    ideal_probabilities: np.ndarray
    ideal_counts: Dict[str, int]
    noisy_counts: Dict[str, int] | None = None
    mode: str = MODE_IDEAL
    duration_s: float = 0.0

    @property
    def n_qubits(self) -> int:
        return self.circuit.n_qubits

    @property
    def n_measured(self) -> int:
        return len(self.measured_qubits)

    @property
    def is_noisy(self) -> bool:
        return self.mode == MODE_NOISY

    @property
    def counts(self) -> Dict[str, int]:
        """Частоты, соответствующие выбранному режиму."""

        if self.is_noisy and self.noisy_counts is not None:
            return self.noisy_counts
        return self.ideal_counts

    @property
    def observed_probabilities(self) -> np.ndarray:
        """Эмпирические вероятности выбранного режима."""

        total = max(1, sum(self.counts.values()))
        return np.asarray(
            [self.counts.get(label, 0) / total for label in self.labels], dtype=float
        )

    @property
    def ideal_observed_probabilities(self) -> np.ndarray:
        """Эмпирические вероятности идеальной выборки (без шума)."""

        total = max(1, sum(self.ideal_counts.values()))
        return np.asarray(
            [self.ideal_counts.get(label, 0) / total for label in self.labels],
            dtype=float,
        )

    def counts_for(self, mode: str) -> Dict[str, int]:
        """Частоты для указанного режима (``"ideal"``/``"noisy"``)."""

        if mode == MODE_NOISY:
            if self.noisy_counts is None:
                raise ValueError("Запуск выполнен без модели ошибок.")
            return self.noisy_counts
        return self.ideal_counts

    def probabilities_for(self, mode: str) -> np.ndarray:
        """Эмпирические вероятности для указанного режима."""

        counts = self.counts_for(mode)
        total = max(1, sum(counts.values()))
        return np.asarray(
            [counts.get(label, 0) / total for label in self.labels], dtype=float
        )

    def target_probability(self, bitstring: str, mode: str = "auto") -> float:
        """Вероятность (частота) выбранной битовой строки."""

        if mode == "auto":
            probabilities_source = self.observed_probabilities
        else:
            probabilities_source = self.probabilities_for(mode)
        labels = list(self.labels)
        if bitstring not in labels:
            raise ValueError(
                f"Строка {bitstring!r} не входит в набор возможных исходов."
            )
        return float(probabilities_source[labels.index(bitstring)])

    def ideal_target_probability(self, bitstring: str) -> float:
        """Теоретическая вероятность битовой строки в идеальной модели."""

        labels = list(self.labels)
        if bitstring not in labels:
            raise ValueError(
                f"Строка {bitstring!r} не входит в набор возможных исходов."
            )
        return float(self.ideal_probabilities[labels.index(bitstring)])


def _check_memory(n_qubits: int, shots: int, noisy: bool) -> None:
    """Не дать приложению уйти в неконтролируемое потребление памяти."""

    per_shot = 16 * (2**n_qubits) * (3 if noisy else 1)
    estimate = per_shot * shots + 16 * 2**n_qubits
    if estimate > MAX_SIMULATION_BYTES:
        raise ValueError(
            f"Расчёт требует примерно {estimate / 1e6:.0f} МБ памяти, что превышает "
            f"безопасный предел {MAX_SIMULATION_BYTES / 1e6:.0f} МБ. "
            "Уменьшите число измерений (shots) или число кубитов."
        )


def build_ideal_state(circuit: Circuit) -> QuantumState:
    """Построить идеальное состояние после применения всех операций."""

    circuit.validate_or_raise()
    state = QuantumState.zero(circuit.n_qubits)
    for operation in circuit.operations:
        state.apply(operation.gate, operation.target, operation.control)
    return state


@lru_cache(maxsize=64)
def _x_permutation(n_qubits: int, qubit: int) -> np.ndarray:
    """Перестановка индексов при X на кубите ``qubit``."""

    mask = 1 << (n_qubits - 1 - qubit)
    indices = np.arange(2**n_qubits, dtype=np.int64)
    return indices ^ mask


@lru_cache(maxsize=64)
def _z_signs(n_qubits: int, qubit: int) -> np.ndarray:
    """Знаковый вектор для Z на кубите ``qubit``."""

    mask = 1 << (n_qubits - 1 - qubit)
    indices = np.arange(2**n_qubits, dtype=np.int64)
    return np.where((indices & mask) != 0, -1.0, 1.0)


def _apply_x_subset(
    states: np.ndarray, mask: np.ndarray, qubit: int, n_qubits: int
) -> None:
    """Применить X к выбранным траекториям (изменение на месте)."""

    permutation = _x_permutation(n_qubits, qubit)
    states[mask] = states[mask][:, permutation]


def _apply_z_subset(
    states: np.ndarray, mask: np.ndarray, qubit: int, n_qubits: int
) -> None:
    """Применить Z к выбранным траекториям (изменение на месте)."""

    signs = _z_signs(n_qubits, qubit)
    states[mask] = states[mask] * signs


def _simulate_trajectories(
    circuit: Circuit,
    noise: NoiseConfig,
    shots: int,
    generators: Dict[str, np.random.Generator],
) -> np.ndarray:
    """Смоделировать ``shots`` шумовых траекторий и вернуть исходы.

    Возвращает целочисленные индексы исходов (в порядке измеряемых
    кубитов, слева — первый измеряемый кубит).
    """

    n = circuit.n_qubits
    dim = 2**n
    states = np.zeros((shots, dim), dtype=np.complex128)
    states[:, 0] = 1.0

    noise_generator = generators["noise"]
    for operation in circuit.operations:
        states = apply_gate_to_array(
            states, n, operation.gate, operation.target, operation.control
        )
        if not (noise.bit_flip_active or noise.phase_flip_active):
            continue
        for qubit in operation.involved_qubits():
            if noise.bit_flip_active:
                mask = noise_generator.random(shots) < noise.p_bit_flip
                if mask.any():
                    _apply_x_subset(states, mask, qubit, n)
            if noise.phase_flip_active:
                mask = noise_generator.random(shots) < noise.p_phase_flip
                if mask.any():
                    _apply_z_subset(states, mask, qubit, n)

    measured = circuit.measured
    state_probabilities = probabilities(states)
    marginal = marginal_probabilities(state_probabilities, n, measured)
    outcomes = sample_outcomes(marginal, shots, generators["state"])
    if noise.readout_active:
        outcomes = apply_readout_error(
            outcomes, len(measured), noise.p_readout, generators["readout"]
        )
    return outcomes


def run_circuit(
    circuit: Circuit,
    shots: int = 1024,
    seed: int = 42,
    noise: NoiseConfig | None = None,
) -> SimulationResult:
    """Выполнить схему и вернуть результат измерения.

    Parameters
    ----------
    circuit : Circuit
        Схема; должна пройти проверку :meth:`Circuit.validate`.
    shots : int
        Число измерений.
    seed : int
        Зерно генератора случайных чисел (воспроизводимость).
    noise : NoiseConfig | None
        Настройки ошибок. ``None`` или ``NoiseConfig(enabled=False)``
        соответствует идеальной модели.

    Raises
    ------
    ValueError
        Если схема некорректна или параметры запуска недопустимы.
    """

    circuit.validate_or_raise()
    count = validate_shots(shots)
    safe_seed = validate_seed(seed)
    config = noise if noise is not None else NoiseConfig()
    noisy = config.enabled

    _check_memory(circuit.n_qubits, count, noisy)

    started = time.perf_counter()
    ideal_state = build_ideal_state(circuit)
    measured = circuit.measured
    labels = bitstrings_from_indices(range(2 ** len(measured)), len(measured))
    ideal_probabilities = measured_distribution(
        ideal_state.probabilities, circuit.n_qubits, measured
    )

    generators = make_generators(safe_seed)
    ideal_outcomes = sample_outcomes(
        ideal_probabilities, count, generators["state"]
    )
    ideal_counts = counts_from_outcomes(ideal_outcomes, len(measured))

    noisy_counts: Dict[str, int] | None = None
    if noisy:
        # Для воспроизводимости используем тот же поток измерений, что и в
        # идеальном режиме: при p = 0 результаты должны совпадать.
        noisy_generators = make_generators(safe_seed)
        outcomes = _simulate_trajectories(circuit, config, count, noisy_generators)
        noisy_counts = counts_from_outcomes(outcomes, len(measured))

    duration = time.perf_counter() - started
    return SimulationResult(
        circuit=circuit.copy(),
        shots=count,
        seed=safe_seed,
        noise=config,
        ideal_state=ideal_state.amplitudes,
        measured_qubits=measured,
        labels=labels,
        ideal_probabilities=ideal_probabilities,
        ideal_counts=ideal_counts,
        noisy_counts=noisy_counts,
        mode=MODE_NOISY if noisy else MODE_IDEAL,
        duration_s=duration,
    )


def ideal_state_of(circuit: Circuit) -> QuantumState:
    """Публичный помощник: идеальное состояние схемы без измерения."""

    return build_ideal_state(circuit)


def memory_estimate(n_qubits: int, shots: int = 1, noisy: bool = False) -> int:
    """Оценка объёма памяти под один запуск в байтах."""

    base = state_memory_bytes(n_qubits)
    if noisy:
        return base + shots * 16 * (2**n_qubits) * 2
    return base


def described_state(state: QuantumState, threshold: float = 1e-9) -> List[dict]:
    """Таблица амплитуд состояния для интерфейса.

    Каждая строка: индекс, битовая строка, действительная и мнимая части,
    вероятность.
    """

    rows: List[dict] = []
    for index in range(2**state.n_qubits):
        amplitude = complex(state.amplitudes[index])
        rows.append(
            {
                "Индекс": index,
                "Состояние": state.label(index),
                "Re(a)": round(amplitude.real, 6),
                "Im(a)": round(amplitude.imag, 6),
                "Вероятность": round(abs(amplitude) ** 2, 6),
            }
        )
    del threshold
    return rows


__all__ = [
    "MAX_SIMULATION_BYTES",
    "MODE_IDEAL",
    "MODE_NOISY",
    "SimulationResult",
    "build_ideal_state",
    "described_state",
    "ideal_state_of",
    "memory_estimate",
    "run_circuit",
]
