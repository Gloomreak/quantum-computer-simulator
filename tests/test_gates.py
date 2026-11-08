"""Тесты вентилей: X, H, Z, CNOT и применение к произвольным кубитам."""

from __future__ import annotations

import unittest

import numpy as np

from src.quantum.circuit import circuit_from_operations
from src.quantum.gates import CNOT_MATRIX, H_MATRIX, X_MATRIX, Z_MATRIX, get_gate
from src.quantum.statevector import (
    QuantumState,
    apply_gate,
    apply_gate_to_array,
    basis_labels,
    zero_state,
)
from tests.reference import ref_apply, ref_probabilities, ref_state_vector


def probabilities_of(state: QuantumState) -> np.ndarray:
    return state.probabilities


class TestSingleQubitGates(unittest.TestCase):
    def test_x_flips_zero_to_one(self) -> None:
        state = QuantumState.zero(1).apply("x", 0)
        np.testing.assert_allclose(state.amplitudes, [0, 1], atol=1e-12)
        self.assertAlmostEqual(state.probabilities[1], 1.0, places=12)

    def test_x_twice_returns_zero(self) -> None:
        state = QuantumState.zero(1).apply("x", 0).apply("x", 0)
        np.testing.assert_allclose(state.amplitudes, [1, 0], atol=1e-12)

    def test_hadamard_creates_uniform_superposition(self) -> None:
        state = QuantumState.zero(1).apply("h", 0)
        probabilities = probabilities_of(state)
        self.assertAlmostEqual(probabilities[0], 0.5, places=12)
        self.assertAlmostEqual(probabilities[1], 0.5, places=12)
        expected = np.array([1, 1]) / np.sqrt(2)
        np.testing.assert_allclose(state.amplitudes, expected, atol=1e-12)

    def test_hadamard_twice_returns_zero(self) -> None:
        state = QuantumState.zero(1).apply("h", 0).apply("h", 0)
        np.testing.assert_allclose(np.abs(state.amplitudes), [1, 0], atol=1e-12)

    def test_z_preserves_probabilities(self) -> None:
        state = QuantumState.zero(1).apply("h", 0)
        before = state.probabilities.copy()
        state.apply("z", 0)
        np.testing.assert_allclose(state.probabilities, before, atol=1e-12)

    def test_z_flips_sign_of_one_amplitude(self) -> None:
        state = QuantumState.zero(1).apply("x", 0).apply("z", 0)
        np.testing.assert_allclose(state.amplitudes, [0, -1], atol=1e-12)

    def test_z_turns_plus_into_minus(self) -> None:
        state = QuantumState.zero(1).apply("h", 0).apply("z", 0)
        expected = np.array([1, -1]) / np.sqrt(2)
        np.testing.assert_allclose(state.amplitudes, expected, atol=1e-12)

    def test_applying_gate_to_second_qubit(self) -> None:
        # X на q1 переводит |00⟩ в |01⟩, то есть индекс 1.
        state = QuantumState.zero(2).apply("x", 1)
        self.assertEqual(int(np.argmax(state.probabilities)), 1)
        self.assertEqual(state.label(1), "01")

    def test_gate_on_first_qubit_uses_leftmost_bit(self) -> None:
        state = QuantumState.zero(2).apply("x", 0)
        self.assertEqual(int(np.argmax(state.probabilities)), 2)
        self.assertEqual(state.label(2), "10")


class TestCnot(unittest.TestCase):
    def test_cnot_flips_target_when_control_is_one(self) -> None:
        state = QuantumState.zero(2).apply("x", 0).apply("cnot", 1, control=0)
        np.testing.assert_allclose(state.probabilities, [0, 0, 0, 1], atol=1e-12)

    def test_cnot_does_nothing_when_control_is_zero(self) -> None:
        state = QuantumState.zero(2).apply("cnot", 1, control=0)
        np.testing.assert_allclose(state.probabilities, [1, 0, 0, 0], atol=1e-12)

    def test_cnot_with_control_greater_than_target(self) -> None:
        # |q0=0, q1=1⟩ -> управляющий q1 = 1 -> инвертируем q0 -> |11⟩
        state = QuantumState.zero(2).apply("x", 1).apply("cnot", 0, control=1)
        self.assertEqual(int(np.argmax(state.probabilities)), 3)

    def test_cnot_same_qubits_raises(self) -> None:
        with self.assertRaises(ValueError):
            QuantumState.zero(2).apply("cnot", 0, control=0)

    def test_cnot_matrix_is_unitary(self) -> None:
        product = CNOT_MATRIX @ CNOT_MATRIX.conj().T
        np.testing.assert_allclose(product, np.eye(4), atol=1e-12)


