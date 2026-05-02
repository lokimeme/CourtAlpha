"""
CourtAlpha Economic Layer (v2.2)
Phase 3: The Reality-Adjusted Economic Layer
--------------------------------------------
This module integrates financial data with health metrics to calculate 
True Surplus Value and 3-year market projections.

Methodology:
- Durability Coefficient: Discounting wins based on historical game-miss rates.
- Surplus Value: Market Value (Impact-derived) minus Actual Contract Cost.
- Salary Projections: 3-year forecasting considering estimated cap increases.
"""

import duckdb
import pandas as pd
import numpy as np
import logging
from scripts.utils import setup_logging, format_currency

# --- CONFIGURATION ---
DB_PATH = 'data/courtalpha.duckdb'
logger = setup_logging()

def calculate_market_value(meta_impact, dura_coeff, age=27):
    """
    Translates Meta-Impact (Pts/100) into seasonal market value.
    Version 2.4: External Benchmark Integration.
    """
    # 1. Shift to "Above Replacement"
    # League average meta_impact is 0. Replacement level is roughly -2.0.
    replacement_buffer = 2.0
    impact_over_replacement = meta_impact + replacement_buffer
    
    # 2. Scale to seasonal wins
    # A starter plays ~2000 mins, which is ~4000-5000 possessions.
    # We use 4,500 possessions as the benchmark for a standard heavy-rotation player.
    # total_points = (impact_over_replacement * possessions) / 100
    total_points = impact_over_replacement * 45.0 
    wins_added = total_points / 30.0 # 30 pts per win
    
    # 3. Base Value
    REPLACEMENT_VAL = 1121428 
    
    # 4. Trajectory Multiplier (Aging Curve)
    if age < 23:
        traj_multiplier = 1.25
    elif age < 26:
        traj_multiplier = 1.15
    elif age < 30:
        traj_multiplier = 1.0 
    elif age < 34:
        traj_multiplier = 0.85
    else:
        traj_multiplier = 0.65

    # 5. Non-Linear Superstar Premium
    # Top-tier wins (Elite production) are exponentially more expensive.
    if wins_added > 12:
        win_rate = 6500000  # True MVP Tier ($6.5M/win)
    elif wins_added > 8:
        win_rate = 5500000  # All-Star Tier ($5.5M/win)
    elif wins_added > 4:
        win_rate = 4500000  # Quality Starter ($4.5M/win)
    else:
        win_rate = 3500000  # Rotation/Depth ($3.5M/win)
    
    impact_value = wins_added * win_rate
    
    # Apply Trajectory and Durability
    market_val = (REPLACEMENT_VAL + impact_value) * traj_multiplier * dura_coeff
    
    return max(REPLACEMENT_VAL, market_val)

def run_economic_pipeline():
    """
    Integrates contract, age, and Meta-Impact data for market projections.
    Includes Phase 3 Strategic Valuation Layer (Pillar vs. Engine).
    """
    logger.info("Starting Meta-Adjusted Economic Layer (v2.5)...")
    con = duckdb.connect(DB_PATH)
    
    # Join metrics with metadata for age calculation
    query = """
        SELECT 
            m.PLAYER_NAME,
            m.META_IMPACT,
            m.CONTRACT_COST,
            m.ARCHETYPE_NAME,
            meta.BIRTHDATE,
            date_diff('year', CAST(meta.BIRTHDATE AS DATE), current_date) as CALC_AGE
        FROM player_metrics m
        LEFT JOIN player_metadata meta ON m.PLAYER_NAME = meta.PLAYER_NAME
    """
    df = con.execute(query).df()
    
    if df.empty:
        logger.warning("No metrics found.")
        return

    for idx, row in df.iterrows():
        p_name = row['PLAYER_NAME']
        age = row['CALC_AGE'] if not pd.isnull(row['CALC_AGE']) else 27 
        cost = row['CONTRACT_COST'] if row['CONTRACT_COST'] > 0 else 1121428
        arch = row['ARCHETYPE_NAME']
        
        # 1. Market Value using META_IMPACT (Pts/100 scale)
        meta_impact = row['META_IMPACT'] if not pd.isnull(row['META_IMPACT']) else 0.0
        market_val = calculate_market_value(meta_impact, 0.95, age)
        surplus = market_val - cost
        
        # 2. Flags
        flags = ""
        if age >= 35: flags += " 📉 Age Risk"
        elif age <= 22: flags += " 📈 Upside"
        
        # 3. STRATEGIC VALUATION LAYER
        outlook = "Rotation Depth" # Default
        
        # CHAMPIONSHIP PILLAR (High-End Starters/Stars in Scarce Archetypes)
        is_pillar_archetype = arch in ['Floor General', '3&D Wing', 'Elite Rim Protector', 'Point-of-Attack Defender']
        if is_pillar_archetype and meta_impact > 0.5:
            if cost > 30000000:
                outlook = "Championship Pillar"
                flags += " 🏛️ Pillar"
            else:
                outlook = "Elite Value Starter"
                flags += " 🟢 Value"
        
        # EFFICIENCY ENGINE (High Surplus / Low Cost)
        elif surplus > 15000000 and cost < 15000000:
            outlook = "Efficiency Engine"
            flags += " ⚙️ Engine"
        
        # CONTEXTUAL RISK
        elif cost > 35000000 and meta_impact < 0:
            outlook = "Negative Asset"
            flags += " ⚠️ Toxic Contract"
        
        elif meta_impact < -1.0:
            outlook = "Replacement Candidate"
            flags += " ❌ Replacement"

        if surplus > 15000000: 
            if "Engine" not in flags: flags += " 💎 Elite Surplus"
        elif surplus < -15000000: 
            flags += " ⚠️ Overpaid"

        # Update Database
        con.execute("""
            UPDATE player_metrics 
            SET MARKET_VALUE = ?,
                SURPLUS_VALUE = ?,
                FLAGS = ?,
                AGE = ?,
                STRATEGIC_OUTLOOK = ?
            WHERE PLAYER_NAME = ?
        """, (float(market_val), float(surplus), flags, int(age), outlook, p_name))

    con.close()
    logger.info("Meta-Economic processing complete with Strategic Layer.")

if __name__ == "__main__":
    run_economic_pipeline()
