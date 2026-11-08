"""Пакет интерфейса Streamlit: по одному модулю на раздел."""

from . import (
    architecture,
    circuit_editor,
    experiments_view,
    help_view,
    noise_view,
    run_view,
)

__all__ = [
    "architecture",
    "circuit_editor",
    "experiments_view",
    "help_view",
    "noise_view",
    "run_view",
]
