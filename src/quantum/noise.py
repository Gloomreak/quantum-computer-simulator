"""Модели аппаратных ошибок.

В симуляторе реализованы три учебных канала ошибок:

``bit_flip``
    После применения вентиля к кубиту с вероятностью ``p`` применяется
    X-преобразование (переворот бита).

``phase_flip``
    После применения вентиля к кубиту с вероятностью ``p`` применяется
    Z-преобразование (фазовая ошибка). Вероятности в вычислительном
    базисе от такой ошибки не меняются, но она меняет относительные
    фазы и влияет на результат, если дальше в схеме есть вентили,
    меняющие базис (например, H).

``readout``
    При считывании каждый измеренный бит независимо инвертируется
    с вероятностью ``p_readout`` — модель ошибки измерения.

Это упрощённые модели: они не описывают амплитудное затухание,
деполяризацию, коррелированные ошибки и зависимость от времени
(T1/T2). Такие каналы сознательно не добавлены, чтобы сохранить
прозрачность модели (см. README и docs/MATH_MODEL.md).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Tuple

# Диапазон вероятностей, доступный в интерфейсе (требование ТЗ: 0…0,2).
UI_MAX_PROBABILITY: float = 0.2
# Абсолютный предел для вычислительного ядра (используется тестами и
# расширенными экспериментами, где нужны p вплоть до 0,5 и 1,0).
ABSOLUTE_MAX_PROBABILITY: float = 1.0


@dataclass(frozen=True)
class NoiseConfig:
    """Настройки всех каналов ошибок.

    Поле ``enabled`` включает режим «Модель с ошибками» целиком.
    Остальные флаги позволяют независимо отключать каналы.
    """

    enabled: bool = False
    bit_flip_enabled: bool = True
    phase_flip_enabled: bool = True
    readout_enabled: bool = True
    p_bit_flip: float = 0.02
    p_phase_flip: float = 0.02
    p_readout: float = 0.02

    def __post_init__(self) -> None:
        for field_name, label in (
            ("p_bit_flip", "вероятность bit-flip"),
            ("p_phase_flip", "вероятность phase-flip"),
            ("p_readout", "вероятность ошибки считывания"),
        ):
            value = getattr(self, field_name)
            setattr_value = _validate_probability(value, label)
            object.__setattr__(self, field_name, setattr_value)

    # ------------------------------------------------------------------
    # Состояние каналов
    # ------------------------------------------------------------------
    @property
    def bit_flip_active(self) -> bool:
        return self.enabled and self.bit_flip_enabled and self.p_bit_flip > 0.0

    @property
    def phase_flip_active(self) -> bool:
        return self.enabled and self.phase_flip_enabled and self.p_phase_flip > 0.0

    @property
    def readout_active(self) -> bool:
        return self.enabled and self.readout_enabled and self.p_readout > 0.0

    @property
    def gate_noise_active(self) -> bool:
        """Активен хотя бы один канал ошибок вентилей."""

        return self.bit_flip_active or self.phase_flip_active

    @property
    def is_active(self) -> bool:
        """Включён режим ошибок и хотя бы один канал реально действует."""

        return self.gate_noise_active or self.readout_active

    @property
    def has_enabled_channel(self) -> bool:
        """Режим ошибок включён, даже если вероятности равны нулю."""

        return self.enabled

    def active_channels(self) -> List[str]:
        """Активные каналы в человекочитаемом виде."""

        channels: List[str] = []
        if self.bit_flip_active:
            channels.append(f"bit-flip (X), p = {self.p_bit_flip:g}")
        if self.phase_flip_active:
            channels.append(f"phase-flip (Z), p = {self.p_phase_flip:g}")
        if self.readout_active:
            channels.append(f"ошибка считывания, p = {self.p_readout:g}")
        return channels

    def summary(self) -> str:
        """Краткое описание настроек для панели параметров запуска."""

        if not self.enabled:
            return "Идеальная модель (ошибки отключены)"
        if not self.active_channels():
            return "Модель с ошибками включена, но все вероятности равны 0"
        return "Модель с ошибками: " + "; ".join(self.active_channels())

    def copy(self) -> "NoiseConfig":
        return replace(self)

    # ------------------------------------------------------------------
    # Сериализация
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "bit_flip_enabled": self.bit_flip_enabled,
            "phase_flip_enabled": self.phase_flip_enabled,
            "readout_enabled": self.readout_enabled,
            "p_bit_flip": self.p_bit_flip,
            "p_phase_flip": self.p_phase_flip,
            "p_readout": self.p_readout,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NoiseConfig":
        if not isinstance(data, dict):
            raise ValueError("Настройки ошибок должны быть объектом JSON.")
        defaults = cls()
        return cls(
            enabled=bool(data.get("enabled", defaults.enabled)),
            bit_flip_enabled=bool(
                data.get("bit_flip_enabled", defaults.bit_flip_enabled)
            ),
            phase_flip_enabled=bool(
                data.get("phase_flip_enabled", defaults.phase_flip_enabled)
            ),
            readout_enabled=bool(
                data.get("readout_enabled", defaults.readout_enabled)
            ),
            p_bit_flip=float(data.get("p_bit_flip", defaults.p_bit_flip)),
            p_phase_flip=float(data.get("p_phase_flip", defaults.p_phase_flip)),
            p_readout=float(data.get("p_readout", defaults.p_readout)),
        )


def _validate_probability(value: float, label: str) -> float:
    """Проверить вероятность и вернуть её как ``float``."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label.capitalize()} должна быть числом, получено {value!r}.")
    probability = float(value)
    if not 0.0 <= probability <= ABSOLUTE_MAX_PROBABILITY:
        raise ValueError(
            f"{label.capitalize()} должна быть в диапазоне от 0 до "
            f"{ABSOLUTE_MAX_PROBABILITY:g}, получено {probability:g}."
        )
    return probability


