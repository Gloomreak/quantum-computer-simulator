"""Экспериментальный модуль: серии запусков, метрики и экспорт."""

from .export import (
    experiment_csv_bytes,
    experiment_aggregated_dataframe,
    experiment_raw_dataframe,
    run_csv_bytes,
    run_dataframe,
    save_experiment_csv,
    save_png,
    save_run_csv,
)
from .metrics import (
    RunMetrics,
    confidence_interval_95,
    metrics_for_result,
    total_variation_distance,
)
from .runner import (
    EXPERIMENT_KINDS,
    ExperimentPoint,
    ExperimentResult,
    ExperimentSeries,
    ExperimentSpec,
    estimate_total_runs,
    experiment_kinds,
    kind_info,
    probability_grid,
    run_experiment,
)

__all__ = [
    "EXPERIMENT_KINDS",
    "ExperimentPoint",
    "ExperimentResult",
    "ExperimentSeries",
    "ExperimentSpec",
    "RunMetrics",
    "confidence_interval_95",
    "estimate_total_runs",
    "experiment_aggregated_dataframe",
    "experiment_csv_bytes",
    "experiment_kinds",
    "experiment_raw_dataframe",
    "kind_info",
    "metrics_for_result",
    "probability_grid",
    "run_csv_bytes",
    "run_dataframe",
    "run_experiment",
    "save_experiment_csv",
    "save_png",
    "save_run_csv",
    "total_variation_distance",
]
