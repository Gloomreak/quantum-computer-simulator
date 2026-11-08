"""Квантовая схема: операции, параметры, проверка корректности, сериализация.

Схема — это упорядоченный список операций над кубитами регистра.
Измерение в модели не является отдельным вентилем: схема содержит
множество измеряемых кубитов, и измерение выполняется после всех
операций (в интерфейсе отображается отдельным столбцом «M»).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence

from .gates import GATE_KEYS, get_gate
from .statevector import MAX_QUBITS, validate_qubit_count, validate_qubit_index

FORMAT_VERSION: int = 1

LEVEL_ERROR: str = "error"
LEVEL_WARNING: str = "warning"


def _as_qubit_number(value: Any, role: str) -> int:
    """Привести номер кубита к ``int`` и понятно сообщить об ошибке."""

    if isinstance(value, bool):
        raise ValueError(f"Номер {role} кубита должен быть целым числом.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Номер {role} кубита должен быть целым числом, получено {value!r}."
        ) from exc


@dataclass(frozen=True)
class ValidationIssue:
    """Замечание к схеме: ошибка или предупреждение."""

    level: str
    code: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.level == LEVEL_ERROR


@dataclass(frozen=True)
class Operation:
    """Одна операция схемы.

    Для однокубитных вентилей ``control`` равен ``None``. Для CNOT
    обязательны и ``control``, и ``target``, причём они различаются.
    """

    gate: str
    target: int
    control: int | None = None

    def __post_init__(self) -> None:
        key = str(self.gate).strip().lower()
        if key not in GATE_KEYS:
            raise ValueError(
                f"Неизвестный вентиль {self.gate!r}. "
                f"Допустимые значения: {', '.join(GATE_KEYS)}."
            )
        object.__setattr__(self, "gate", key)
        object.__setattr__(self, "target", _as_qubit_number(self.target, "целевого"))
        if self.control is not None:
            object.__setattr__(
                self, "control", _as_qubit_number(self.control, "управляющего")
            )
        if get_gate(key).num_qubits == 1 and self.control is not None:
            raise ValueError(
                f"Вентиль {get_gate(key).symbol} действует на один кубит "
                "и не имеет управляющего кубита."
            )
        if get_gate(key).num_qubits == 2 and self.control is None:
            raise ValueError("Для CNOT необходимо указать управляющий кубит.")

    @property
    def symbol(self) -> str:
        return get_gate(self.gate).symbol

    def involved_qubits(self) -> tuple[int, ...]:
        """Кубиты, к которым применяется вентиль (порядок фиксирован)."""

        if self.control is None:
            return (self.target,)
        return (self.control, self.target)

    def describe(self) -> str:
        """Понятное описание операции для интерфейса."""

        if self.control is None:
            return f"{self.symbol} на кубите q{self.target}"
        return f"CNOT: управляющий q{self.control} → целевой q{self.target}"

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"gate": self.gate, "target": self.target}
        if self.control is not None:
            data["control"] = self.control
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Operation":
        if not isinstance(data, dict):
            raise ValueError("Операция должна быть описана объектом JSON.")
        if "gate" not in data:
            raise ValueError("В описании операции отсутствует поле 'gate'.")
        if "target" not in data:
            raise ValueError("В описании операции отсутствует поле 'target'.")
        control = data.get("control")
        return cls(gate=data["gate"], target=data["target"], control=control)


@dataclass
class Circuit:
    """Квантовая схема для регистра из ``n_qubits`` кубитов."""

    n_qubits: int
    operations: List[Operation] = field(default_factory=list)
    measured_qubits: List[int] | None = None
    name: str = "Своя схема"
    description: str = ""

    def __post_init__(self) -> None:
        self.n_qubits = validate_qubit_count(self.n_qubits)
        self.operations = [
            op if isinstance(op, Operation) else Operation.from_dict(op)
            for op in self.operations
        ]
        if self.measured_qubits is None:
            self.measured_qubits = list(range(self.n_qubits))
        else:
            self.measured_qubits = sorted(int(q) for q in self.measured_qubits)

    # ------------------------------------------------------------------
    # Параметры схемы
    # ------------------------------------------------------------------
    @property
    def measured(self) -> List[int]:
        """Список измеряемых кубитов (по возрастанию номеров)."""

        if not self.measured_qubits:
            return []
        return list(self.measured_qubits)

    @property
    def gate_count(self) -> int:
        """Количество операций (без измерения)."""

        return len(self.operations)

    @property
    def measured_count(self) -> int:
        """Число измеряемых кубитов."""

        return len(self.measured)

    @property
    def is_empty(self) -> bool:
        """Схема не содержит ни одной операции."""

        return not self.operations

    def layers(self) -> List[int]:
        """Номер «временного слоя» для каждой операции.

        Операции, действующие на разные кубиты, могут выполняться
        одновременно и попадать в один слой — так схема рисуется
        компактнее.
        """

        depth = [0] * self.n_qubits
        layers: List[int] = []
        for op in self.operations:
            qubits = op.involved_qubits()
            for qubit in qubits:
                validate_qubit_index(qubit, self.n_qubits)
            layer = max(depth[q] for q in qubits) + 1
            for qubit in qubits:
                depth[qubit] = layer
            layers.append(layer)
        return layers

    def depth(self) -> int:
        """Глубина схемы — число последовательных слоёв операций."""

        layers = self.layers()
        return max(layers) if layers else 0

    def counts_by_gate(self) -> Dict[str, int]:
        """Сколько раз встречается каждый вентиль."""

        result: Dict[str, int] = {}
        for op in self.operations:
            result[op.gate] = result.get(op.gate, 0) + 1
        return result

    # ------------------------------------------------------------------
    # Изменение схемы
    # ------------------------------------------------------------------
    def add(self, operation: Operation) -> "Circuit":
        """Добавить операцию в конец схемы."""

        self.operations.append(operation)
        return self

    def add_gate(
        self, gate: str, target: int, control: int | None = None
    ) -> "Circuit":
        """Добавить операцию по параметрам вентиля."""

        return self.add(Operation(gate=gate, target=target, control=control))

    def remove(self, index: int) -> Operation:
        """Удалить операцию по индексу и вернуть её."""

        self._check_operation_index(index)
        return self.operations.pop(index)

    def clear(self) -> None:
        """Удалить все операции."""

        self.operations.clear()

    def move(self, index: int, offset: int) -> int:
        """Сдвинуть операцию на ``offset`` позиций (например, -1 или +1).

        Возвращает новый индекс операции. Порядок операций влияет на
        результат, если операции действуют на одни и те же кубиты,
        поэтому интерфейс предупреждает об этом пользователя.
        """

        self._check_operation_index(index)
        new_index = index + int(offset)
        if new_index < 0 or new_index >= len(self.operations):
            raise ValueError("Операцию нельзя сдвинуть за пределы схемы.")
        operation = self.operations.pop(index)
        self.operations.insert(new_index, operation)
        return new_index

    def _check_operation_index(self, index: int) -> None:
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("Индекс операции должен быть целым числом.")
        if index < 0 or index >= len(self.operations):
            raise ValueError(
                f"Операции с номером {index} нет: в схеме {len(self.operations)} операций."
            )

    def copy(self) -> "Circuit":
        """Полная копия схемы."""

        return Circuit(
            n_qubits=self.n_qubits,
            operations=list(self.operations),
            measured_qubits=list(self.measured),
            name=self.name,
            description=self.description,
        )

    # ------------------------------------------------------------------
    # Проверка корректности
    # ------------------------------------------------------------------
    def validate(self) -> List[ValidationIssue]:
        """Проверить схему и вернуть список замечаний.

        Ошибки (``level == "error"``) препятствуют запуску,
        предупреждения — нет.
        """

        issues: List[ValidationIssue] = []

        if len(self.measured) == 0:
            issues.append(
                ValidationIssue(
                    LEVEL_ERROR,
                    "measurement_empty",
                    "Не выбран ни один кубит для измерения: результаты измерить нечем.",
                )
            )

        seen: set[int] = set()
        for qubit in self.measured:
            if qubit in seen:
                issues.append(
                    ValidationIssue(
                        LEVEL_ERROR,
                        "measurement_duplicate",
                        f"Кубит q{qubit} указан для измерения дважды.",
                    )
                )
                continue
            seen.add(qubit)
            if qubit < 0 or qubit >= self.n_qubits:
                issues.append(
                    ValidationIssue(
                        LEVEL_ERROR,
                        "measurement_range",
                        f"Кубит q{qubit} нельзя измерить: в схеме "
                        f"{self.n_qubits} кубит(ов).",
                    )
                )

        if not self.operations:
            issues.append(
                ValidationIssue(
                    LEVEL_WARNING,
                    "empty_circuit",
                    "Схема не содержит операций: будет измерено начальное "
                    "состояние |00…0⟩.",
                )
            )

        for position, operation in enumerate(self.operations):
            number = position + 1
            gate = get_gate(operation.gate)
            for qubit, role in (
                (operation.target, "целевой кубит"),
                (operation.control, "управляющий кубит"),
            ):
                if qubit is None:
                    continue
                if qubit < 0 or qubit >= self.n_qubits:
                    issues.append(
                        ValidationIssue(
                            LEVEL_ERROR,
                            "qubit_range",
                            f"Операция №{number} ({gate.symbol}): {role} q{qubit} "
                            f"отсутствует в схеме из {self.n_qubits} кубит(ов).",
                        )
                    )
            if (
                operation.control is not None
                and operation.control == operation.target
            ):
                issues.append(
                    ValidationIssue(
                        LEVEL_ERROR,
                        "cnot_same_qubits",
                        f"Операция №{number}: у CNOT управляющий и целевой кубиты "
                        "должны различаться.",
                    )
                )
        return issues

    def errors(self) -> List[ValidationIssue]:
        """Только ошибки схемы."""

        return [issue for issue in self.validate() if issue.is_error]

    def warnings(self) -> List[ValidationIssue]:
        """Только предупреждения."""

        return [issue for issue in self.validate() if not issue.is_error]

    def is_valid(self) -> bool:
        """Схему можно запустить (ошибок нет)."""

        return not self.errors()

    def validate_or_raise(self) -> None:
        """Выбросить ``ValueError`` с понятным текстом, если есть ошибки."""

        errors = self.errors()
        if errors:
            raise ValueError(" ".join(issue.message for issue in errors))

    # ------------------------------------------------------------------
    # Сериализация
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Представление схемы для JSON."""

        return {
            "format_version": FORMAT_VERSION,
            "name": self.name,
            "description": self.description,
            "n_qubits": self.n_qubits,
            "measured_qubits": self.measured,
            "operations": [op.to_dict() for op in self.operations],
        }

    def to_json(self, indent: int = 2) -> str:
        """Сериализовать схему в JSON-строку."""

        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Circuit":
        """Восстановить схему из словаря с проверкой структуры."""

        if not isinstance(data, dict):
            raise ValueError("Описание схемы должно быть объектом JSON.")
        if "n_qubits" not in data:
            raise ValueError("В описании схемы отсутствует поле 'n_qubits'.")
        raw_operations = data.get("operations", [])
        if not isinstance(raw_operations, list):
            raise ValueError("Поле 'operations' должно быть списком операций.")
        operations = [Operation.from_dict(item) for item in raw_operations]
        measured = data.get("measured_qubits")
        if measured is not None and not isinstance(measured, list):
            raise ValueError("Поле 'measured_qubits' должно быть списком номеров.")
        circuit = cls(
            n_qubits=int(data["n_qubits"]),
            operations=operations,
            measured_qubits=None if measured is None else [int(q) for q in measured],
            name=str(data.get("name") or "Своя схема"),
            description=str(data.get("description") or ""),
        )
        circuit.validate_or_raise()
        return circuit

    @classmethod
    def from_json(cls, text: str) -> "Circuit":
        """Восстановить схему из JSON-строки."""

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Файл не является корректным JSON: {exc.msg}.") from exc
        return cls.from_dict(data)


def circuit_from_operations(
    n_qubits: int,
    operations: Iterable[Sequence[Any]],
    measured_qubits: List[int] | None = None,
    name: str = "Своя схема",
) -> Circuit:
    """Собрать схему из компактного списка операций.

    Каждая операция задаётся парой ``(вентиль, целевой_кубит)`` или
    тройкой ``(вентиль, управляющий, целевой)`` для CNOT.
    """

    ops: List[Operation] = []
    for item in operations:
        values = list(item)
        if len(values) == 2:
            ops.append(Operation(gate=values[0], target=int(values[1])))
        elif len(values) == 3:
            ops.append(
                Operation(gate=values[0], target=int(values[2]), control=int(values[1]))
            )
        else:
            raise ValueError(
                "Операция должна содержать 2 или 3 элемента: "
                "(вентиль, целевой) или (вентиль, управляющий, целевой)."
            )
    return Circuit(
        n_qubits=n_qubits,
        operations=ops,
        measured_qubits=measured_qubits,
        name=name,
    )


__all__ = [
    "Circuit",
    "Operation",
    "ValidationIssue",
    "FORMAT_VERSION",
    "LEVEL_ERROR",
    "LEVEL_WARNING",
    "MAX_QUBITS",
    "circuit_from_operations",
]