# Описания каналов для интерфейса и документации.
CHANNEL_INFO: Dict[str, Dict[str, str]] = {
    "bit_flip": {
        "name": "Bit-flip (X)",
        "short": "Случайный переворот бита с вероятностью p.",
        "description": (
            "После вентиля к кубиту с вероятностью p применяется X. "
            "Модель имитирует потерю когерентности, приводящую к ошибке "
            "переворота бита. Для CNOT ошибка разыгрывается независимо "
            "для управляющего и целевого кубитов."
        ),
        "limitations": (
            "В реальном устройстве ошибка вентиля зависит от его типа, "
            "длительности и калибровки; здесь используется одна и та же "
            "вероятность для всех операций."
        ),
    },
    "phase_flip": {
        "name": "Phase-flip (Z)",
        "short": "Случайная фазовая ошибка с вероятностью p.",
        "description": (
            "После вентиля к кубиту с вероятностью p применяется Z. "
            "Такая ошибка не меняет вероятности в вычислительном базисе, "
            "но разрушает относительные фазы: она проявится, если после "
            "неё в схеме есть H или другой вентиль, меняющий базис."
        ),
        "limitations": (
            "Модель не описывает непрерывный фазовый дрейф и корреляции "
            "между кубитами; это бинарный (паулиевский) канал."
        ),
    },
    "readout": {
        "name": "Ошибка считывания (readout)",
        "short": "Инверсия измеренного бита с вероятностью p_readout.",
        "description": (
            "При измерении каждый бит независимо инвертируется с "
            "вероятностью p_readout. Ошибка возникает уже после "
            "измерения и не влияет на квантовое состояние до него; "
            "именно поэтому она видна даже на схеме без вентилей."
        ),
        "limitations": (
            "Реальные ошибки считывания асимметричны (например, |1⟩ "
            "считывается как |0⟩ чаще, чем наоборот) и коррелированы. "
            "Симметричная модель — учебное упрощение."
        ),
    },
}

_CHANNEL_KEYS: Tuple[str, ...] = ("bit_flip", "phase_flip", "readout")


def channel_summary(config: NoiseConfig) -> List[Dict[str, str]]:
    """Таблица описаний каналов с текущими настройками.

    Возвращает список словарей с ключами ``name``, ``status``,
    ``probability``, ``description``, ``limitations``.
    """

    rows: List[Dict[str, str]] = []
    for key in _CHANNEL_KEYS:
        info = CHANNEL_INFO[key]
        if key == "bit_flip":
            enabled = config.bit_flip_enabled
            probability = config.p_bit_flip
        elif key == "phase_flip":
            enabled = config.phase_flip_enabled
            probability = config.p_phase_flip
        else:
            enabled = config.readout_enabled
            probability = config.p_readout
        if not config.enabled:
            status = "выключено (идеальная модель)"
        elif not enabled:
            status = "канал отключён"
        elif probability == 0.0:
            status = "включён, p = 0"
        else:
            status = "активен"
        rows.append(
            {
                "name": info["name"],
                "status": status,
                "probability": f"{probability:.3f}",
                "description": info["description"],
                "limitations": info["limitations"],
            }
        )
    return rows


__all__ = [
    "NoiseConfig",
    "CHANNEL_INFO",
    "channel_summary",
    "UI_MAX_PROBABILITY",
    "ABSOLUTE_MAX_PROBABILITY",
]
