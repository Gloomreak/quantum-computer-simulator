"""Тесты схемы: проверка корректности, изменение и сериализация."""

from __future__ import annotations

import unittest

from src.quantum.circuit import (
    Circuit,
    Operation,
    circuit_from_operations,
)


class TestOperation(unittest.TestCase):
    def test_single_qubit_operation(self) -> None:
        operation = Operation(gate="h", target=2)
        self.assertEqual(operation.involved_qubits(), (2,))
        self.assertEqual(operation.symbol, "H")
        self.assertIn("q2", operation.describe())

    def test_cnot_operation(self) -> None:
        operation = Operation(gate="cnot", target=1, control=0)
        self.assertEqual(operation.involved_qubits(), (0, 1))
        self.assertEqual(operation.describe(), "CNOT: управляющий q0 → целевой q1")

    def test_unknown_gate_raises(self) -> None:
        with self.assertRaises(ValueError):
            Operation(gate="swap", target=0)

    def test_cnot_without_control_raises(self) -> None:
        with self.assertRaises(ValueError):
            Operation(gate="cnot", target=0)

    def test_control_on_single_qubit_gate_raises(self) -> None:
        with self.assertRaises(ValueError):
            Operation(gate="x", target=0, control=1)

    def test_non_integer_target_raises(self) -> None:
        with self.assertRaises(ValueError):
            Operation(gate="x", target="zero")


class TestCircuitValidation(unittest.TestCase):
    def test_valid_circuit(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])
        self.assertTrue(circuit.is_valid())
        self.assertEqual(circuit.errors(), [])

    def test_cnot_same_qubits_is_error(self) -> None:
        circuit = circuit_from_operations(2, [("cnot", 1, 1)])
        errors = circuit.errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, "cnot_same_qubits")
        with self.assertRaises(ValueError):
            circuit.validate_or_raise()

    def test_qubit_out_of_range_is_error(self) -> None:
        circuit = Circuit(n_qubits=2, operations=[Operation(gate="x", target=5)])
        errors = circuit.errors()
        self.assertTrue(any(issue.code == "qubit_range" for issue in errors))

    def test_empty_circuit_is_warning(self) -> None:
        circuit = Circuit(n_qubits=1, operations=[])
        self.assertTrue(circuit.is_valid())
        self.assertEqual(len(circuit.warnings()), 1)
        self.assertEqual(circuit.warnings()[0].code, "empty_circuit")

    def test_no_measured_qubits_is_error(self) -> None:
        circuit = Circuit(n_qubits=2, operations=[], measured_qubits=[])
        self.assertFalse(circuit.is_valid())
        self.assertTrue(any(issue.code == "measurement_empty" for issue in circuit.errors()))

    def test_duplicate_measurement_is_error(self) -> None:
        circuit = Circuit(n_qubits=2, operations=[], measured_qubits=[0, 0])
        # Дубликаты отфильтровываются конструктором только по порядку,
        # поэтому проверяем итоговый список.
        errors = circuit.errors()
        self.assertTrue(any(issue.code in {"measurement_duplicate"} for issue in errors))

    def test_measured_qubits_sorted(self) -> None:
        circuit = Circuit(n_qubits=3, operations=[], measured_qubits=[2, 0])
        self.assertEqual(circuit.measured, [0, 2])


class TestCircuitEditing(unittest.TestCase):
    def setUp(self) -> None:
        self.circuit = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1), ("x", 1)])

    def test_add_and_remove(self) -> None:
        self.circuit.add_gate("z", 0)
        self.assertEqual(self.circuit.gate_count, 4)
        removed = self.circuit.remove(0)
        self.assertEqual(removed.gate, "h")
        self.assertEqual(self.circuit.gate_count, 3)

    def test_move_operation(self) -> None:
        moved = self.circuit.move(0, 1)
        self.assertEqual(moved, 1)
        self.assertEqual(self.circuit.operations[0].gate, "cnot")
        self.assertEqual(self.circuit.operations[1].gate, "h")

    def test_move_out_of_range_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.circuit.move(0, -1)
        with self.assertRaises(ValueError):
            self.circuit.move(2, 1)

    def test_remove_invalid_index_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.circuit.remove(10)

    def test_clear(self) -> None:
        self.circuit.clear()
        self.assertTrue(self.circuit.is_empty)
        self.assertEqual(self.circuit.depth(), 0)

    def test_layers(self) -> None:
        circuit = circuit_from_operations(2, [("h", 0), ("x", 1), ("cnot", 0, 1)])
        self.assertEqual(circuit.layers(), [1, 1, 2])

    def test_copy_independent(self) -> None:
        clone = self.circuit.copy()
        clone.add_gate("x", 0)
        self.assertEqual(self.circuit.gate_count, 3)
        self.assertEqual(clone.gate_count, 4)


class TestSerialization(unittest.TestCase):
    def test_json_roundtrip(self) -> None:
        circuit = circuit_from_operations(
            3,
            [("h", 0), ("cnot", 0, 1), ("z", 2)],
            measured_qubits=[0, 1],
            name="Тест",
        )
        restored = Circuit.from_json(circuit.to_json())
        self.assertEqual(restored.to_dict(), circuit.to_dict())
        self.assertEqual(restored.name, "Тест")

    def test_serialization_contains_required_fields(self) -> None:
        circuit = circuit_from_operations(2, [("cnot", 0, 1)])
        data = circuit.to_dict()
        self.assertEqual(data["n_qubits"], 2)
        self.assertEqual(data["operations"][0]["control"], 0)
        self.assertEqual(data["format_version"], 1)

    def test_invalid_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            Circuit.from_json("{not json}")

    def test_missing_n_qubits_raises(self) -> None:
        with self.assertRaises(ValueError):
            Circuit.from_dict({"operations": []})

    def test_operations_must_be_list(self) -> None:
        with self.assertRaises(ValueError):
            Circuit.from_dict({"n_qubits": 2, "operations": "h"})

    def test_invalid_circuit_in_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            Circuit.from_dict(
                {
                    "n_qubits": 2,
                    "operations": [{"gate": "cnot", "target": 0, "control": 0}],
                    "measured_qubits": [0, 1],
                }
            )


if __name__ == "__main__":
    unittest.main()
