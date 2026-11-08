"""Тесты измерения: вероятности, sampling, ошибки считывания."""

from __future__ import annotations

import unittest

import numpy as np

from src.quantum.circuit import circuit_from_operations
from src.quantum.measurement import (
    apply_readout_error,
    counts_from_outcomes,
    make_generators,
    normalize_probabilities,
    probabilities_from_counts,
    sample_outcomes,
    validate_seed,
    validate_shots,
)
from src.quantum.simulator import run_circuit
from src.quantum.statevector import QuantumState

from tests.reference import total_variation


class TestProbabilities(unittest.TestCase):
    def test_probabilities_sum_to_one(self) -> None:
        state = QuantumState.zero(3).apply("h", 0).apply("cnot", 1, control=0)
        self.assertAlmostEqual(state.total_probability(), 1.0, places=12)
        self.assertTrue(state.is_normalized())

    def test_probability_is_squared_amplitude(self) -> None:
        state = QuantumState.zero(1).apply("h", 0)
        for amplitude, probability in zip(state.amplitudes, state.probabilities):
            self.assertAlmostEqual(abs(amplitude) ** 2, probability, places=12)

    def test_normalize_rejects_negative(self) -> None:
        with self.assertRaises(ValueError):
            normalize_probabilities(np.array([1.2, -0.2]))

    def test_normalize_rejects_zero_sum(self) -> None:
        with self.assertRaises(ValueError):
            normalize_probabilities(np.array([0.0, 0.0]))


class TestSampling(unittest.TestCase):
    def test_sampling_follows_theory(self) -> None:
        probabilities = np.array([0.5, 0.5])
        generator = np.random.default_rng(1234)
        outcomes = sample_outcomes(probabilities, 20000, generator)
        counts = counts_from_outcomes(outcomes, 1)
        self.assertLess(abs(counts["0"] / 20000 - 0.5), 0.02)
        self.assertLess(abs(counts["1"] / 20000 - 0.5), 0.02)

    def test_sampling_of_nonuniform_distribution(self) -> None:
        probabilities = np.array([0.4, 0.3, 0.2, 0.1])
        generator = np.random.default_rng(7)
        outcomes = sample_outcomes(probabilities, 30000, generator)
        counts = counts_from_outcomes(outcomes, 2)
        observed = probabilities_from_counts(counts, ["00", "01", "10", "11"])
        self.assertLess(total_variation(probabilities, observed), 0.02)

    def test_deterministic_state_gives_single_outcome(self) -> None:
        circuit = circuit_from_operations(2, [("x", 0), ("x", 1)])
        result = run_circuit(circuit, shots=500, seed=5)
        self.assertEqual(result.counts["11"], 500)
        self.assertEqual(sum(result.counts.values()), 500)

    def test_same_seed_reproduces_counts(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])
        first = run_circuit(circuit, shots=777, seed=99)
        second = run_circuit(circuit, shots=777, seed=99)
        self.assertEqual(first.counts, second.counts)

    def test_different_seed_changes_counts(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])
        first = run_circuit(circuit, shots=777, seed=1)
        second = run_circuit(circuit, shots=777, seed=2)
        self.assertNotEqual(first.counts, second.counts)

    def test_bell_state_only_correlated_outcomes(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])
        result = run_circuit(circuit, shots=5000, seed=3)
        self.assertEqual(result.counts["01"], 0)
        self.assertEqual(result.counts["10"], 0)
        self.assertLess(abs(result.counts["00"] / 5000 - 0.5), 0.05)

    def test_shots_validation(self) -> None:
        for value in (0, -5, 10**9, 1.5, "100"):
            with self.assertRaises(ValueError):
                validate_shots(value)
        self.assertEqual(validate_shots(1024), 1024)

    def test_seed_validation(self) -> None:
        for value in (-1, 2**32, "seed", 1.5):
            with self.assertRaises(ValueError):
                validate_seed(value)
        self.assertEqual(validate_seed(0), 0)


class TestCounts(unittest.TestCase):
    def test_counts_sum_to_shots(self) -> None:
        outcomes = np.array([0, 0, 1, 2, 3, 3])
        counts = counts_from_outcomes(outcomes, 2)
        self.assertEqual(counts, {"00": 2, "01": 1, "10": 1, "11": 2})

    def test_probabilities_from_counts(self) -> None:
        probabilities = probabilities_from_counts({"00": 1, "01": 3}, ["00", "01", "10"])
        np.testing.assert_allclose(probabilities, [0.25, 0.75, 0.0])

    def test_out_of_range_outcome_raises(self) -> None:
        with self.assertRaises(ValueError):
            counts_from_outcomes(np.array([0, 4]), 2)


class TestReadoutError(unittest.TestCase):
    def test_zero_probability_keeps_outcomes(self) -> None:
        outcomes = np.array([0, 1, 0, 1])
        generator = np.random.default_rng(1)
        result = apply_readout_error(outcomes, 1, 0.0, generator)
        np.testing.assert_array_equal(result, outcomes)

    def test_full_probability_inverts_all_bits(self) -> None:
        outcomes = np.array([0, 0, 1, 1])
        generator = np.random.default_rng(1)
        result = apply_readout_error(outcomes, 1, 1.0, generator)
        np.testing.assert_array_equal(result, [1, 1, 0, 0])

    def test_half_probability_on_zero_state(self) -> None:
        # Требование ТЗ: при p = 0,5 для |0⟩ результаты близки к равномерным.
        circuit = circuit_from_operations(1, [])
        from src.quantum.noise import NoiseConfig

        noise = NoiseConfig(
            enabled=True,
            bit_flip_enabled=False,
            phase_flip_enabled=False,
            readout_enabled=True,
            p_readout=0.5,
        )
        result = run_circuit(circuit, shots=20000, seed=17, noise=noise)
        self.assertLess(abs(result.counts["0"] / 20000 - 0.5), 0.02)
        self.assertLess(abs(result.counts["1"] / 20000 - 0.5), 0.02)

    def test_independent_generators(self) -> None:
        first = make_generators(42)
        second = make_generators(42)
        for key in ("state", "noise", "readout"):
            np.testing.assert_allclose(
                first[key].random(10), second[key].random(10), atol=0.0
            )

    def test_readout_probability_validation(self) -> None:
        from src.quantum.noise import NoiseConfig

        with self.assertRaises(ValueError):
            NoiseConfig(enabled=True, p_readout=1.5)


if __name__ == "__main__":
    unittest.main()
