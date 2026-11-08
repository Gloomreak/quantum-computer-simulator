"""Тесты метрик, серий экспериментов и экспорта."""

from __future__ import annotations

import csv
import io
import unittest

import numpy as np

from src.experiments.export import (
    experiment_aggregated_dataframe,
    experiment_csv_bytes,
    experiment_raw_dataframe,
    run_csv_bytes,
    run_dataframe,
)
from src.experiments.metrics import (
    confidence_interval_95,
    metrics_for_result,
    total_variation_distance,
)
from src.experiments.runner import (
    CHANNEL_BIT_FLIP,
    CHANNEL_PHASE_FLIP,
    CHANNEL_READOUT,
    ExperimentSpec,
    circuit_with_depth,
    derive_seed,
    depth_values,
    estimate_total_runs,
    experiment_kinds,
    probability_grid,
    run_experiment,
)
from src.quantum.circuit import circuit_from_operations
from src.quantum.noise import NoiseConfig
from src.quantum.simulator import run_circuit

BELL = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)], name="Белл")


class TestMetrics(unittest.TestCase):
    def test_tvd_identical_distributions(self) -> None:
        self.assertEqual(total_variation_distance([0.5, 0.5], [0.5, 0.5]), 0.0)

    def test_tvd_orthogonal_distributions(self) -> None:
        self.assertAlmostEqual(total_variation_distance([1, 0], [0, 1]), 1.0)

    def test_tvd_known_value(self) -> None:
        self.assertAlmostEqual(
            total_variation_distance([0.7, 0.3], [0.5, 0.5]), 0.2, places=12
        )

    def test_tvd_symmetry(self) -> None:
        first = total_variation_distance([0.6, 0.4], [0.2, 0.8])
        second = total_variation_distance([0.2, 0.8], [0.6, 0.4])
        self.assertAlmostEqual(first, second, places=12)

    def test_tvd_rejects_bad_input(self) -> None:
        with self.assertRaises(ValueError):
            total_variation_distance([0.5, 0.5], [0.5])
        with self.assertRaises(ValueError):
            total_variation_distance([0.5, 0.6], [0.5, 0.5])

    def test_confidence_interval(self) -> None:
        mean, low, high = confidence_interval_95([1.0, 1.0, 1.0])
        self.assertAlmostEqual(mean, 1.0)
        self.assertAlmostEqual(low, 1.0)
        self.assertAlmostEqual(high, 1.0)

    def test_metrics_for_result(self) -> None:
        noise = NoiseConfig(enabled=True, p_bit_flip=0.1)
        result = run_circuit(BELL, shots=2000, seed=5, noise=noise)
        metrics = metrics_for_result(result, target="11")
        self.assertEqual(metrics.mode, "noisy")
        self.assertGreater(metrics.tvd_ideal_vs_observed, 0.0)
        self.assertGreaterEqual(metrics.tvd_noise_floor, 0.0)
        self.assertAlmostEqual(metrics.target_probability_ideal, 0.5, places=12)
        self.assertIsNotNone(metrics.success_rate)

    def test_metrics_unknown_target(self) -> None:
        result = run_circuit(BELL, shots=100, seed=5)
        with self.assertRaises(ValueError):
            metrics_for_result(result, target="101")


