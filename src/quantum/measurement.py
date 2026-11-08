"""Измерение: вероятности, случайная выборка (sampling), ошибки считывания.

Стохастическое измерение выполняется по стандартной схеме обратного
преобразования распределения: строится кумулятивная сумма вероятностей
и для каждого запуска (shot) разыгрывается равномерное число
``u ∈ [0, 1)``; исход — первый базисный индекс, для которого
накопленная вероятность превышает ``u``.

Для воспроизводимости все случайные числа берутся из явно заданного
генератора ``numpy.random.Generator``.
"""

from __future__ import annotations

from typing import Dict, Sequence

import numpy as np

from .statevector import (
    bit_matrix,
    bitstrings_from_indices,
    marginal_probabilities,
    validate_qubit_count,
)

MAX_SHOTS: int = 200_000
"""Верхний предел числа измерений за один запуск."""


def validate_shots(shots: int) -> int:
    """Проверить число измерений."""

    if isinstance(shots, bool) or not isinstance(shots, (int, np.integer)):
        raise ValueError(f"Число измерений должно быть целым, получено {shots!r}.")
    value = int(shots)
    if value < 1:
        raise ValueError("Число измерений (shots) должно быть не меньше 1.")
    if value > MAX_SHOTS:
        raise ValueError(
            f"Число измерений {value} превышает предел {MAX_SHOTS}. "
            "Уменьшите параметр: точность растёт как 1/√shots, а время — линейно."
        )
    return value


def validate_seed(seed: int) -> int:
    """Проверить и привести к допустимому виду random seed."""

    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError(f"Random seed должен быть целым числом, получено {seed!r}.")
    value = int(seed)
    if value < 0 or value > 2**32 - 1:
        raise ValueError(
            "Random seed должен быть в диапазоне от 0 до 4294967295."
        )
    return value


def make_generators(seed: int) -> Dict[str, np.random.Generator]:
    """Создать независимые генераторы для разных этапов моделирования.

    Раздельные потоки нужны для того, чтобы включение или отключение
    одного канала ошибок не сдвигало выборку в другом канале. Благодаря
    этому при ``p = 0`` шумовой запуск совпадает с идеальным.
    """

    safe_seed = validate_seed(seed)
    sequence = np.random.SeedSequence([safe_seed, 0x51A7E])
    state_seq, noise_seq, readout_seq = sequence.spawn(3)
    return {
        "state": np.random.default_rng(state_seq),
        "noise": np.random.default_rng(noise_seq),
        "readout": np.random.default_rng(readout_seq),
    }


def normalize_probabilities(
    probabilities: np.ndarray, tolerance: float = 1e-9
) -> np.ndarray:
    """Проверить и нормировать распределение вероятностей.

    Для двумерного массива (набор распределений) нормировка выполняется
    построчно.
    """

    array = np.asarray(probabilities, dtype=np.float64)
    if array.ndim not in (1, 2):
        raise ValueError("Ожидался одномерный или двумерный массив вероятностей.")
    if np.any(array < -tolerance):
        raise ValueError("Вероятности не могут быть отрицательными.")
    clipped = np.clip(array, 0.0, None)
    if clipped.ndim == 1:
        total = float(clipped.sum())
        if total <= 0.0:
            raise ValueError("Сумма вероятностей должна быть положительной.")
        return clipped / total
    totals = clipped.sum(axis=1, keepdims=True)
    if np.any(totals <= 0.0):
        raise ValueError("Сумма вероятностей должна быть положительной.")
    return clipped / totals


