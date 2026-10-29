"""Bottom-up agrarian society simulation.

No ruler decisions, relief, technology buffs or scripted events are used.
Harvests vary from year to year, as they do in any pre-modern farm economy.
Dynastic cycles emerge from production, subsistence, reproduction,
inheritance, credit, taxation and revolt.

Units: land in 亩 (mu), grain in 石 (shi), rates per year.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import csv
import math
import random
from pathlib import Path
from typing import Iterable

# Structural constants with a measured meaning; they are not policy knobs.
HOUSEHOLD_SIZE = 5       # 户均五口: expected members per married son's household
GRAIN_SPOILAGE = 0.10    # share of stored grain lost each year
LANDLESS_LAND = 0.5      # 亩/人 below which a household counts as landless


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
    """Physical conditions and rules fixed from outside the household."""

    yield_per_mu: float = 2.0          # 石/亩 at the reference density
    reference_land: float = 4.0        # 亩/人 at which yield_per_mu is observed
    land_elasticity: float = 0.50      # land share of output; competitive rent share
    subsistence: float = 4.0           # 石/人/年 grain-equivalent minimum
    baseline_mortality: float = 0.030
    shortage_mortality: float = 0.30   # extra deaths per unit of food shortfall
    harvest_cv: float = 0.20           # coefficient of variation of annual yield
    interest_rate: float = 0.40        # grain loans
    years_purchase: float = 12.0       # land price as years of net rent
    fiscal_burden: float = 0.08        # state demand as share of output at founding
    fiscal_growth: float = 0.007       # yearly growth of state demand within a dynasty
    evasion_rate: float = 0.01         # speed at which large estates leave the register
    revolt_threshold: float = 0.20     # mobilized share a fully funded state can suppress
    war_mortality: float = 0.03        # violent deaths per year among rebels
    generation_years: int = 25
    inheritance: str = "equal"


@dataclass
class Strategy:
    """Heritable behaviour; selection acts on surviving descendants."""

    fertility: float = 0.040
    reserve_years: float = 0.50
    acquisition: float = 0.60          # share of spare grain offered as loans
    resistance_threshold: float = 0.15  # remembered hunger at which a family joins revolt
    equal_inheritance: bool = True


@dataclass
class Household:
    ident: int
    lineage: int
    members: int
    land: float
    grain: float
    strategy: Strategy
    next_split: int = 0
    debt: float = 0.0
    credit: float = 0.0
    hidden: float = 0.0       # share of land kept off the tax register
    hunger: float = 0.0
    grievance: float = 0.0
    rebel: bool = False

    @property
    def land_per_person(self) -> float:
        return self.land / max(self.members, 1)


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
                 max_households: int = 6000):
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
        self.total_land = total_land if total_land is not None else households * 30.0
        self.year = self.cycles = 0
        self.dynasty, self.dynasty_start, self.at_war = 1, 0, False
        self.state_land = 0.0
        self.fiscal_base = self.fiscal_need = self.collected = 0.0
        self.fiscal_ratio = 1.0
        self.tax_per_mu = self.land_price = self.last_transferred_land = 0.0
        self.pressure = self.mobilized = 0.0
        self.next_ident = households
        self.households: list[Household] = []
        self.history: list[dict[str, float | int | str]] = []
        self.events: list[str] = []
        self._create_population(households)
        self.wage, self.rent, self.output_per_person = self._factor_prices()
        self._found_dynasty()
        self.land_price = self.rent * self.institution.years_purchase
        self._record()

    # ------------------------------------------------------------------ setup

    def _create_population(self, count: int) -> None:
        raw_land = [self.rng.lognormvariate(1.45, 0.30) for _ in range(count)]
        scale = self.total_land / sum(raw_land)
        for i, amount in enumerate(raw_land):
            strategy = (Strategy(
                fertility=self.rng.uniform(0.020, 0.060),
                reserve_years=self.rng.uniform(0.10, 1.50),
                acquisition=self.rng.uniform(0.10, 0.95),
                resistance_threshold=self.rng.uniform(0.05, 0.50),
                equal_inheritance=self.rng.random() < 0.5,
            ) if self.mode == "evolution" else replace(self.fixed_strategy))
            members = self.rng.randint(3, 7)
            self.households.append(Household(
                ident=i, lineage=i, members=members, land=amount * scale,
                grain=members * self.institution.subsistence * self.rng.uniform(0.4, 1.4),
                strategy=strategy,
                next_split=self.rng.randint(1, self.institution.generation_years),
            ))

    @property
    def living(self) -> list[Household]:
        return [h for h in self.households if h.members > 0]

    def _binomial(self, n: int, p: float) -> int:
        if n <= 0 or p <= 0:
            return 0
        if p >= 1:
            return n
        if n <= 25:
            return sum(1 for _ in range(n) if self.rng.random() < p)
        mean, sd = n * p, math.sqrt(n * p * (1 - p))
        return min(n, max(0, round(self.rng.gauss(mean, sd))))

    # ---------------------------------------------------------------- economy

    def _factor_prices(self, include_ownerless: bool = False) -> tuple[float, float, float]:
        """Competitive tenancy with Cobb-Douglas farms.

        When land is leased until every family farms in proportion to its
        labour, each person earns the marginal product of labour and each 亩
        earns the marginal product of land. Rent is therefore the land share
        of output, and rent per 亩 rises as people crowd the land.
        """
        inst = self.institution
        population = sum(h.members for h in self.households)
        cultivated = self.total_land - (0.0 if include_ownerless else self.state_land)
        if population <= 0 or cultivated <= 0:
            return 0.0, 0.0, 0.0
        alpha = inst.land_elasticity
        k = cultivated / (population * inst.reference_land)
        per_person = inst.yield_per_mu * inst.reference_land * k ** alpha
        rent = alpha * inst.yield_per_mu * k ** (alpha - 1)
        return (1 - alpha) * per_person, rent, per_person

    def _found_dynasty(self) -> None:
        """A new regime surveys the land, voids old debts and settles refugees."""
        survivors = self.living
        weight = sum(h.members * (2.0 if h.rebel else 1.0) for h in survivors)
        for h in survivors:
            if self.state_land > 0 and weight > 0:
                h.land += self.state_land * h.members * (2.0 if h.rebel else 1.0) / weight
            h.debt = h.credit = h.hidden = h.grievance = 0.0
            h.rebel = False
        if survivors:
            self.state_land = 0.0
        self.at_war = False
        self.dynasty_start = self.year
        self.wage, self.rent, self.output_per_person = self._factor_prices()
        population = sum(h.members for h in survivors)
        self.fiscal_base = self.institution.fiscal_burden * self.output_per_person * population
        self.fiscal_need = self.fiscal_base

    def step(self, years: int = 1) -> None:
        for _ in range(years):
            self._step_year()

    def _step_year(self) -> None:
        self.year += 1
        self.events = []
        self.last_transferred_land = 0.0
        if not self.households:
            self._record()
            return
        inst = self.institution
        self.wage, self.rent, self.output_per_person = self._factor_prices()

        # The state needs a growing sum and can only tax land on the register.
        if not self.at_war:
            self._update_evasion()
        age = self.year - self.dynasty_start
        self.fiscal_need = self.fiscal_base * (1 + inst.fiscal_growth) ** age
        registered = sum(h.land * (1 - h.hidden) for h in self.households)
        if self.at_war or registered <= 0:
            self.tax_per_mu = 0.0
        else:
            self.tax_per_mu = min(self.rent, self.fiscal_need / registered)
        self.land_price = max(0.0, self.rent - self.tax_per_mu) * inst.years_purchase

        # Harvest: one shock shared by the region, one particular to the family.
        s2 = math.log(1 + inst.harvest_cv ** 2) / 2
        common = math.exp(self.rng.gauss(-s2 / 2, math.sqrt(s2)))
        collected = 0.0
        for h in self.households:
            local = math.exp(self.rng.gauss(-s2 / 2, math.sqrt(s2)))
            if self.at_war:
                # In a war zone the land's share is requisitioned or destroyed by
                # armies; families live on their labour alone.
                income = self.wage * h.members * common * local
            else:
                income = (self.wage * h.members * local + self.rent * h.land) * common
            h.grain = h.grain * (1 - GRAIN_SPOILAGE) + income
            paid = min(h.grain, self.tax_per_mu * h.land * (1 - h.hidden))
            h.grain -= paid
            collected += paid
        self.collected = collected
        self.fiscal_ratio = 0.0 if self.at_war else collected / max(self.fiscal_need, 1e-9)

        if not self.at_war:
            self._lend()
        self._demography()
        if not self.at_war:
            self._settle_debts()
        self._resolve_extinctions()
        self._succession()
        if not self.at_war and self.state_land > 0:
            self._settle_state_land()
        self._reconcile_credit()
        self._update_war()
        self._record()

    def _update_evasion(self) -> None:
        """Large estates drift off the register; a family ten times the mean hides all."""
        households = self.households
        mean_land = (self.total_land - self.state_land) / max(len(households), 1)
        for h in households:
            ratio = h.land / max(mean_land, 1e-9)
            influence = clamp(math.log10(ratio)) if ratio > 1 else 0.0
            h.hidden += self.institution.evasion_rate * (influence - h.hidden)

    def _lend(self) -> None:
        """Families short of food borrow against land from families with spare grain."""
        inst = self.institution
        requests, offers = [], []
        for h in self.households:
            need = h.members * inst.subsistence
            if h.grain < need:
                capacity = max(0.0, h.land * self.land_price - h.debt)
                if capacity > 0:
                    requests.append((h, min(need - h.grain, capacity)))
            else:
                spare = h.grain - need * (1 + h.strategy.reserve_years)
                if spare > 0 and h.strategy.acquisition > 0:
                    offers.append((h, spare * h.strategy.acquisition))
        demand, supply = sum(x for _, x in requests), sum(x for _, x in offers)
        lent = min(demand, supply)
        if lent <= 0:
            return
        for h, amount in requests:
            loan = lent * amount / demand
            h.grain += loan
            h.debt += loan
        for h, amount in offers:
            loan = lent * amount / supply
            h.grain -= loan
            h.credit += loan

    def _demography(self) -> None:
        inst = self.institution
        for h in self.households:
            required = h.members * inst.subsistence
            eaten = min(h.grain, required)
            h.hunger = 1.0 - eaten / max(required, 1e-9)
            h.grain -= eaten
            risk = inst.baseline_mortality + inst.shortage_mortality * h.hunger
            if self.at_war:
                risk += inst.war_mortality * (1.0 if h.rebel else 0.5)
            survivors = h.members - self._binomial(h.members, clamp(risk))
            # Hunger delays marriage and suppresses fertility.
            births = self._binomial(survivors, h.strategy.fertility * (1.0 - h.hunger))
            h.members = survivors + births
            h.grievance = 0.7 * h.grievance + 0.3 * h.hunger

    def _creditors(self) -> tuple[list[Household], float]:
        creditors = [h for h in self.households if h.credit > 0]
        return creditors, sum(h.credit for h in creditors)

    def _settle_debts(self) -> None:
        """Debtors hand over spare grain, interest accrues, and land is foreclosed."""
        repaid = 0.0
        for h in self.households:
            if h.debt > 0 and h.grain > 0:
                pay = min(h.debt, h.grain)
                h.debt -= pay
                h.grain -= pay
                repaid += pay
        creditors, total_credit = self._creditors()
        if repaid > 0 and total_credit > 0:
            for c in creditors:
                share = repaid * c.credit / total_credit
                c.grain += share
                c.credit = max(0.0, c.credit - share)
        rate = 1 + self.institution.interest_rate
        for h in self.households:
            h.debt *= rate
            h.credit *= rate

        # Debt beyond the value of the land: the land passes to the creditors.
        seized = seized_value = 0.0
        for h in self.households:
            if h.debt <= 1e-9:
                continue
            if h.land * self.land_price < h.debt:
                seized += h.land
                seized_value += min(h.debt, h.land * self.land_price)
                h.land = 0.0
                h.debt = 0.0
        self.last_transferred_land = seized
        creditors, total_credit = self._creditors()
        if seized > 0:
            if total_credit <= 0:
                self.state_land += seized
                return
            for c in creditors:
                share = c.credit / total_credit
                c.land += seized * share
                c.credit = max(0.0, c.credit - seized_value * share)

    def _reconcile_credit(self) -> None:
        """Unrecoverable debts are lost by creditors pro rata, and vice versa."""
        debts = sum(h.debt for h in self.households)
        credits = sum(h.credit for h in self.households)
        if abs(debts - credits) <= 1e-9 * max(1.0, debts):
            return
        if debts > credits:
            scale = credits / debts if debts > 0 else 0.0
            for h in self.households:
                h.debt *= scale
        else:
            scale = debts / credits if credits > 0 else 0.0
            for h in self.households:
                h.credit *= scale

    def _resolve_extinctions(self) -> None:
        """Extinct estates pass to surviving kin, or become ownerless land."""
        extinct = [h for h in self.households if h.members <= 0]
        if not extinct:
            return
        survivors = [h for h in self.households if h.members > 0]
        by_lineage: dict[int, list[Household]] = {}
        if not self.at_war:
            for h in survivors:
                by_lineage.setdefault(h.lineage, []).append(h)
        for estate in extinct:
            kin = by_lineage.get(estate.lineage)
            if kin:
                heir = min(kin, key=lambda h: h.land / h.members)
                heir.land += estate.land
                heir.grain += estate.grain
                heir.debt += estate.debt
                heir.credit += estate.credit
            else:
                self.state_land += estate.land
        self.households = survivors

    def _settle_state_land(self) -> None:
        """In peacetime ownerless land is reclaimed by the families who farm nearby."""
        population = sum(h.members for h in self.households)
        if population <= 0:
            return
        for h in self.households:
            h.land += self.state_land * h.members / population
        self.state_land = 0.0

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
            fertility=gene(strategy.fertility, 0.005, 0.06),
            reserve_years=gene(strategy.reserve_years, 0.0, 3.0),
            acquisition=gene(strategy.acquisition, 0.0, 1.0),
            resistance_threshold=gene(strategy.resistance_threshold, 0.02, 0.90),
            equal_inheritance=equal_inheritance,
        )

    def _succession(self) -> None:
        """Each family divides when its generation turns over.

        The number of heirs is drawn from the family's size, so families that
        ate well and raised more sons split their estate into more pieces.
        """
        generation = self.institution.generation_years
        result = []
        available_slots = max(0, self.max_households - len(self.households))
        for parent in self.households:
            if self.year < parent.next_split:
                result.append(parent)
                continue
            heirs = max(1, self._binomial(parent.members, 1 / HOUSEHOLD_SIZE))
            heirs = min(heirs, parent.members, 1 + available_slots)
            available_slots -= heirs - 1
            if heirs <= 1:
                parent.strategy = self._mutate(parent.strategy)
                parent.next_split = self.year + generation
                result.append(parent)
                continue
            base, extra = divmod(parent.members, heirs)
            for i in range(heirs):
                share = 1 / heirs if parent.strategy.equal_inheritance else float(i == 0)
                result.append(Household(
                    ident=self.next_ident, lineage=parent.lineage,
                    members=base + (1 if i < extra else 0),
                    land=parent.land * share, grain=parent.grain / heirs,
                    strategy=self._mutate(parent.strategy),
                    next_split=self.year + generation,
                    debt=parent.debt * share, credit=parent.credit / heirs,
                    hidden=parent.hidden, hunger=parent.hunger,
                    grievance=parent.grievance, rebel=parent.rebel,
                ))
                self.next_ident += 1
        self.households = result

    # ------------------------------------------------------------ revolt/war

    def _mobilized_share(self) -> float:
        population = sum(h.members for h in self.households)
        if population <= 0:
            return 0.0
        return sum(h.members for h in self.households
                   if h.grievance > h.strategy.resistance_threshold) / population

    def _update_war(self) -> None:
        inst = self.institution
        self.mobilized = self._mobilized_share()
        if not self.at_war:
            capacity = clamp(self.fiscal_ratio)
            self.pressure = self.mobilized / max(inst.revolt_threshold * capacity, 1e-9)
            if self.mobilized >= inst.revolt_threshold * capacity and self.households:
                self.at_war = True
                self.cycles += 1
                for h in self.households:
                    h.rebel = h.grievance > h.strategy.resistance_threshold
                self.events.append(
                    f"第 {self.dynasty} 朝第 {self.year - self.dynasty_start} 年大起义："
                    f"动员 {self.mobilized:.0%}，财政充足率 {self.fiscal_ratio:.0%}"
                )
            return
        # The war ends once the survivors, settled on abandoned fields too, can
        # again live by their own labour.
        self.pressure = 1.0
        wage, _rent, _per_person = self._factor_prices(include_ownerless=True)
        settled = wage >= inst.subsistence and self.mobilized <= inst.revolt_threshold / 2
        if settled or not self.households:
            self.dynasty += 1
            self.events.append(f"战乱结束，第 {self.dynasty} 朝建立")
            self._found_dynasty()

    # ---------------------------------------------------------------- metrics

    def strategy_metrics(self) -> dict[str, float]:
        living = self.households
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
        living = self.households
        population, lands = sum(h.members for h in living), [h.land for h in living]
        owned = max(sum(lands), 1e-9)
        ordered = sorted(living, key=lambda h: h.land, reverse=True)
        elite_n = max(1, len(ordered) // 10) if ordered else 0
        output = self.output_per_person * population
        result: dict[str, float | int | str] = {
            "year": self.year,
            "generation": self.year // self.institution.generation_years,
            "dynasty": self.dynasty, "dynasty_age": self.year - self.dynasty_start,
            "cycles": self.cycles, "at_war": int(self.at_war),
            "mode": self.mode, "population": population, "households": len(living),
            "land_per_person": (self.total_land - self.state_land) / max(population, 1),
            "land_gini": gini(lands),
            "top10_land": sum(h.land for h in ordered[:elite_n]) / owned,
            "landless_rate": sum(h.members for h in living
                                 if h.land_per_person < LANDLESS_LAND) / max(population, 1),
            "land_deficient_rate": sum(
                h.members for h in living
                if h.land_per_person < self.institution.reference_land
            ) / max(population, 1),
            "hunger_rate": sum(h.members * h.hunger for h in living) / max(population, 1),
            "mobilized": self.mobilized, "uprising_pressure": min(self.pressure, 1.0),
            "fiscal_ratio": self.fiscal_ratio, "tax_per_mu": self.tax_per_mu,
            "tax_share": self.collected / max(output, 1e-9),
            "hidden_land": sum(h.land * h.hidden for h in living) / owned,
            "debt_ratio": sum(h.debt for h in living) / max(owned * self.land_price, 1e-9),
            "land_price": self.land_price, "rent": self.rent, "wage": self.wage,
            "land_transferred": self.last_transferred_land,
        }
        result.update(self.strategy_metrics())
        return result

    def _record(self) -> None:
        self.history.append(dict(self.metrics()))

    def land_histogram(self, bins: int = 20) -> tuple[list[int], float]:
        values = [h.land for h in self.households]
        if not values:
            return [0] * bins, 1.0
        cap = max(1.0, sorted(values)[min(len(values) - 1, int(len(values) * .97))])
        counts = [0] * bins
        for value in values:
            counts[min(bins - 1, int(value / cap * bins))] += 1
        return counts, cap

    def lineage_shares(self, limit: int = 8) -> list[tuple[int, float]]:
        totals, population = {}, sum(h.members for h in self.households)
        for h in self.households:
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