class TestGrids(unittest.TestCase):
    def test_probability_grid(self) -> None:
        values = probability_grid(0.0, 0.2, 0.01)
        self.assertEqual(len(values), 21)
        self.assertAlmostEqual(values[0], 0.0)
        self.assertAlmostEqual(values[-1], 0.2)

    def test_probability_grid_invalid(self) -> None:
        with self.assertRaises(ValueError):
            probability_grid(0.2, 0.0, 0.01)
        with self.assertRaises(ValueError):
            probability_grid(0.0, 0.2, 0.0)
        with self.assertRaises(ValueError):
            probability_grid(0.0, 1.0, 0.001)

    def test_depth_values(self) -> None:
        values = depth_values(2, 10)
        self.assertEqual(values, (2, 4, 6, 8, 10))

    def test_circuit_with_depth_keeps_ideal_result(self) -> None:
        deeper = circuit_with_depth(BELL, 10)
        self.assertEqual(deeper.gate_count, 10)
        ideal_base = run_circuit(BELL, shots=100, seed=1)
        ideal_deep = run_circuit(deeper, shots=100, seed=1)
        np.testing.assert_allclose(
            ideal_base.ideal_probabilities, ideal_deep.ideal_probabilities, atol=1e-12
        )

    def test_derive_seed_is_deterministic(self) -> None:
        self.assertEqual(derive_seed(10, 0), derive_seed(10, 0))
        self.assertNotEqual(derive_seed(10, 0), derive_seed(10, 1))
        self.assertLess(derive_seed(10, 49), 2**32)

    def test_estimate_total_runs(self) -> None:
        spec = ExperimentSpec(
            kind="bitflip",
            circuit=BELL,
            values=probability_grid(0.0, 0.1, 0.05),
            shots=100,
            repeats=2,
        )
        self.assertEqual(estimate_total_runs(spec), 3 * 2)

    def test_kinds_registered(self) -> None:
        keys = {info.key for info in experiment_kinds()}
        self.assertEqual(
            keys,
            {"bitflip", "phaseflip", "readout", "depth", "compare", "shots"},
        )


class TestExperimentSpecValidation(unittest.TestCase):
    def test_repeats_validation(self) -> None:
        spec = ExperimentSpec(kind="bitflip", circuit=BELL, values=(0.0,), repeats=0)
        with self.assertRaises(ValueError):
            spec.validate()
        spec = ExperimentSpec(kind="bitflip", circuit=BELL, values=(0.0,), repeats=51)
        with self.assertRaises(ValueError):
            spec.validate()

    def test_empty_values(self) -> None:
        spec = ExperimentSpec(kind="bitflip", circuit=BELL, values=())
        with self.assertRaises(ValueError):
            spec.validate()

    def test_bad_target(self) -> None:
        spec = ExperimentSpec(
            kind="bitflip", circuit=BELL, values=(0.0,), target="101"
        )
        with self.assertRaises(ValueError):
            spec.validate()

    def test_depth_requires_two_qubits(self) -> None:
        circuit = circuit_from_operations(1, [("h", 0)])
        spec = ExperimentSpec(kind="depth", circuit=circuit, max_operations=6)
        with self.assertRaises(ValueError):
            spec.validate()