class TestGateMatrices(unittest.TestCase):
    def test_matrices_are_unitary(self) -> None:
        for matrix in (X_MATRIX, H_MATRIX, Z_MATRIX):
            product = matrix @ matrix.conj().T
            np.testing.assert_allclose(product, np.eye(2), atol=1e-12)

    def test_unknown_gate_raises(self) -> None:
        with self.assertRaises(KeyError):
            get_gate("qft")

    def test_two_qubit_flag(self) -> None:
        self.assertTrue(get_gate("cnot").num_qubits == 2)
        self.assertTrue(get_gate("h").num_qubits == 1)


class TestValidation(unittest.TestCase):
    def test_negative_qubit_index_raises(self) -> None:
        with self.assertRaises(ValueError):
            QuantumState.zero(2).apply("x", -1)

    def test_out_of_range_qubit_index_raises(self) -> None:
        with self.assertRaises(ValueError):
            QuantumState.zero(2).apply("x", 2)

    def test_invalid_number_of_qubits_raises(self) -> None:
        with self.assertRaises(ValueError):
            QuantumState.zero(0)
        with self.assertRaises(ValueError):
            QuantumState.zero(11)

    def test_state_length_must_match_qubit_count(self) -> None:
        with self.assertRaises(ValueError):
            QuantumState(2, np.zeros(3, dtype=complex))

    def test_basis_labels_order(self) -> None:
        self.assertEqual(basis_labels(2), ["00", "01", "10", "11"])


class TestAgainstReferenceImplementation(unittest.TestCase):
    """Сравнение быстрой реализации с независимым перебором индексов."""

    def test_random_circuits_match_reference(self) -> None:
        rng = np.random.default_rng(20240607)
        for _ in range(10):
            n_qubits = int(rng.integers(1, 5))
            operations = []
            for _ in range(int(rng.integers(1, 12))):
                if n_qubits >= 2 and rng.random() < 0.4:
                    control, target = rng.choice(n_qubits, size=2, replace=False)
                    operations.append(("cnot", int(control), int(target)))
                else:
                    gate = ["x", "h", "z"][int(rng.integers(0, 3))]
                    operations.append((gate, int(rng.integers(0, n_qubits))))
            circuit = circuit_from_operations(n_qubits, operations)
            expected = ref_state_vector(circuit)
            actual = zero_state(n_qubits)
            for operation in circuit.operations:
                actual = apply_gate(
                    actual,
                    n_qubits,
                    operation.gate,
                    operation.target,
                    operation.control,
                )
            np.testing.assert_allclose(actual, expected, atol=1e-10)
            np.testing.assert_allclose(
                np.abs(actual) ** 2, ref_probabilities(circuit), atol=1e-10
            )

    def test_batch_gate_application_matches_single_state(self) -> None:
        n_qubits = 3
        single = zero_state(n_qubits)
        batch = np.tile(single, (5, 1))
        for gate, target, control in (
            ("h", 1, None),
            ("cnot", 2, 0),
            ("x", 0, None),
            ("cnot", 0, 2),
            ("z", 2, None),
        ):
            batch = apply_gate_to_array(batch, n_qubits, gate, target, control)
            single = apply_gate_to_array(single, n_qubits, gate, target, control)
            for row in range(batch.shape[0]):
                np.testing.assert_allclose(batch[row], single, atol=1e-12)

    def test_reference_apply_matches_state_for_each_gate(self) -> None:
        n_qubits = 2
        initial = np.array([1, 0, 0, 0], dtype=complex)
        for gate, target, control in (
            ("x", 0, None),
            ("h", 1, None),
            ("z", 0, None),
            ("cnot", 1, 0),
            ("cnot", 0, 1),
        ):
            fast = apply_gate(initial, n_qubits, gate, target, control)
            slow = ref_apply(initial, n_qubits, gate, target, control)
            np.testing.assert_allclose(fast, slow, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