def sample_outcomes(
    probabilities: np.ndarray,
    shots: int,
    generator: np.random.Generator,
    chunk_size: int = 8192,
) -> np.ndarray:
    """Разыграть ``shots`` исходов измерения.

    Parameters
    ----------
    probabilities : np.ndarray
        Одно распределение формы ``(2**m,)`` или набор распределений
        формы ``(shots, 2**m)`` (для шумовых траекторий).
    shots : int
        Число измерений.
    generator : np.random.Generator
        Генератор случайных чисел.
    chunk_size : int
        Размер блока при построчной выборке (экономия памяти).

    Returns
    -------
    np.ndarray
        Целочисленные индексы исходов формы ``(shots,)``.
    """

    count = validate_shots(shots)
    array = np.asarray(probabilities, dtype=np.float64)

    if array.ndim == 1:
        distribution = normalize_probabilities(array)
        cumulative = np.cumsum(distribution)
        cumulative[-1] = 1.0
        uniforms = generator.random(count)
        outcomes = np.searchsorted(cumulative, uniforms, side="left")
        return np.clip(outcomes, 0, distribution.size - 1).astype(np.int64)

    if array.ndim != 2:
        raise ValueError("Ожидался массив вероятностей формы (2**m,) или (shots, 2**m).")
    if array.shape[0] != count:
        raise ValueError(
            f"Число распределений ({array.shape[0]}) не совпадает с числом "
            f"измерений ({count})."
        )

    outcomes = np.empty(count, dtype=np.int64)
    for start in range(0, count, chunk_size):
        stop = min(start + chunk_size, count)
        block = normalize_probabilities(array[start:stop])
        cumulative = np.cumsum(block, axis=1)
        cumulative[:, -1] = 1.0
        uniforms = generator.random(stop - start)
        # Число накопленных вероятностей, строго меньших u, равно индексу
        # первого элемента, для которого cdf >= u (аналог searchsorted
        # с side="left"). Векторизация по всем строкам блока сразу.
        indices = np.count_nonzero(cumulative < uniforms[:, None], axis=1)
        outcomes[start:stop] = np.clip(indices, 0, block.shape[1] - 1)
    return outcomes


def apply_readout_error(
    outcomes: np.ndarray,
    n_bits: int,
    probability: float,
    generator: np.random.Generator,
) -> np.ndarray:
    """Инвертировать измеренные биты с заданной вероятностью.

    Каждый бит каждого измерения инвертируется независимо. Функция не
    изменяет входной массив.
    """

    if n_bits < 1:
        raise ValueError("Число измеряемых битов должно быть не меньше 1.")
    if not 0.0 <= float(probability) <= 1.0:
        raise ValueError("Вероятность ошибки считывания должна быть от 0 до 1.")
    array = np.asarray(outcomes, dtype=np.int64)
    if array.ndim != 1:
        raise ValueError("Ожидался одномерный массив исходов.")
    if probability <= 0.0:
        return array.copy()
    flips = generator.random((array.size, n_bits)) < float(probability)
    bits = bit_matrix(array, n_bits).astype(np.int64)
    bits = np.bitwise_xor(bits, flips.astype(np.int64))
    weights = 2 ** np.arange(n_bits - 1, -1, -1, dtype=np.int64)
    return (bits * weights).sum(axis=1).astype(np.int64)


def probabilities_from_counts(
    counts: Dict[str, int], labels: Sequence[str]
) -> np.ndarray:
    """Преобразовать абсолютные частоты в вероятности.

    ``labels`` задаёт порядок битовых строк и длину результата.
    """

    total = sum(counts.values())
    if total <= 0:
        raise ValueError("Сумма частот должна быть положительной.")
    return np.asarray([counts.get(label, 0) / total for label in labels], dtype=float)


def counts_from_outcomes(
    outcomes: np.ndarray, n_bits: int
) -> Dict[str, int]:
    """Посчитать частоты исходов и вернуть словарь «битовая строка → число»."""

    array = np.asarray(outcomes, dtype=np.int64)
    if array.ndim != 1:
        raise ValueError("Ожидался одномерный массив исходов.")
    size = 2**n_bits
    if array.size and (array.min() < 0 or array.max() >= size):
        raise ValueError("Индекс исхода выходит за пределы разрядности.")
    counts = np.bincount(array, minlength=size)
    labels = bitstrings_from_indices(range(size), n_bits)
    return {label: int(count) for label, count in zip(labels, counts)}


def measured_distribution(
    state_probabilities: np.ndarray,
    n_qubits: int,
    measured_qubits: Sequence[int],
) -> np.ndarray:
    """Теоретическое распределение результатов по измеряемым кубитам."""

    validate_qubit_count(n_qubits)
    marginal = marginal_probabilities(state_probabilities, n_qubits, measured_qubits)
    return normalize_probabilities(marginal)


__all__ = [
    "MAX_SHOTS",
    "apply_readout_error",
    "counts_from_outcomes",
    "make_generators",
    "measured_distribution",
    "normalize_probabilities",
    "probabilities_from_counts",
    "sample_outcomes",
    "validate_seed",
    "validate_shots",
]
