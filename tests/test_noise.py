"""Тесты моделей ошибок и валидации их параметров."""

from __future__ import annotations

import unittest

from src.quantum.circuit import circuit_from_operations
from src.quantum.noise import (
    ABSOLUTE_MAX_PROBABILITY,
    CHANNEL_INFO,
    NoiseConfig,
    channel_summary,
)
from src.quantum.simulator import run_circuit

from tests.reference import ref_counts, counts_to_probabilities, total_variation

BELL = circuit_from_operations(2, [("h", 0), ("cnot", 0, 1)])


class TestNoiseConfig(unittest.TestCase):
    def test_default_is_ideal(self) -> None:
        config = NoiseConfig()
        self.assertFalse(config.enabled)
        self.assertFalse(config.is_active)
        self.assertIn("Идеальная модель", config.summary())

    def test_probability_validation(self) -> None:
        with self.assertRaises(ValueError):
            NoiseConfig(p_bit_flip=-0.01)
        with self.assertRaises(ValueError):
            NoiseConfig(p_phase_flip=1.01)
        with self.assertRaises(ValueError):
            NoiseConfig(p_readout="0.1")
        NoiseConfig(p_bit_flip=0.0, p_phase_flip=0.2, p_readout=0.5)

    def test_absolute_max_probability(self) -> None:
        self.assertEqual(ABSOLUTE_MAX_PROBABILITY, 1.0)

    def test_active_flags(self) -> None:
        config = NoiseConfig(
            enabled=True,
            bit_flip_enabled=True,
            phase_flip_enabled=False,
            readout_enabled=False,
            p_bit_flip=0.02,
            p_phase_flip=0.02,
            p_readout=0.0,
        )
        self.assertTrue(config.bit_flip_active)
        self.assertFalse(config.phase_flip_active)
        self.assertFalse(config.readout_active)
        self.assertTrue(config.gate_noise_active)
        self.assertTrue(config.is_active)
        self.assertEqual(len(config.active_channels()), 1)

    def test_zero_probability_channel_is_inactive(self) -> None:
        config = NoiseConfig(enabled=True, p_bit_flip=0.0, p_readout=0.0, p_phase_flip=0.0)
        self.assertFalse(config.is_active)
        self.assertEqual(config.active_channels(), [])

    def test_disabled_mode_ignores_channels(self) -> None:
        config = NoiseConfig(enabled=False, p_bit_flip=0.1, p_readout=0.1)
        self.assertFalse(config.is_active)

    def test_serialization_roundtrip(self) -> None:
        config = NoiseConfig(
            enabled=True,
            bit_flip_enabled=False,
            phase_flip_enabled=True,
            readout_enabled=True,
            p_bit_flip=0.05,
            p_phase_flip=0.03,
            p_readout=0.07,
        )
        restored = NoiseConfig.from_dict(config.to_dict())
        self.assertEqual(config, restored)

    def test_channel_info_complete(self) -> None:
        for key in ("bit_flip", "phase_flip", "readout"):
            self.assertIn(key, CHANNEL_INFO)
            for field in ("name", "description", "limitations"):
                self.assertTrue(CHANNEL_INFO[key][field])
        rows = channel_summary(NoiseConfig(enabled=True, p_bit_flip=0.01))
        self.assertEqual(len(rows), 3)


