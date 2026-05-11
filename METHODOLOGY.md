# CourtAlpha Methodology: Executive Intelligence Suite

## 1. System Architecture: The Unified Data Pillar
CourtAlpha operates on a **Single Source of Truth** architecture powered by **DuckDB**. This high-performance OLAP engine allows for sub-millisecond querying of multi-million row play-by-play datasets, enabling real-time frontline decision support.

- **Data Ingestion:** Automated daily pipelines via `nba_api` pulling play-by-play (PBP), player tracking coordinates, and official box scores.
- **Roster Truth:** A proprietary synchronization layer that reconciles Spotrac contract data with real-time NBA roster movements, ensuring 100% accurate team-cap mapping.
- **Garbage Time Filter:** All ML models are trained exclusively on "Leverage Minutes"—filtering out noise where the score differential is >15 points in the 4th quarter.

## 2. ML Core: Meta-Impact & Bayesian Shrinkage
Our impact model moves beyond traditional box scores to capture **Structural Gravity**.

- **RAPM-Lite (Proprietary Meta-Impact):** A ridge-regression-based impact model that calculates a player’s contribution to team point differential per 100 possessions, adjusted for teammate and opponent quality.
- **Bayesian Shrinkage:** To solve the "Small Sample Size" problem (e.g., rookies or end-of-bench players), we use Bayesian priors to shrink raw impact scores toward the league mean until a sufficient possession threshold is reached.
- **xEFG% (Expected Effective Field Goal Percentage):** A spatial heuristic that evaluates the *quality* of shots a player generates based on location coordinates, regardless of whether the shot went in.

## 3. Economic Layer: True Surplus Value
We translate statistical impact into financial leverage by comparing performance against the current 2023 CBA salary scales.

- **Market Valuation:** A dynamic model that calculates what a player *should* be paid based on their Meta-Impact, age trajectory, and archetype scarcity.
- **Surplus Value:** The delta between a player’s **Market Value** and their **Actual Contract Cost**. This is the primary KPI for front-office efficiency.
- **Offseason Strategic Outlook:** Categorizes players as *Pillars* (Max-level anchors), *Engines* (High-usage creators), or *Connectors* (Elite role players) to guide trade and free-agency targets.

## 4. Spatial Intelligence & Gravity
CourtAlpha uses raw (X, Y) coordinate data to map the floor geometry of every 5-man unit.

- **Spacing Rating:** Calculated by measuring the perimeter gravity of all 5 players on the floor.
- **Context Suppression:** A specialized engine that identifies "Hidden Gems"—players whose efficiency is suppressed by poor teammate spacing, projecting their breakout potential in optimized lineups.

## 5. Integrity & Validation
Every metric in CourtAlpha is backed by a **Play-By-Play Tape**. Users can drill down from an executive metric (e.g., +3.5 Meta-Impact) directly to the specific game events that drove that score, ensuring total transparency and auditability.
