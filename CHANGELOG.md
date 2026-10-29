# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Annual harvest shocks with a shared regional and a household component.
- Grain credit secured on land, interest, and foreclosure to creditors.
- Land price as capitalized net rent.
- State with a growing fiscal need, land registers, and tax evasion by large estates.
- Revolt when mobilized hunger exceeds what the state's funding can suppress.
- Multi-year wars and new dynasties that resurvey land, void debts and settle ownerless land.
- Integer household members and a random number of heirs per generation.

### Changed

- Rent is the competitive land share of output instead of a fixed share.
- Each household divides on its own generation clock instead of all at once.
- Births are suppressed by hunger rather than by a grain cost.
- Lending replaces land purchase as the use of the acquisition strategy.

### Removed

- `tax_rate`, `rent_share`, `uprising_threshold`, `redistribution_share`,
  `conflict_mortality`, `child_cost` and the land price bounds.

## [1.0.0] - 2026-08-14

### Added

- Bottom-up household simulation with strictly conserved land.
- Fixed-rule and evolutionary strategy modes.
- Binary equal-division and primogeniture inheritance strategies.
- Production, subsistence, reproduction, mortality, tenancy and land markets.
- Persistent household grievance, collective mobilization and uprising cycles.
- Population-weighted inheritance strategy display.
- Separate demographic, land, survival/conflict and strategy charts.
- Labeled landholding histogram and CSV history export.
- Deterministic random seeds and nine regression tests.

[1.0.0]: https://github.com/BrianQaQ/agrarian-society-simulator/releases/tag/v1.0.0