class TestNoiseBehaviour(unittest.TestCase):
    def test_zero_probability_matches_ideal_run(self) -> None:
        # Требование ТЗ: при p = 0 шумовая модель совпадает с идеальной.
        for circuit in (BELL, circuit_from_operations(1, [("h", 0)])):
            ideal = run_circuit(circuit, shots=500, seed=11)
            noisy = run_circuit(
                circuit,
                shots=500,
                seed=11,
                noise=NoiseConfig(
                    enabled=True,
                    bit_flip_enabled=True,
                    phase_flip_enabled=True,
                    readout_enabled=True,
                    p_bit_flip=0.0,
                    p_phase_flip=0.0,
                    p_readout=0.0,
                ),
            )
            self.assertEqual(ideal.counts, noisy.counts)

    def test_bit_flip_creates_forbidden_outcomes(self) -> None:
        ideal = run_circuit(BELL, shots=4000, seed=5)
        self.assertEqual(ideal.counts["01"], 0)
        noisy = run_circuit(
            BELL,
            shots=4000,
            seed=5,
            noise=NoiseConfig(enabled=True, bit_flip_enabled=True, phase_flip_enabled=False, readout_enabled=False, p_bit_flip=0.1),
        )
        self.assertGreater(noisy.counts["01"] + noisy.counts["10"], 0)

    def test_phase_flip_does_not_change_z_basis_for_plain_bell(self) -> None:
        # Для состояния Белла без H после места ошибки Z-ошибка не видна.
        noisy = run_circuit(
            BELL,
            shots=4000,
            seed=5,
            noise=NoiseConfig(enabled=True, bit_flip_enabled=False, phase_flip_enabled=True, readout_enabled=False, p_phase_flip=0.2),
        )
        self.assertEqual(noisy.counts["01"], 0)
        self.assertEqual(noisy.counts["10"], 0)

    def test_phase_flip_visible_in_hzh_circuit(self) -> None:
        circuit = circuit_from_operations(1, [("h", 0), ("z", 0), ("h", 0)])
        noisy = run_circuit(
            circuit,
            shots=4000,
            seed=5,
            noise=NoiseConfig(enabled=True, bit_flip_enabled=False, phase_flip_enabled=True, readout_enabled=False, p_phase_flip=0.2),
        )
        self.assertGreater(noisy.counts["0"], 0)

    def test_readout_only_affects_counts_not_ideal(self) -> None:
        circuit = circuit_from_operations(1, [("x", 0)])
        result = run_circuit(
            circuit,
            shots=3000,
            seed=8,
            noise=NoiseConfig(enabled=True, bit_flip_enabled=False, phase_flip_enabled=False, readout_enabled=True, p_readout=0.1),
        )
        self.assertEqual(result.ideal_counts["1"], 3000)
        self.assertGreater(result.counts["0"], 0)
        self.assertLess(result.counts["1"] / 3000, 0.95)

    def test_noise_statistics_match_reference_trajectories(self) -> None:
        """Быстрая модель должна статистически совпадать с эталоном."""

        shots = 6000
        config = NoiseConfig(
            enabled=True,
            bit_flip_enabled=True,
            phase_flip_enabled=True,
            readout_enabled=True,
            p_bit_flip=0.05,
            p_phase_flip=0.03,
            p_readout=0.04,
        )
        fast = run_circuit(BELL, shots=shots, seed=4242, noise=config)
        slow_counts = ref_counts(BELL, config, shots=shots, seed=4242)
        probabilities_fast = fast.probabilities_for("noisy")
        probabilities_slow = counts_to_probabilities(slow_counts, fast.labels)
        distance = total_variation(probabilities_fast, probabilities_slow)
        self.assertLess(
            distance,
            0.06,
            f"Расхождение с эталоном слишком велико: TVD = {distance:.4f}",
        )

    def test_noise_grows_with_probability(self) -> None:
        distances = []
        for probability in (0.0, 0.05, 0.15):
            result = run_circuit(
                BELL,
                shots=3000,
                seed=33,
                noise=NoiseConfig(enabled=True, bit_flip_enabled=True, phase_flip_enabled=False, readout_enabled=False, p_bit_flip=probability),
            )
            from src.experiments.metrics import metrics_for_result

            distances.append(metrics_for_result(result).tvd_ideal_vs_observed)
        self.assertLess(distances[0], distances[1])
        self.assertLess(distances[1], distances[2])


if __name__ == "__main__":
    unittest.main()