class TestRunExperiment(unittest.TestCase):
    def test_bitflip_experiment_runs_and_grows(self) -> None:
        spec = ExperimentSpec(
            kind="bitflip",
            circuit=BELL,
            shots=400,
            repeats=3,
            seed=2024,
            target="11",
            values=(0.0, 0.05, 0.15),
        )
        result = run_experiment(spec)
        self.assertEqual(len(result.series), 1)
        points = result.series[0].points
        self.assertEqual(len(points), 3)
        self.assertGreater(points[-1].mean, points[0].mean)
        self.assertTrue(all(point.repeats == 3 for point in points))
        self.assertEqual(result.total_runs, 9)
        self.assertIsNotNone(points[0].target_probability_mean)

    def test_experiment_is_reproducible(self) -> None:
        spec = ExperimentSpec(
            kind="bitflip",
            circuit=BELL,
            shots=300,
            repeats=2,
            seed=77,
            values=(0.0, 0.1),
        )
        first = run_experiment(spec)
        second = run_experiment(spec)
        for first_point, second_point in zip(first.series[0].points, second.series[0].points):
            self.assertAlmostEqual(first_point.mean, second_point.mean, places=12)

    def test_depth_experiment(self) -> None:
        spec = ExperimentSpec(
            kind="depth",
            circuit=BELL,
            shots=400,
            repeats=3,
            seed=5,
            target="11",
            max_operations=10,
            p_fixed=0.05,
        )
        result = run_experiment(spec)
        points = result.series[0].points
        self.assertEqual([point.value for point in points], [2.0, 4.0, 6.0, 8.0, 10.0])
        self.assertGreater(points[-1].mean, points[0].mean)

    def test_compare_experiment_has_three_series(self) -> None:
        spec = ExperimentSpec(
            kind="compare",
            circuit=BELL,
            shots=300,
            repeats=2,
            seed=11,
            target="11",
            values=(0.0, 0.1),
        )
        result = run_experiment(spec)
        keys = [series.key for series in result.series]
        self.assertEqual(keys, [CHANNEL_BIT_FLIP, CHANNEL_PHASE_FLIP, CHANNEL_READOUT])
        for series in result.series:
            self.assertEqual(len(series.points), 2)

    def test_shots_experiment(self) -> None:
        spec = ExperimentSpec(
            kind="shots",
            circuit=BELL,
            repeats=2,
            seed=9,
            target="11",
            shots_grid=(200, 800),
            p_fixed=0.05,
        )
        result = run_experiment(spec)
        points = result.series[0].points
        self.assertEqual([point.value for point in points], [200.0, 800.0])
        self.assertEqual(result.total_runs, 4)
        self.assertEqual(result.shots, 0)
        self.assertIn("shots:", result.params_note)

    def test_shots_experiment_requires_grid(self) -> None:
        spec = ExperimentSpec(kind="shots", circuit=BELL, repeats=1)
        with self.assertRaises(ValueError):
            spec.validate()

    def test_progress_callback_called(self) -> None:
        calls = []
        spec = ExperimentSpec(
            kind="readout",
            circuit=BELL,
            shots=100,
            repeats=1,
            values=(0.0, 0.1),
        )
        run_experiment(spec, progress=lambda done, total, message: calls.append((done, total)))
        self.assertEqual(calls[0][0], 1)
        self.assertEqual(calls[-1], (2, 2))


class TestExport(unittest.TestCase):
    def test_run_dataframe_columns(self) -> None:
        result = run_circuit(BELL, shots=100, seed=1)
        frame = run_dataframe(result)
        self.assertEqual(
            list(frame.columns),
            [
                "Битовая строка",
                "Теоретическая вероятность",
                "Идеально: число измерений",
                "Идеально: частота",
                "С шумом: число измерений",
                "С шумом: частота",
            ],
        )
        self.assertEqual(len(frame), 4)
        self.assertAlmostEqual(frame["Теоретическая вероятность"].sum(), 1.0, places=6)

    def test_run_csv_has_header_and_rows(self) -> None:
        result = run_circuit(BELL, shots=100, seed=1)
        payload = run_csv_bytes(result)
        text = payload.decode("utf-8-sig")
        self.assertTrue(text.startswith("#"))
        lines = [line for line in text.splitlines() if not line.startswith("#")]
        self.assertEqual(len(lines), 5)

    def test_experiment_csv_roundtrip(self) -> None:
        spec = ExperimentSpec(
            kind="bitflip",
            circuit=BELL,
            shots=200,
            repeats=2,
            values=(0.0, 0.1),
            target="11",
        )
        result = run_experiment(spec)
        payload = experiment_csv_bytes(result)
        text = payload.decode("utf-8-sig")
        data_lines = [line for line in text.splitlines() if not line.startswith("#")]
        reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
        rows = list(reader)
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertIn("TVD", row)
            self.assertIn("Повтор", row)
            float(row["TVD"])

    def test_experiment_aggregated_export(self) -> None:
        spec = ExperimentSpec(
            kind="bitflip",
            circuit=BELL,
            shots=200,
            repeats=2,
            values=(0.0, 0.1),
        )
        result = run_experiment(spec)
        frame = experiment_aggregated_dataframe(result)
        self.assertEqual(len(frame), 2)
        self.assertIn("Средний TVD", frame.columns)
        raw = experiment_raw_dataframe(result)
        self.assertEqual(len(raw), 4)
        self.assertTrue((raw["TVD"] >= 0).all())


if __name__ == "__main__":
    unittest.main()
