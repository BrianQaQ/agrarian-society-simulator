import math
import tempfile
import unittest
from pathlib import Path

from simulation import AgrarianSimulation, Institution, Strategy, gini


class BottomUpModelTests(unittest.TestCase):
    def test_gini(self):
        self.assertEqual(gini([1, 1, 1]), 0.0)
        self.assertAlmostEqual(gini([0, 0, 3]), 2 / 3)

    def test_land_is_strictly_conserved_in_both_modes(self):
        for mode in ("fixed", "evolution"):
            sim = AgrarianSimulation(households=160, seed=11, mode=mode, max_households=900)
            initial = sum(h.land for h in sim.households)
            sim.step(300)
            self.assertAlmostEqual(initial, sum(h.land for h in sim.households), places=6)

    def test_fixed_mode_does_not_change_strategy(self):
        strategy = Strategy(fertility=.04, reserve_years=1.25, acquisition=.31)
        sim = AgrarianSimulation(households=100, seed=3, mode="fixed", fixed_strategy=strategy)
        sim.step(100)
        for h in sim.households:
            self.assertEqual(h.strategy, strategy)

    def test_evolution_is_seeded_and_changes_population_strategy(self):
        a = AgrarianSimulation(households=120, seed=23, mode="evolution")
        b = AgrarianSimulation(households=120, seed=23, mode="evolution")
        initial = a.strategy_metrics()
        a.step(150)
        b.step(150)
        self.assertEqual(a.history, b.history)
        self.assertNotEqual(initial["fertility"], a.strategy_metrics()["fertility"])

    def test_inheritance_is_binary_and_population_shares_sum_to_one(self):
        sim = AgrarianSimulation(households=120, seed=7, mode="evolution")
        sim.step(75)
        m = sim.metrics()
        self.assertAlmostEqual(m["equal_inheritance"] + m["primogeniture"], 1.0)
        self.assertTrue(all(isinstance(h.strategy.equal_inheritance, bool) for h in sim.households))

    def test_default_evolution_can_complete_a_cycle_within_400_years(self):
        sim = AgrarianSimulation(households=600, seed=7, mode="evolution")
        sim.step(400)
        self.assertGreaterEqual(sim.cycles, 1)

    def test_forced_uprising_redistributes_without_creating_land(self):
        institution = Institution(uprising_threshold=0.0, redistribution_share=.8)
        sim = AgrarianSimulation(households=120, seed=9, institution=institution)
        land = sum(h.land for h in sim.households)
        sim.step(1)
        self.assertGreaterEqual(sim.cycles, 1)
        self.assertAlmostEqual(land, sum(h.land for h in sim.households), places=7)

    def test_metrics_are_finite(self):
        sim = AgrarianSimulation(households=180, seed=5, mode="evolution")
        sim.step(250)
        for key, value in sim.metrics().items():
            if isinstance(value, (int, float)):
                self.assertTrue(math.isfinite(value), key)

    def test_csv(self):
        sim = AgrarianSimulation(households=40, seed=2)
        sim.step(3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            sim.export_csv(path)
            self.assertEqual(len(path.read_text(encoding="utf-8-sig").splitlines()), 5)


if __name__ == "__main__":
    unittest.main()
