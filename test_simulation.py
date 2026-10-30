import math
import tempfile
import unittest
from pathlib import Path

from simulation import AgrarianSimulation, Household, Institution, Strategy, gini


def total_land(sim):
    return sum(h.land for h in sim.households) + sim.state_land


class BottomUpModelTests(unittest.TestCase):
    def test_gini(self):
        self.assertEqual(gini([1, 1, 1]), 0.0)
        self.assertAlmostEqual(gini([0, 0, 3]), 2 / 3)

    def test_land_is_strictly_conserved_in_both_modes(self):
        for mode in ("fixed", "evolution"):
            sim = AgrarianSimulation(households=160, seed=11, mode=mode, max_households=900)
            initial = total_land(sim)
            sim.step(300)
            self.assertAlmostEqual(initial, total_land(sim), places=6)

    def test_debts_always_match_credits(self):
        sim = AgrarianSimulation(households=200, seed=4)
        for _ in range(250):
            sim.step(1)
            debts = sum(h.debt for h in sim.households)
            credits = sum(h.credit for h in sim.households)
            self.assertAlmostEqual(debts, credits, delta=1e-6 * max(1.0, debts))

    def test_fixed_mode_does_not_change_strategy(self):
        strategy = Strategy(fertility=.035, reserve_years=1.25, acquisition=.31)
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

    def test_equal_inheritance_still_concentrates_land_and_ends_a_dynasty(self):
        sim = AgrarianSimulation(households=600, seed=7)
        start_gini = sim.metrics()["land_gini"]
        peak_gini = start_gini
        while sim.cycles == 0 and sim.year < 400:
            sim.step(1)
            peak_gini = max(peak_gini, float(sim.metrics()["land_gini"]))
        self.assertGreaterEqual(sim.cycles, 1)
        self.assertGreater(peak_gini, start_gini + 0.2)

    def test_foreclosure_passes_land_to_creditors(self):
        sim = AgrarianSimulation(households=2, seed=1)
        debtor, creditor = sim.households
        debtor.land, creditor.land = 10.0, 10.0
        debtor.grain = creditor.grain = 0.0
        sim.land_price = 5.0
        debtor.debt = creditor.credit = 80.0   # 80 * 1.4 interest > 10 亩 * 5
        sim._settle_debts()
        self.assertEqual(debtor.land, 0.0)
        self.assertEqual(debtor.debt, 0.0)
        self.assertAlmostEqual(creditor.land, 20.0)
        self.assertAlmostEqual(sim.last_transferred_land, 10.0)

    def test_tax_evasion_shifts_burden_to_registered_land(self):
        honest = AgrarianSimulation(households=300, seed=5, institution=Institution(evasion_rate=0.0))
        evasive = AgrarianSimulation(households=300, seed=5, institution=Institution(evasion_rate=0.05))
        honest.step(60)
        evasive.step(60)
        self.assertEqual(honest.metrics()["hidden_land"], 0.0)
        self.assertGreater(evasive.metrics()["hidden_land"], 0.05)
        self.assertGreater(evasive.tax_per_mu, honest.tax_per_mu)

    def test_forced_revolt_founds_new_dynasty_and_resets_registers(self):
        institution = Institution(revolt_threshold=0.0)
        sim = AgrarianSimulation(households=150, seed=9, institution=institution)
        land = total_land(sim)
        sim.step(1)
        self.assertTrue(sim.at_war)
        self.assertEqual(sim.cycles, 1)
        while sim.at_war and sim.year < 200:
            sim.step(1)
            self.assertAlmostEqual(land, total_land(sim), places=6)
        self.assertGreaterEqual(sim.dynasty, 2)
        founding = next(h for h in sim.history if h["dynasty"] == 2)
        self.assertEqual(founding["hidden_land"], 0.0)
        self.assertEqual(founding["debt_ratio"], 0.0)

    def test_war_hands_leased_land_to_tenants(self):
        sim = AgrarianSimulation(households=3, seed=1)
        landlord, tenant, owner = sim.households
        landlord.members, landlord.land = 5, 80.0
        tenant.members, tenant.land = 5, 0.0
        owner.members, owner.land = 5, 40.0
        sim.total_land, sim.state_land = 120.0, 0.0
        sim._seize_leased_land()   # 8 亩/人: landlord leases out 40, tenant rents 40
        self.assertAlmostEqual(landlord.land, 80.0 - 40.0 * sim.institution.war_seizure)
        self.assertAlmostEqual(tenant.land, 40.0 * sim.institution.war_seizure)
        self.assertAlmostEqual(owner.land, 40.0)
        self.assertAlmostEqual(sum(h.land for h in sim.households), 120.0)

    def test_new_dynasty_starts_with_more_equal_land(self):
        sim = AgrarianSimulation(households=600, seed=7)
        while sim.dynasty == 1 and sim.year < 500:
            sim.step(1)
        self.assertEqual(sim.dynasty, 2)
        fall = next(h for h in reversed(sim.history) if h["at_war"] == 0 and h["dynasty"] == 1)
        self.assertLess(sim.metrics()["land_gini"], float(fall["land_gini"]) - 0.1)

    def test_heirs_receive_whole_members(self):
        sim = AgrarianSimulation(households=1, seed=2, institution=Institution(inheritance="equal"))
        parent = sim.households[0]
        parent.members, parent.land, parent.next_split = 15, 30.0, 0
        sim._succession()
        self.assertEqual(sum(h.members for h in sim.households), 15)
        self.assertAlmostEqual(sum(h.land for h in sim.households), 30.0)
        self.assertTrue(all(isinstance(h, Household) and h.members >= 1 for h in sim.households))

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
