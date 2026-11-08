"""Демонстрационные схемы.

Схемы хранятся в ``examples/demo_circuits.json`` (требование ТЗ о готовом
наборе примеров) и загружаются один раз при старте приложения. Загрузка
проверяет структуру и корректность каждой схемы, поэтому повреждённый
файл не приведёт к «тихому» появлению неверной схемы.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

from .quantum.circuit import Circuit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_PATH = PROJECT_ROOT / "examples" / "demo_circuits.json"


@dataclass(frozen=True)
class DemoCircuit:
    """Демонстрационная схема с пояснением для интерфейса."""

    key: str
    name: str
    description: str
    purpose: str
    circuit: Circuit
    default_target: str | None = None

    @property
    def n_qubits(self) -> int:
        return self.circuit.n_qubits


def _parse_demo(item: dict) -> DemoCircuit:
    if not isinstance(item, dict):
        raise ValueError("Каждый элемент списка схем должен быть объектом JSON.")
    for field in ("key", "name", "circuit"):
        if field not in item:
            raise ValueError(f"В описании демонстрационной схемы нет поля {field!r}.")
    circuit = Circuit.from_dict(item["circuit"])
    circuit.name = str(item["name"])
    target = item.get("target")
    if target is not None:
        target = str(target)
        if target not in _all_labels(circuit):
            raise ValueError(
                f"Схема {item['key']!r}: целевая строка {target!r} не входит "
                "в набор возможных исходов."
            )
    return DemoCircuit(
        key=str(item["key"]),
        name=str(item["name"]),
        description=str(item.get("description", "")),
        purpose=str(item.get("purpose", "")),
        circuit=circuit,
        default_target=target,
    )


def _all_labels(circuit: Circuit) -> List[str]:
    width = circuit.measured_count
    return [format(index, f"0{width}b") for index in range(2**width)]


@lru_cache(maxsize=1)
def load_demo_circuits() -> Tuple[DemoCircuit, ...]:
    """Загрузить и проверить все демонстрационные схемы."""

    if not DEMO_PATH.exists():
        raise FileNotFoundError(
            f"Не найден файл демонстрационных схем: {DEMO_PATH}. "
            "Проверьте, что каталог examples скопирован вместе с приложением."
        )
    try:
        data = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Файл демонстрационных схем повреждён: {exc.msg}.") from exc

    items = data.get("circuits") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ValueError("Файл демонстрационных схем не содержит списка схем.")

    demos = tuple(_parse_demo(item) for item in items)
    keys = [demo.key for demo in demos]
    if len(set(keys)) != len(keys):
        raise ValueError("Ключи демонстрационных схем должны быть уникальны.")
    return demos


def demo_by_key(key: str) -> DemoCircuit:
    """Найти схему по ключу."""

    for demo in load_demo_circuits():
        if demo.key == key:
            return demo
    raise KeyError(f"Демонстрационная схема {key!r} не найдена.")


def demo_names() -> List[str]:
    """Названия схем в порядке файла."""

    return [demo.name for demo in load_demo_circuits()]


def demo_circuit(key: str) -> Circuit:
    """Вернуть копию схемы по ключу."""

    return demo_by_key(key).circuit.copy()


def default_demo() -> DemoCircuit:
    """Схема, предлагаемая по умолчанию (состояние Белла)."""

    demos = {demo.key: demo for demo in load_demo_circuits()}
    return demos.get("bell") or load_demo_circuits()[0]


__all__ = [
    "DEMO_PATH",
    "DemoCircuit",
    "PROJECT_ROOT",
    "default_demo",
    "demo_by_key",
    "demo_circuit",
    "demo_names",
    "load_demo_circuits",
]
