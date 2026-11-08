"""Вычислительное ядро симулятора.

Публичный интерфейс:

* :class:`QuantumState` — вектор состояния регистра;
* :class:`Circuit` и :class:`Operation` — схема;
* :class:`NoiseConfig` — модели аппаратных ошибок;
* :func:`run_circuit` — исполнение схемы (идеально или с ошибками).
"""

from .circuit import Circuit, Operation, ValidationIssue, circuit_from_operations
from .gates import GATES, GateInfo, get_gate, gate_matrix
from .measurement import (
    counts_from_outcomes,
    measured_distribution,
    sample_outcomes,
)
from .noise import CHANNEL_INFO, NoiseConfig, channel_summary
from .simulator import (
    MODE_IDEAL,
    MODE_NOISY,
    SimulationResult,
    build_ideal_state,
    run_circuit,
)
from .statevector import (
    MAX_QUBITS,
    QuantumState,
    basis_labels,
    state_memory_bytes,
    zero_state,
)

__all__ = [
    "CHANNEL_INFO",
    "Circuit",
    "GATES",
    "GateInfo",
    "MAX_QUBITS",
    "MODE_IDEAL",
    "MODE_NOISY",
    "NoiseConfig",
    "Operation",
    "QuantumState",
    "SimulationResult",
    "ValidationIssue",
    "basis_labels",
    "build_ideal_state",
    "circuit_from_operations",
    "channel_summary",
    "counts_from_outcomes",
    "gate_matrix",
    "get_gate",
    "measured_distribution",
    "run_circuit",
    "sample_outcomes",
    "state_memory_bytes",
    "zero_state",
]
