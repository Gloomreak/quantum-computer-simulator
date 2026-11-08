"""Тесты исполнения схемы и результата запуска."""

from __future__ import annotations

import unittest

import numpy as np

from src.quantum.circuit import circuit_from_operations
from src.quantum.noise import NoiseConfig
from src.quantum.simulator import (
    MODE_IDEAL,
    MODE_NOISY,
    described_state,
    ideal_state_of,
    memory_estimate,
    run_circuit,
)


class TestIdealSimulation(unittest.TestCase):
    def test_bell_state(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])
        result = run_circuit(circuit, shots=1000, seed=1)
        np.testing.assert_allclose(result.ideal_probabilities, [0.5, 0.0, 0.0, 0.5], atol=1e-12)
        self.assertEqual(result.counts["01"], 0)
        self.assertEqual(result.counts["10"], 0)

    def test_state_is_normalized(self) -> None:
        circuit = circuit_from_operations(1, [("h", 0)])
        state = ideal_state_of(circuit)
        self.assertTrue(state.is_normalized())
        self.assertAlmostEqual(state.total_probability(), 1.0, places=12)

    def test_amplitudes_match_textbook_values(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])
        state = ideal_state_of(circuit)
        expected = np.array([1, 0, 0, 1], dtype=complex) / np.sqrt(2)
        np.testing.assert_allclose(state.amplitudes, expected, atol=1e-12)

    def test_empty_circuit_measures_initial_state(self) -> None:
        circuit = circuit_from_operations(2, [])
        result = run_circuit(circuit, shots=100, seed=1)
        self.assertEqual(result.counts["00"], 100)

    def test_gate_count_and_depth(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("x", 1), ("cnot", 0, 1)])
        self.assertEqual(circuit.gate_count, 3)
        self.assertEqual(circuit.depth(), 2)

    def test_mode_is_ideal_without_noise(self) -> None:
        circuit = circuit_from_operations(1, [("h", 0)])
        result = run_circuit(circuit, shots=10, seed=0)
        self.assertEqual(result.mode, MODE_IDEAL)
        self.assertIsNone(result.noisy_counts)

    def test_mode_is_noisy_when_enabled(self) -> None:
        circuit = circuit_from_operations(1, [("h", 0)])
        result = run_circuit(
            circuit,
            shots=10,
            seed=0,
            noise=NoiseConfig(enabled=True, p_bit_flip=0.1),
        )
        self.assertEqual(result.mode, MODE_NOISY)
        self.assertIsNotNone(result.noisy_counts)

    def test_memory_estimate_positive(self) -> None:
        self.assertGreater(memory_estimate(3, shots=1000, noisy=True), 0)


class TestPartialMeasurement(unittest.TestCase):
    def test_ghz_measured_subset(self) -> None:
        # (|0000⟩ + |1111⟩)/√2, измеряем кубиты 0 и 2 -> только 00 и 11.
        circuit = circuit_from_operations(
            4,
            [("h", 0), ("cnot", 0, 1), ("cnot", 1, 2), ("cnot", 2, 3)],
            measured_qubits=[0, 2],
        )
        result = run_circuit(circuit, shots=2000, seed=5)
        self.assertEqual(result.labels, ["00", "01", "10", "11"])
        self.assertEqual(result.counts["01"], 0)
        self.assertEqual(result.counts["10"], 0)
        self.assertGreater(result.counts["00"], 0)
        np.testing.assert_allclose(result.ideal_probabilities, [0.5, 0.0, 0.0, 0.5], atol=1e-12)

    def test_measurement_of_single_qubit(self) -> None:
        circuit = circuit_from_operations(2, [("x", 1)], measured_qubits=[1])
        result = run_circuit(circuit, shots=50, seed=2)
        self.assertEqual(result.labels, ["0", "1"])
        self.assertEqual(result.counts["1"], 50)


class TestTargetProbability(unittest.TestCase):
    def test_target_probability_bell(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])
        result = run_circuit(circuit, shots=2000, seed=10)
        self.assertAlmostEqual(result.ideal_target_probability("11"), 0.5, places=12)
        self.assertAlmostEqual(result.target_probability("11"), 0.5, delta=0.05)

    def test_unknown_target_raises(self) -> None:
        circuit = circuit_from_operations(1, [("h", 0)])
        result = run_circuit(circuit, shots=10, seed=1)
        with self.assertRaises(ValueError):
            result.target_probability("2")


class TestValidation(unittest.TestCase):
    def test_invalid_circuit_raises(self) -> None:
        circuit = circuit_from_operations(2, [("cnot", 0, 0)])
        with self.assertRaises(ValueError):
            run_circuit(circuit, shots=10, seed=1)

    def test_shots_validation(self) -> None:
        circuit = circuit_from_operations(1, [("h", 0)])
        with self.assertRaises(ValueError):
            run_circuit(circuit, shots=0, seed=1)

    def test_seed_validation(self) -> None:
        circuit = circuit_from_operations(1, [("h", 0)])
        with self.assertRaises(ValueError):
            run_circuit(circuit, shots=10, seed=-3)

    def test_memory_guard(self) -> None:
        circuit = circuit_from_operations(10, [("h", 0)])
        noise = NoiseConfig(enabled=True, p_bit_flip=0.01)
        with self.assertRaises(ValueError):
            run_circuit(circuit, shots=200000, seed=1, noise=noise)


class TestReproducibility(unittest.TestCase):
    def test_noisy_run_is_reproducible(self) -> None:
        circuit = circuit_from_operations(3, [("h", 0), ("cnot", 0, 1), ("cnot", 1, 2)])
        noise = NoiseConfig(enabled=True, p_bit_flip=0.05, p_readout=0.03)
        first = run_circuit(circuit, shots=1000, seed=314, noise=noise)
        second = run_circuit(circuit, shots=1000, seed=314, noise=noise)
        self.assertEqual(first.counts, second.counts)

    def test_noisy_run_differs_for_other_seed(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])
        noise = NoiseConfig(enabled=True, p_bit_flip=0.1)
        first = run_circuit(circuit, shots=1000, seed=1, noise=noise)
        second = run_circuit(circuit, shots=1000, seed=2, noise=noise)
        self.assertNotEqual(first.counts, second.counts)


class TestDescription(unittest.TestCase):
    def test_described_state_rows(self) -> None:
        state = ideal_state_of(circuit_from_operations(1, [("h", 0)]))
        rows = described_state(state)
        self.assertEqual(len(rows), 2)
        self.assertEqual(set(rows[0]), {"Индекс", "Состояние", "Re(a)", "Im(a)", "Вероятность"})
        self.assertAlmostEqual(sum(row["Вероятность"] for row in rows), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
