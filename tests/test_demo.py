"""Тесты демонстрационных схем из examples/demo_circuits.json."""

from __future__ import annotations

import unittest

from src.demo import demo_by_key, demo_circuit, demo_names, load_demo_circuits
from src.quantum.simulator import run_circuit


class TestDemoCircuits(unittest.TestCase):
    def test_file_loads(self) -> None:
        demos = load_demo_circuits()
        self.assertGreaterEqual(len(demos), 3)

    def test_keys_unique(self) -> None:
        keys = [demo.key for demo in load_demo_circuits()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_required_scenarios_present(self) -> None:
        keys = {demo.key for demo in load_demo_circuits()}
        self.assertIn("one_qubit_h", keys)
        self.assertIn("bit_flip", keys)
        self.assertIn("bell", keys)

    def test_all_demos_are_valid_and_runnable(self) -> None:
        for demo in load_demo_circuits():
            with self.subTest(demo=demo.key):
                self.assertTrue(demo.circuit.is_valid(), demo.key)
                result = run_circuit(demo.circuit, shots=50, seed=1)
                self.assertEqual(sum(result.counts.values()), 50)

    def test_bell_demo_distribution(self) -> None:
        circuit = demo_circuit("bell")
        result = run_circuit(circuit, shots=4000, seed=1)
        self.assertEqual(result.counts["00"] + result.counts["11"], 4000)

    def test_ghz_demo(self) -> None:
        circuit = demo_circuit("ghz3")
        result = run_circuit(circuit, shots=2000, seed=1)
        self.assertEqual(result.counts["000"] + result.counts["111"], 2000)

    def test_demo_names_not_empty(self) -> None:
        names = demo_names()
        self.assertTrue(all(name.strip() for name in names))

    def test_missing_demo_raises(self) -> None:
        with self.assertRaises(KeyError):
            demo_by_key("does_not_exist")


if __name__ == "__main__":
    unittest.main()
