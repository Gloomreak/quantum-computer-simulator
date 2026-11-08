"""Вектор состояния квантового регистра и операции над ним.

Модель
------
Регистр из ``n`` кубитов описывается вектором комплексных амплитуд
длины ``2**n``. Базисные состояния упорядочены по индексу: индекс ``i``
соответствует битовой строке ``format(i, f"0{n}b")``, в которой **крайний
левый символ относится к кубиту 0**. Например, для двух кубитов:

======  ==========  =================
индекс  битовая     состояние
        строка
======  ==========  =================
0       00          |0⟩_0 |0⟩_1
1       01          |0⟩_0 |1⟩_1
2       10          |1⟩_0 |0⟩_1
3       11          |1⟩_0 |1⟩_1
======  ==========  =================

Такой порядок совпадает с порядком строк в схеме (кубит 0 сверху) и
позволяет без преобразований подписывать результаты измерений.

Все операции реализованы и для одного вектора состояния (форма
``(2**n,)``), и для «пакета» состояний (форма ``(shots, 2**n)``), который
используется при моделировании шумовых траекторий.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

import numpy as np

from .gates import TOLERANCE, get_gate

MAX_QUBITS: int = 10
"""Жёсткий предел числа кубитов в вычислительном ядре.

Интерактивный режим ограничен 1–5 кубитами согласно ТЗ, однако
экспериментальный модуль и тесты могут работать с большим регистром.
При 10 кубитах вектор состояния занимает 2**10 * 16 байт ≈ 16 КБ,
что безопасно; предел защищает от случайного запроса 2**30 амплитуд.
"""


def validate_qubit_index(index: int, n_qubits: int, role: str = "кубит") -> int:
    """Проверить корректность номера кубита и вернуть его как ``int``.

    Parameters
    ----------
    index : int
        Номер кубита (нумерация с нуля).
    n_qubits : int
        Число кубитов в регистре.
    role : str
        Слово для сообщения об ошибке (например, ``"управляющий кубит"``).

    Raises
    ------
    ValueError
        Если индекс не является целым числом или выходит за границы.
    """

    if isinstance(index, bool) or not isinstance(index, (int, np.integer)):
        raise ValueError(f"Номер кубита должен быть целым числом, получено {index!r}.")
    value = int(index)
    if value < 0 or value >= n_qubits:
        raise ValueError(
            f"Номер {role} {value} вне диапазона: в схеме {n_qubits} кубит(ов), "
            f"допустимые номера — от 0 до {n_qubits - 1}."
        )
    return value


def validate_qubit_count(n_qubits: int) -> int:
    """Проверить число кубитов регистра."""

    if isinstance(n_qubits, bool) or not isinstance(n_qubits, (int, np.integer)):
        raise ValueError(f"Число кубитов должно быть целым, получено {n_qubits!r}.")
    value = int(n_qubits)
    if value < 1:
        raise ValueError("Число кубитов должно быть не меньше 1.")
    if value > MAX_QUBITS:
        raise ValueError(
            f"Число кубитов {value} превышает предел модели ({MAX_QUBITS}). "
            "Размер вектора состояния растёт как 2^n, поэтому регистр "
            "ограничен."
        )
    return value


def basis_labels(n_qubits: int) -> List[str]:
    """Битовые строки всех базисных состояний в порядке индексов.

    Первый (левый) символ строки соответствует кубиту 0.
    """

    n = validate_qubit_count(n_qubits)
    return [format(i, f"0{n}b") for i in range(2**n)]


def zero_state(n_qubits: int) -> np.ndarray:
    """Вектор состояния |00…0⟩."""

    n = validate_qubit_count(n_qubits)
    amplitudes = np.zeros(2**n, dtype=np.complex128)
    amplitudes[0] = 1.0
    return amplitudes


def normalize(amplitudes: np.ndarray) -> np.ndarray:
    """Нормировать вектор состояния (защита от накопленной ошибки)."""

    norm = float(np.linalg.norm(amplitudes))
    if norm == 0.0:
        raise ValueError("Вектор состояния имеет нулевую норму.")
    return amplitudes / norm


def apply_gate_to_array(
    states: np.ndarray,
    n_qubits: int,
    gate_key: str,
    target: int,
    control: int | None = None,
) -> np.ndarray:
    """Применить вентиль к вектору состояния или пакету векторов.

    Parameters
    ----------
    states : np.ndarray
        Массив формы ``(2**n,)`` либо ``(shots, 2**n)`` (любое число
        ведущих осей).
    n_qubits : int
        Число кубитов.
    gate_key : str
        ``"x"``, ``"h"``, ``"z"`` или ``"cnot"``.
    target : int
        Целевой кубит.
    control : int | None
        Управляющий кубит, обязателен для ``"cnot"``.

    Returns
    -------
    np.ndarray
        Новый массив той же формы.

    Notes
    -----
    Функция не изменяет входной массив.
    """

    n = validate_qubit_count(n_qubits)
    gate = get_gate(gate_key)
    target = validate_qubit_index(target, n, "целевого кубита")

    array = np.asarray(states, dtype=np.complex128)
    if array.ndim < 1 or array.shape[-1] != 2**n:
        raise ValueError(
            f"Ожидался вектор состояния длины {2**n}, получена форма {array.shape}."
        )

    lead = array.ndim - 1
    tensor = array.reshape(array.shape[:-1] + (2,) * n)

    if gate.num_qubits == 1:
        axis = lead + target
        moved = np.moveaxis(tensor, axis, lead)
        moved = np.tensordot(gate.matrix, moved, axes=([1], [lead]))
        # tensordot ставит ось матрицы (размер 2) на первое место.
        moved = np.moveaxis(moved, 0, axis)
    else:
        if control is None:
            raise ValueError("Для вентиля CNOT необходимо указать управляющий кубит.")
        control = validate_qubit_index(control, n, "управляющего кубита")
        if control == target:
            raise ValueError(
                "Управляющий и целевой кубиты CNOT должны различаться."
            )
        axes = (lead + control, lead + target)
        moved = np.moveaxis(tensor, axes, (lead, lead + 1))
        # Матрица 4×4 представляется тензором (control', target', control, target).
        matrix = gate.matrix.reshape(2, 2, 2, 2)
        moved = np.tensordot(matrix, moved, axes=([2, 3], [lead, lead + 1]))
        moved = np.moveaxis(moved, (0, 1), axes)

    return moved.reshape(array.shape)


def apply_gate(
    amplitudes: np.ndarray,
    n_qubits: int,
    gate_key: str,
    target: int,
    control: int | None = None,
) -> np.ndarray:
    """Применить вентиль к одному вектору состояния."""

    array = np.asarray(amplitudes, dtype=np.complex128)
    if array.ndim != 1:
        raise ValueError("Ожидался одномерный вектор состояния.")
    return apply_gate_to_array(array, n_qubits, gate_key, target, control)


def probabilities(amplitudes: np.ndarray) -> np.ndarray:
    """Вероятности базисных состояний: |a_i|^2.

    Для пакета состояний возвращает массив формы ``(shots, 2**n)``.
    """

    array = np.asarray(amplitudes)
    return np.abs(array) ** 2


def marginal_probabilities(
    state_probabilities: np.ndarray,
    n_qubits: int,
    measured_qubits: Sequence[int],
) -> np.ndarray:
    """Просуммировать вероятности по не измеряемым кубитам.

    Parameters
    ----------
    state_probabilities : np.ndarray
        Массив формы ``(2**n,)`` или ``(shots, 2**n)``.
    n_qubits : int
        Число кубитов.
    measured_qubits : Sequence[int]
        Номера измеряемых кубитов в порядке возрастания.

    Returns
    -------
    np.ndarray
        Массив формы ``(2**m,)`` или ``(shots, 2**m)``, где ``m`` — число
        измеряемых кубитов. Порядок битов: слева — первый измеряемый кубит.
    """

    n = validate_qubit_count(n_qubits)
    measured = [validate_qubit_index(q, n, "измеряемого кубита") for q in measured_qubits]
    if not measured:
        raise ValueError("Не выбран ни один кубит для измерения.")
    if len(set(measured)) != len(measured):
        raise ValueError("Кубиты для измерения не должны повторяться.")

    array = np.asarray(state_probabilities, dtype=np.float64)
    if array.shape[-1] != 2**n:
        raise ValueError(
            f"Ожидался массив вероятностей длины {2**n}, получена форма {array.shape}."
        )

    lead_shape = array.shape[:-1]
    tensor = array.reshape(lead_shape + (2,) * n)
    sum_axes = tuple(
        (len(lead_shape) + q) for q in range(n) if q not in measured
    )
    if sum_axes:
        tensor = tensor.sum(axis=sum_axes)
    # Оставшиеся оси соответствуют измеряемым кубитам в порядке возрастания
    # номеров, то есть в том же порядке, что и measured.
    return np.ascontiguousarray(tensor.reshape(lead_shape + (2 ** len(measured),)))


def bit_matrix(outcomes: np.ndarray, n_bits: int) -> np.ndarray:
    """Представить целочисленные исходы как матрицу битов.

    Старший бит (слева) соответствует первому измеряемому кубиту —
    той же нотации, что и в битовых строках интерфейса.
    """

    shifts = np.arange(n_bits - 1, -1, -1, dtype=np.int64)
    return ((outcomes[:, None] >> shifts[None, :]) & 1).astype(np.uint8)


def bitstrings_from_indices(indices: Iterable[int], n_bits: int) -> List[str]:
    """Преобразовать индексы исходов в битовые строки ширины ``n_bits``."""

    return [format(int(index), f"0{n_bits}b") for index in indices]


def state_memory_bytes(n_qubits: int) -> int:
    """Оценка объёма памяти под вектор состояния (complex128)."""

    n = validate_qubit_count(n_qubits)
    return 16 * 2**n


class QuantumState:
    """Вектор состояния регистра из ``n`` кубитов.

    Класс хранит амплитуды в одном массиве и предоставляет операции
    для интерактивной части приложения. Метод :meth:`apply` изменяет
    состояние на месте.

    Examples
    --------
    >>> state = QuantumState.zero(1)
    >>> state.apply("h", 0).apply("h", 0)
    >>> state.is_normalized()
    True
    """

    __slots__ = ("n_qubits", "amplitudes")

    def __init__(self, n_qubits: int, amplitudes: np.ndarray | None = None) -> None:
        self.n_qubits = validate_qubit_count(n_qubits)
        if amplitudes is None:
            self.amplitudes = zero_state(self.n_qubits)
        else:
            array = np.asarray(amplitudes, dtype=np.complex128).reshape(-1)
            if array.size != 2**self.n_qubits:
                raise ValueError(
                    f"Для {self.n_qubits} кубитов нужен вектор длины "
                    f"{2**self.n_qubits}, получено {array.size}."
                )
            self.amplitudes = array.copy()

    @classmethod
    def zero(cls, n_qubits: int) -> "QuantumState":
        """Создать состояние |00…0⟩."""

        return cls(n_qubits)

    @classmethod
    def from_basis_state(cls, n_qubits: int, index: int) -> "QuantumState":
        """Создать базисное состояние по его индексу."""

        n = validate_qubit_count(n_qubits)
        if not 0 <= int(index) < 2**n:
            raise ValueError(
                f"Индекс базисного состояния должен быть в диапазоне "
                f"0..{2**n - 1}, получено {index}."
            )
        amplitudes = np.zeros(2**n, dtype=np.complex128)
        amplitudes[int(index)] = 1.0
        return cls(n, amplitudes)

    def copy(self) -> "QuantumState":
        """Глубокая копия состояния."""

        return QuantumState(self.n_qubits, self.amplitudes)

    def apply(
        self, gate_key: str, target: int, control: int | None = None
    ) -> "QuantumState":
        """Применить вентиль на месте и вернуть ``self``."""

        self.amplitudes = apply_gate(
            self.amplitudes, self.n_qubits, gate_key, target, control
        )
        return self

    @property
    def probabilities(self) -> np.ndarray:
        """Вероятности базисных состояний."""

        return probabilities(self.amplitudes)

    def probabilities_of(self, qubits: Sequence[int]) -> np.ndarray:
        """Маргинальные вероятности для выбранных кубитов."""

        return marginal_probabilities(self.probabilities, self.n_qubits, qubits)

    def norm(self) -> float:
        """Евклидова норма вектора состояния."""

        return float(np.linalg.norm(self.amplitudes))

    def total_probability(self) -> float:
        """Сумма вероятностей базисных состояний."""

        return float(np.sum(self.probabilities))

    def is_normalized(self, tolerance: float = TOLERANCE) -> bool:
        """Проверить нормировку с допустимой погрешностью."""

        return abs(self.total_probability() - 1.0) <= tolerance

    def basis_state_index(self) -> int:
        """Индекс базисного состояния, если состояние базисное, иначе -1."""

        probs = self.probabilities
        index = int(np.argmax(probs))
        return index if probs[index] >= 1.0 - TOLERANCE else -1

    def label(self, index: int) -> str:
        """Битовая строка для индекса базисного состояния."""

        return format(int(index), f"0{self.n_qubits}b")

    def nonzero_amplitudes(self, threshold: float = 1e-12) -> List[Tuple[str, complex]]:
        """Список (битовая строка, амплитуда) для ненулевых компонент."""

        result: List[Tuple[str, complex]] = []
        for index, amplitude in enumerate(self.amplitudes):
            if abs(amplitude) > threshold:
                result.append((self.label(index), complex(amplitude)))
        return result
