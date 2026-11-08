"""Независимая (медленная) эталонная реализация для проверки симулятора.

Модуль намеренно не использует numpy-тензорные преобразования из
``src.quantum.statevector``: вентили применяются прямым перебором
базисных индексов, а шумовые траектории моделируются по одному
измерению за раз. Это позволяет сравнивать быструю реализацию с
независимым эталоном.

Используется только в тестах.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from src.quantum.circuit import Circuit
from src.quantum.gates import H_MATRIX, X_MATRIX, Z_MATRIX
from src.quantum.noise import NoiseConfig

SINGLE_QUBIT_MATRICES = {"x": X_MATRIX, "h": H_MATRIX, "z": Z_MATRIX}


def ref_zero_state(n_qubits: int) -> np.ndarray:
    state = np.zeros(2**n_qubits, dtype=np.complex128)
    state[0] = 1.0
    return state


def ref_apply(
    state: np.ndarray,
    n_qubits: int,
    gate: str,
    target: int,
    control: int | None = None,
) -> np.ndarray:
    """Применить вентиль прямым перебором индексов."""

    dim = 2**n_qubits
    result = np.zeros(dim, dtype=np.complex128)

    if gate in SINGLE_QUBIT_MATRICES:
        matrix = SINGLE_QUBIT_MATRICES[gate]
        bit = 1 << (n_qubits - 1 - target)
        for index in range(dim):
            if index & bit:
                continue
            partner = index | bit
            a0 = state[index]
            a1 = state[partner]
            result[index] = matrix[0, 0] * a0 + matrix[0, 1] * a1
            result[partner] = matrix[1, 0] * a0 + matrix[1, 1] * a1
        return result

    if gate == "cnot":
        if control is None:
            raise ValueError("CNOT требует управляющий кубит.")
        control_bit = 1 << (n_qubits - 1 - control)
        target_bit = 1 << (n_qubits - 1 - target)
        result[:] = state
        for index in range(dim):
            if (index & control_bit) and not (index & target_bit):
                partner = index | target_bit
                result[index] = state[partner]
                result[partner] = state[index]
        return result

    raise ValueError(f"Неизвестный вентиль: {gate}")


def ref_state_vector(circuit: Circuit) -> np.ndarray:
    """Идеальный вектор состояния, посчитанный эталонным способом."""

    state = ref_zero_state(circuit.n_qubits)
    for operation in circuit.operations:
        state = ref_apply(
            state, circuit.n_qubits, operation.gate, operation.target, operation.control
        )
    return state


def ref_probabilities(circuit: Circuit) -> np.ndarray:
    state = ref_state_vector(circuit)
    return np.abs(state) ** 2


def ref_marginal(probabilities: np.ndarray, n_qubits: int, measured: List[int]) -> np.ndarray:
    """Маргинальные вероятности измеряемых кубитов."""

    width = len(measured)
    result = np.zeros(2**width, dtype=float)
    for index, probability in enumerate(probabilities):
        label = 0
        for position, qubit in enumerate(measured):
            bit = (index >> (n_qubits - 1 - qubit)) & 1
            label = (label << 1) | bit
        result[label] += probability
    return result


def ref_counts(
    circuit: Circuit,
    noise: NoiseConfig,
    shots: int,
    seed: int,
) -> Dict[str, int]:
    """Медленная шумовая траектория по одному измерению за раз."""

    rng_state = np.random.default_rng([seed, 11])
    rng_noise = np.random.default_rng([seed, 22])
    rng_readout = np.random.default_rng([seed, 33])
    n = circuit.n_qubits
    measured = circuit.measured
    width = len(measured)
    counts = {
        format(index, f"0{width}b"): 0 for index in range(2**width)
    }

    for _ in range(shots):
        state = ref_zero_state(n)
        for operation in circuit.operations:
            state = ref_apply(
                state,
                n,
                operation.gate,
                operation.target,
                operation.control,
            )
            if noise.gate_noise_active:
                for qubit in operation.involved_qubits():
                    if noise.bit_flip_active and rng_noise.random() < noise.p_bit_flip:
                        state = ref_apply(state, n, "x", qubit)
                    if noise.phase_flip_active and rng_noise.random() < noise.p_phase_flip:
                        state = ref_apply(state, n, "z", qubit)

        probabilities = np.abs(state) ** 2
        marginal = ref_marginal(probabilities, n, measured)
        cumulative = np.cumsum(marginal)
        outcome = int(np.searchsorted(cumulative, rng_state.random(), side="left"))
        bits = [(outcome >> (width - 1 - position)) & 1 for position in range(width)]
        if noise.readout_active:
            for position in range(width):
                if rng_readout.random() < noise.p_readout:
                    bits[position] ^= 1
        label = "".join(str(bit) for bit in bits)
        counts[label] = counts.get(label, 0) + 1
    return counts


def counts_to_probabilities(counts: Dict[str, int], labels: List[str]) -> np.ndarray:
    total = sum(counts.values())
    return np.asarray([counts.get(label, 0) / total for label in labels], dtype=float)


def total_variation(first: np.ndarray, second: np.ndarray) -> float:
    return float(0.5 * np.abs(np.asarray(first) - np.asarray(second)).sum())
