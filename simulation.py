"""Bottom-up agrarian society simulation.

No disasters, rulers, relief, technology buffs or scripted events are used.
Macro history emerges from production, subsistence, reproduction, inheritance,
land markets and revolt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import csv
import math
import random
from pathlib import Path
from typing import Iterable


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def gini(values: Iterable[float]) -> float:
    xs = sorted(max(0.0, float(v)) for v in values)
    total, n = sum(xs), len(xs)
    if not n or total <= 1e-12:
        return 0.0
    weighted = sum((i + 1) * x for i, x in enumerate(xs))
    return clamp(2 * weighted / (n * total) - (n + 1) / n)


@dataclass
class Institution:
    """Rules fixed from outside the household."""

    tax_rate: float = 0.12
    rent_share: float = 0.32
    subsistence: float = 1.00
    land_elasticity: float = 0.55
    labor_per_person: float = 1.25
    child_cost: float = 1.40
    baseline_mortality: float = 0.018
    shortage_mortality: float = 0.22
    generation_years: int = 25
    uprising_threshold: float = 0.18
    redistribution_share: float = 0.68
    conflict_mortality: float = 0.035
    inheritance: str = "equal"


@dataclass
class Strategy:
    """Heritable behaviour; selection acts on surviving descendants."""

    fertility: float = 0.055
    reserve_years: float = 0.80
    acquisition: float = 0.55
    resistance_threshold: float = 0.46
    equal_inheritance: bool = True


@dataclass
class Household:
    ident: int
    lineage: int
    members: float
    land: float
    grain: float
    strategy: Strategy
    hunger: float = 0.0
    grievance: float = 0.0
    operational_land: float = 0.0
    leased_land: float = 0.0
    output: float = 0.0

    @property
    def land_per_person(self) -> float:
        return self.land / max(self.members, 0.05)


class AgrarianSimulation:
    """Household model with fixed-rule and evolutionary modes.

    Fixed mode applies one strategy and a chosen inheritance institution to all
    families. Evolution mode copies strategies into descendants with mutation.
    Differential survival and reproduction—not a utility oracle—perform the
    optimization.
    """

    def __init__(self, households: int = 600, total_land: float | None = None,
                 seed: int = 7, mode: str = "fixed",
                 institution: Institution | None = None,
                 fixed_strategy: Strategy | None = None,
                 mutation_rate: float = 0.06, mutation_scale: float = 0.07,
                 max_households: int = 4000):
        if mode not in {"fixed", "evolution"}:
            raise ValueError("mode must be 'fixed' or 'evolution'")
        self.seed, self.rng, self.mode = seed, random.Random(seed), mode
        self.institution = institution or Institution()
        self.fixed_strategy = fixed_strategy or Strategy()
        if mode == "fixed":
            self.fixed_strategy = replace(
                self.fixed_strategy,
                equal_inheritance=self.institution.inheritance == "equal",
            )
        self.mutation_rate, self.mutation_scale = mutation_rate, mutation_scale
        self.max_households = max_households
        self.initial_households = households
        self.total_land = total_land if total_land is not None else households * 5.0
        self.year = self.generation = self.cycles = 0
        self.land_price = 4.5
        self.next_ident = households
        self.households: list[Household] = []
        self.history: list[dict[str, float | int | str]] = []
        self.events: list[str] = []
        self.last_transferred_land = 0.0
        self._create_population(households)
        self._record()

    def _create_population(self, count: int) -> None:
        raw_land = [self.rng.lognormvariate(1.45, 0.30) for _ in range(count)]
        scale = self.total_land / sum(raw_land)
        for i, amount in enumerate(raw_land):
            strategy = (Strategy(
                fertility=self.rng.uniform(0.025, 0.090),
                reserve_years=self.rng.uniform(0.15, 1.80),
                acquisition=self.rng.uniform(0.10, 0.95),
                resistance_threshold=self.rng.uniform(0.25, 0.75),
                equal_inheritance=self.rng.random() < 0.5,
            ) if self.mode == "evolution" else replace(self.fixed_strategy))
            members = self.rng.uniform(3.2, 6.0)
            self.households.append(Household(
                ident=i, lineage=i, members=members, land=amount * scale,
                grain=members * self.institution.subsistence * self.rng.uniform(0.4, 1.4),
                strategy=strategy,
            ))

    @property
    def living(self) -> list[Household]:
        return [h for h in self.households if h.members >= 0.20]

    def step(self, years: int = 1) -> None:
        for _ in range(years):
            self._step_year()

    def _step_year(self) -> None:
        self.year += 1
        self.events = []
        living = self.living
        if not living:
            self._record()
            return

        # Rental market: idle owned land is allocated in proportion to spare labor.
        idle, tenants = [], []
        for h in living:
            labor_capacity = h.members * self.institution.labor_per_person
            own_operated = min(h.land, labor_capacity)
            h.operational_land, h.leased_land = own_operated, 0.0
            if h.land > own_operated:
                idle.append((h, h.land - own_operated))
            if labor_capacity > own_operated:
                tenants.append((h, labor_capacity - own_operated))
        idle_total, demand_total = sum(x for _, x in idle), sum(x for _, x in tenants)
        leased_total = min(idle_total, demand_total)
        if demand_total > 0:
            for h, demand in tenants:
                h.leased_land = leased_total * demand / demand_total
                h.operational_land += h.leased_land

        # Cobb-Douglas output. Tax exits the household sector; rent is transferred.
        rent_pool = 0.0
        for h in living:
            labor = min(h.members * self.institution.labor_per_person,
                        max(h.operational_land, 1e-9))
            alpha = self.institution.land_elasticity
            h.output = (max(h.operational_land, 0.0) ** alpha
                        * max(labor, 0.0) ** (1 - alpha) * 1.85)
            leased_fraction = h.leased_land / max(h.operational_land, 1e-9)
            rent = h.output * leased_fraction * self.institution.rent_share
            tax = h.output * self.institution.tax_rate
            h.grain += h.output - rent - tax
            rent_pool += rent
        if idle_total > 0:
            for owner, amount in idle:
                owner.grain += rent_pool * amount / idle_total

        # Subsistence precedes births. Both mortality and births are resource-bound.
        for h in living:
            required = h.members * self.institution.subsistence
            coverage = clamp(h.grain / max(required, 1e-9))
            h.hunger = 1.0 - coverage
            deaths = h.members * (self.institution.baseline_mortality
                                  + self.institution.shortage_mortality * h.hunger)
            h.grain -= min(h.grain, required)
            survivors = max(0.0, h.members - deaths)
            reserve = h.strategy.reserve_years * survivors * self.institution.subsistence
            reproductive_surplus = max(0.0, h.grain - reserve)
            births = min(h.strategy.fertility * survivors,
                         reproductive_surplus / max(self.institution.child_cost, 1e-9))
            h.grain -= births * self.institution.child_cost
            h.members = survivors + births

        self._land_market()
        self._resolve_extinctions()
        self.households = self.living
        if self.year % self.institution.generation_years == 0:
            self._succession()
        self._update_grievances()
        self._test_uprising()
        self._record()

    def _resolve_extinctions(self) -> None:
        """Pass extinct estates to surviving kin, or back to surviving cultivators."""
        extinct = [h for h in self.households if h.members < 0.20]
        survivors = [h for h in self.households if h.members >= 0.20]
        if not extinct or not survivors:
            return
        by_lineage: dict[int, list[Household]] = {}
        for h in survivors:
            by_lineage.setdefault(h.lineage, []).append(h)
        unclaimed_land = 0.0
        unclaimed_grain = 0.0
        for estate in extinct:
            kin = by_lineage.get(estate.lineage, [])
            if kin:
                heir = min(kin, key=lambda h: h.land / max(h.members, 0.2))
                heir.land += estate.land
                heir.grain += estate.grain
            else:
                unclaimed_land += estate.land
                unclaimed_grain += estate.grain
            estate.land = estate.grain = 0.0
        if unclaimed_land or unclaimed_grain:
            weight = sum(h.members for h in survivors)
            for h in survivors:
                share = h.members / max(weight, 1e-9)
                h.land += unclaimed_land * share
                h.grain += unclaimed_grain * share

    def _land_market(self) -> None:
        """Reserve shortfall creates supply; surplus and acquisition create demand."""
        sale_offers, buy_offers = [], []
        for h in self.living:
            target = h.strategy.reserve_years * h.members * self.institution.subsistence
            shortfall, surplus = max(0.0, target - h.grain), max(0.0, h.grain - target)
            if shortfall > 0 and h.land > 0:
                sale_offers.append((h, min(h.land, shortfall / max(self.land_price, 0.1))))
            budget = surplus * h.strategy.acquisition
            if budget > 0:
                buy_offers.append((h, budget))
        supply = sum(x for _, x in sale_offers)
        demand = sum(x for _, x in buy_offers) / max(self.land_price, 0.1)
        imbalance = (demand - supply) / max(self.total_land * 0.025, 1.0)
        self.land_price *= math.exp(clamp(imbalance, -1.0, 1.0) * 0.10)
        self.land_price = min(40.0, max(0.8, self.land_price))
        quantity = min(supply, sum(x for _, x in buy_offers) / self.land_price)
        self.last_transferred_land = quantity
        if quantity <= 1e-10 or supply <= 0:
            return
        revenue = quantity * self.land_price
        for seller, amount in sale_offers:
            sold = quantity * amount / supply
            seller.land -= sold
            seller.grain += revenue * amount / supply
        total_budget = sum(x for _, x in buy_offers)
        for buyer, budget in buy_offers:
            bought = quantity * budget / max(total_budget, 1e-9)
            buyer.land += bought
            buyer.grain -= bought * self.land_price

    def _mutate(self, strategy: Strategy) -> Strategy:
        if self.mode != "evolution":
            return replace(self.fixed_strategy)
        def gene(value: float, low: float, high: float) -> float:
            if self.rng.random() >= self.mutation_rate:
                return value
            return min(high, max(low, value + self.rng.gauss(0, self.mutation_scale * (high - low))))
        equal_inheritance = strategy.equal_inheritance
        if self.rng.random() < self.mutation_rate:
            equal_inheritance = not equal_inheritance
        return Strategy(
            fertility=gene(strategy.fertility, 0.005, 0.14),
            reserve_years=gene(strategy.reserve_years, 0.0, 3.0),
            acquisition=gene(strategy.acquisition, 0.0, 1.0),
            resistance_threshold=gene(strategy.resistance_threshold, 0.05, 0.95),
            equal_inheritance=equal_inheritance,
        )

    def _succession(self) -> None:
        self.generation += 1
        result = []
        available_slots = max(0, self.max_households - len(self.households))
        for parent in self.living:
            potential = min(4, max(1, int(parent.members / 3.4)))
            heirs = min(potential, 1 + available_slots)
            available_slots -= heirs - 1
            if heirs <= 1:
                parent.strategy = self._mutate(parent.strategy)
                result.append(parent)
                continue
            equal_share = 1.0 if parent.strategy.equal_inheritance else 0.0
            equal_pool, first_pool = parent.land * equal_share, parent.land * (1 - equal_share)
            for i in range(heirs):
                result.append(Household(
                    ident=self.next_ident, lineage=parent.lineage,
                    members=parent.members / heirs,
                    land=equal_pool / heirs + (first_pool if i == 0 else 0.0),
                    grain=parent.grain / heirs, strategy=self._mutate(parent.strategy),
                    hunger=parent.hunger, grievance=parent.grievance * 0.70,
                ))
                self.next_ident += 1
        self.households = result
        self.events.append(f"第 {self.generation} 代继承完成：{len(result)} 户")

    def _self_sufficient_land(self) -> float:
        return (self.institution.subsistence
                / max(1.85 * (1.0 - self.institution.tax_rate), 0.1))

    def _current_stress(self, h: Household, inequality: float) -> float:
        land_deficit = clamp(1.0 - h.land_per_person / self._self_sufficient_land())
        return clamp(0.42 * h.hunger + 0.38 * land_deficit + 0.20 * inequality)

    def _update_grievances(self) -> None:
        living = self.living
        inequality = gini(h.land for h in living)
        for h in living:
            current = self._current_stress(h, inequality)
            h.grievance = clamp(0.88 * h.grievance + 0.12 * current)

    def _collective_state(self) -> tuple[float, float, float]:
        living, population = self.living, sum(h.members for h in self.living)
        if population <= 0:
            return 0.0, 0.0, 0.0
        material = sum(h.members * h.grievance for h in living) / population
        mobilized = sum(
            h.members * clamp((h.grievance - h.strategy.resistance_threshold) * 5.0)
            for h in living
        ) / population
        return clamp(0.68 * material + 0.32 * mobilized), mobilized, material

    def _uprising_pressure(self) -> tuple[float, float]:
        pressure, mobilized, _material = self._collective_state()
        return pressure, mobilized

    def _test_uprising(self) -> None:
        pressure, _mobilized, material = self._collective_state()
        if pressure < self.institution.uprising_threshold:
            return
        self.cycles += 1
        living = self.living
        before = gini(h.land for h in living)
        ordered = sorted(living, key=lambda h: h.land)
        median_land = ordered[len(ordered) // 2].land
        pool = 0.0
        participation: dict[int, float] = {}
        for h in living:
            participation[h.ident] = clamp(
                (h.grievance - h.strategy.resistance_threshold) * 5
            )
            seized = max(0.0, h.land - median_land) * self.institution.redistribution_share
            h.land -= seized
            pool += seized
            risk = self.institution.conflict_mortality * (
                0.25 + 0.75 * participation[h.ident]
            )
            h.members *= 1.0 - risk
            h.grievance *= 0.35
        recipients = [h for h in living if h.land <= median_land]
        recipient_weight = sum(
            h.members * (0.5 + 0.5 * participation[h.ident]) for h in recipients
        )
        for h in recipients:
            weight = h.members * (0.5 + 0.5 * participation[h.ident])
            h.land += pool * weight / max(recipient_weight, 1e-9)
        after = gini(h.land for h in living)
        self.events.append(f"第 {self.cycles} 次起义：压力 {pressure:.1%}；土地基尼 {before:.3f} → {after:.3f}")

    def strategy_metrics(self) -> dict[str, float]:
        living = self.living
        keys = ("fertility", "reserve_years", "acquisition", "resistance_threshold")
        if not living:
            return {**{k: 0.0 for k in keys}, "equal_inheritance": 0.0,
                    "primogeniture": 0.0}
        total = sum(h.members for h in living)
        result = {k: sum(getattr(h.strategy, k) * h.members for h in living) / total for k in keys}
        result["equal_inheritance"] = sum(
            h.members for h in living if h.strategy.equal_inheritance
        ) / total
        result["primogeniture"] = 1.0 - result["equal_inheritance"]
        return result

    def metrics(self) -> dict[str, float | int | str]:
        living = self.living
        population, lands = sum(h.members for h in living), [h.land for h in living]
        ordered = sorted(living, key=lambda h: h.land, reverse=True)
        elite_n = max(1, len(ordered) // 10) if ordered else 0
        pressure, mobilized = self._uprising_pressure()
        self_sufficient_land = self._self_sufficient_land()
        result: dict[str, float | int | str] = {
            "year": self.year, "generation": self.generation, "cycles": self.cycles,
            "mode": self.mode, "population": population, "households": len(living),
            "land_gini": gini(lands),
            "top10_land": sum(h.land for h in ordered[:elite_n]) / max(sum(lands), 1e-9),
            "landless_rate": sum(h.members for h in living if h.land_per_person < .12) / max(population, 1e-9),
            "land_deficient_rate": sum(
                h.members for h in living if h.land_per_person < self_sufficient_land
            ) / max(population, 1e-9),
            "hunger_rate": sum(h.members * h.hunger for h in living) / max(population, 1e-9),
            "grievance": sum(h.members * h.grievance for h in living) / max(population, 1e-9),
            "uprising_pressure": pressure, "mobilized": mobilized,
            "land_price": self.land_price, "land_transferred": self.last_transferred_land,
        }
        result.update(self.strategy_metrics())
        return result

    def _record(self) -> None:
        self.history.append(dict(self.metrics()))

    def land_histogram(self, bins: int = 20) -> tuple[list[int], float]:
        values = [h.land for h in self.living]
        if not values:
            return [0] * bins, 1.0
        cap = max(1.0, sorted(values)[min(len(values) - 1, int(len(values) * .97))])
        counts = [0] * bins
        for value in values:
            counts[min(bins - 1, int(value / cap * bins))] += 1
        return counts, cap

    def lineage_shares(self, limit: int = 8) -> list[tuple[int, float]]:
        totals, population = {}, sum(h.members for h in self.living)
        for h in self.living:
            totals[h.lineage] = totals.get(h.lineage, 0.0) + h.members
        ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [(lineage, pop / max(population, 1e-9)) for lineage, pop in ordered]

    def export_csv(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.history[0]))
            writer.writeheader()
            writer.writerows(self.history)


DynastySimulation = AgrarianSimulation
