"""Матрицы квантовых вентилей и их описание.

Вентили задаются матрицами в вычислительном базисе. Для одного кубита
базисные состояния упорядочены как (|0>, |1>), для CNOT — как
(|00>, |01>, |10>, |11>), где первая цифра относится к управляющему,
а вторая — к целевому кубиту.

Модуль не хранит состояние: он только предоставляет матрицы и
человекочитаемые описания, которые используются интерфейсом и
документацией.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

# Допустимая численная погрешность для проверок нормировки и сравнения
# вероятностей. Значение выбрано с запасом относительно ошибок complex128.
TOLERANCE: float = 1e-9


@dataclass(frozen=True)
class GateInfo:
    """Описание вентиля для интерфейса и документации."""

    key: str
    symbol: str
    name: str
    num_qubits: int
    matrix: np.ndarray
    short: str
    description: str


def _matrix(rows: Tuple[Tuple[complex, ...], ...]) -> np.ndarray:
    return np.asarray(rows, dtype=np.complex128)


# Матрица Адамара: создаёт равновесную суперпозицию.
H_MATRIX = _matrix(
    (
        (1 / np.sqrt(2), 1 / np.sqrt(2)),
        (1 / np.sqrt(2), -1 / np.sqrt(2)),
    )
)

# NOT-подобный вентиль: меняет |0> и |1> местами.
X_MATRIX = _matrix(((0, 1), (1, 0)))

# Фазовый вентиль: оставляет |0> без изменений, |1> умножает на -1.
Z_MATRIX = _matrix(((1, 0), (0, -1)))

# Управляемое отрицание (CNOT) в базисе (control, target).
CNOT_MATRIX = _matrix(
    (
        (1, 0, 0, 0),
        (0, 1, 0, 0),
        (0, 0, 0, 1),
        (0, 0, 1, 0),
    )
)

IDENTITY_2 = _matrix(((1, 0), (0, 1)))

GATES: Dict[str, GateInfo] = {
    "x": GateInfo(
        key="x",
        symbol="X",
        name="X — переворот бита (NOT)",
        num_qubits=1,
        matrix=X_MATRIX,
        short="Меняет |0⟩ на |1⟩ и наоборот.",
        description=(
            "Аналог классического NOT. Переводит |0⟩ в |1⟩, а |1⟩ в |0⟩. "
            "Два подряд идущих X возвращают исходное состояние."
        ),
    ),
    "h": GateInfo(
        key="h",
        symbol="H",
        name="H — вентиль Адамара",
        num_qubits=1,
        matrix=H_MATRIX,
        short="Создаёт суперпозицию.",
        description=(
            "Переводит |0⟩ в (|0⟩+|1⟩)/√2, то есть в равновесную суперпозицию, "
            "а |1⟩ — в (|0⟩−|1⟩)/√2. Два подряд идущих H возвращают исходное "
            "состояние. В схеме H обычно ставится первым, чтобы получить "
            "суперпозицию и затем запутать кубиты."
        ),
    ),
    "z": GateInfo(
        key="z",
        symbol="Z",
        name="Z — фазовый вентиль",
        num_qubits=1,
        matrix=Z_MATRIX,
        short="Меняет фазу амплитуды |1⟩.",
        description=(
            "Оставляет |0⟩ без изменений и меняет знак амплитуды |1⟩. "
            "Вероятности в вычислительном базисе не меняются, то есть Z "
            "не виден при прямом измерении; его влияние проявляется, если "
            "после Z применить H или другой вентиль, меняющий базис."
        ),
    ),
    "cnot": GateInfo(
        key="cnot",
        symbol="CNOT",
        name="CNOT — управляемое отрицание",
        num_qubits=2,
        matrix=CNOT_MATRIX,
        short="Переворачивает целевой кубит, если управляющий равен 1.",
        description=(
            "Двухкубитный вентиль: если управляющий кубит находится в |1⟩, "
            "целевой кубит инвертируется; иначе ничего не происходит. "
            "Вместе с H на управляющем кубите CNOT создаёт запутанное "
            "состояние Белла."
        ),
    ),
}

GATE_KEYS: Tuple[str, ...] = tuple(GATES.keys())


def get_gate(key: str) -> GateInfo:
    """Вернуть описание вентиля по ключу.

    Parameters
    ----------
    key : str
        Ключ вентиля: ``"x"``, ``"h"``, ``"z"`` или ``"cnot"``.

    Raises
    ------
    KeyError
        Если вентиль неизвестен.
    """

    try:
        return GATES[key.strip().lower()]
    except KeyError as exc:  # pragma: no cover - защита от опечаток в UI
        raise KeyError(f"Неизвестный вентиль: {key!r}") from exc


def gate_matrix(key: str) -> np.ndarray:
    """Вернуть копию матрицы вентиля."""

    return get_gate(key).matrix.copy()


def is_two_qubit(key: str) -> bool:
    """Является ли вентиль двухкубитным."""

    return get_gate(key).num_qubits == 2
