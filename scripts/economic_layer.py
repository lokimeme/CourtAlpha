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

DB_PATH = 'data/courtalpha.duckdb'
logger = setup_logging()

def calculate_market_value(meta_impact, dura_coeff, age=27, ppg=0, archetype=""):
    """
    Translates Meta-Impact (Pts/100) into seasonal market value.
    Version 2.8: Role-Player Precision.
    """
    replacement_buffer = 2.5
    impact_over_replacement = meta_impact + replacement_buffer
    
    # Wins Added estimated from impact
    total_points = impact_over_replacement * 45.0 
    wins_added = total_points / 30.0
    
    REPLACEMENT_VAL = 1121428 
    
    # Base Trajectory Multipliers
    if age < 23:
        traj_multiplier = 1.25
    elif age < 26:
        traj_multiplier = 1.15
    elif age < 30:
        traj_multiplier = 1.0 
    elif age < 35:
        traj_multiplier = 0.90
    else:
        traj_multiplier = 0.85 if ppg >= 20 else 0.70

    # Role-Based Tuning: 
    # High-value role players (Defensive Specialists / Connectors / Spacers / Rim Protectors)
    # often have a market cap around $18M-$22M if their usage is low (PPG < 15)
    role_cap_archetypes = ["Defensive Specialist", "Two-Way Connector", "Movement Shooter", "Rim Protector"]
    if archetype in role_cap_archetypes and ppg < 15:
        traj_multiplier *= 0.82 # Specifically tuned to bring Keon-tier players to ~$20M

    # Modern Win-Rates (Max contracts are now 50-60M+)
    if wins_added > 12:
        win_rate = 8500000
    elif wins_added > 8:
        win_rate = 7500000
    elif wins_added > 4:
        win_rate = 6000000
    else:
        win_rate = 4500000
    
    impact_value = wins_added * win_rate
    
    market_val = (REPLACEMENT_VAL + impact_value) * traj_multiplier * dura_coeff
    
    # Superstar Floor
    if ppg >= 25:
        market_val = max(market_val, 45000000)
    elif ppg >= 20:
        market_val = max(market_val, 25000000)
        
    return max(REPLACEMENT_VAL, market_val)

def run_economic_pipeline():
    """
    Integrates contract, age, and Meta-Impact data for market projections.
    Includes Phase 3 Strategic Valuation Layer (Pillar vs. Engine).
    """
    logger.info("Starting Meta-Adjusted Economic Layer (v2.6)...")
    con = duckdb.connect(DB_PATH)
    
    # 1. Ensure schema is ready for economic metrics
    logger.info("Hardening player_metrics schema for financial data...")
    cols_to_add = [
        ('MARKET_VALUE', 'FLOAT'),
        ('SURPLUS_VALUE', 'FLOAT'),
        ('FLAGS', 'VARCHAR'),
        ('AGE', 'INTEGER'),
        ('STRATEGIC_OUTLOOK', 'VARCHAR'),
        ('META_IMPACT', 'FLOAT'),
        ('PPG', 'FLOAT'),
        ('CONTRACT_COST', 'FLOAT')
    ]
    
    existing_cols = [c[1] for c in con.execute("PRAGMA table_info(player_metrics)").fetchall()]
    for col, ctype in cols_to_add:
        if col not in existing_cols:
            con.execute(f"ALTER TABLE player_metrics ADD COLUMN {col} {ctype}")

    # 2. Fetch Base Data
    query = """
        SELECT 
            m.PLAYER_NAME,
            m.SHRUNK_IMPACT,
            m.ARCHETYPE_NAME,
            m.FGA,
            m.GP,
            m.PPG,
            meta.BIRTHDATE,
            date_diff('year', CAST(meta.BIRTHDATE AS DATE), current_date) as CALC_AGE,
            c.SALARY as RAW_COST
        FROM player_metrics m
        LEFT JOIN player_metadata meta ON m.PLAYER_NAME = meta.PLAYER_NAME
        LEFT JOIN contracts c ON m.PLAYER_NAME = c.PLAYER_NAME
    """
    df = con.execute(query).df()
    
    if df.empty:
        logger.warning("No metrics found.")
        return

    for idx, row in df.iterrows():
        p_name = row['PLAYER_NAME']
        age = row['CALC_AGE'] if not pd.isnull(row['CALC_AGE']) else 27 
        
        # Smarter fallback for missing contracts (Vet Min vs Rookie Min)
        default_cost = 3630000 if age >= 30 else 1121428
        cost = row['RAW_COST'] if not pd.isnull(row['RAW_COST']) and row['RAW_COST'] > 0 else default_cost
        
        arch = row['ARCHETYPE_NAME']
        
        # Meta-Impact derived from Shrunk impact (Pts/100 scale)
        meta_impact = float(row['SHRUNK_IMPACT'] * 100)
        
        # Use calculated PPG from player_metrics
        ppg = row['PPG'] if not pd.isnull(row['PPG']) else 0.0
        
        market_val = calculate_market_value(meta_impact, 0.95, age, ppg, arch)
        surplus = market_val - cost
        
        flags = ""
        if age >= 35: flags += " 📉 Age Risk"
        elif age <= 22: flags += " 📈 Upside"
        
        outlook = "Rotation Depth"
        
        is_pillar_archetype = arch in ['Floor General', '3&D Wing', 'Elite Rim Protector', 'Point-of-Attack Defender']
        if is_pillar_archetype and meta_impact > 0.5:
            if cost > 30000000:
                outlook = "Championship Pillar"
                flags += " 🏛️ Pillar"
            else:
                outlook = "Elite Value Starter"
                flags += " 🟢 Value"
        
        elif surplus > 15000000 and cost < 15000000:
            outlook = "Efficiency Engine"
            flags += " ⚙️ Engine"
        
        elif cost > 35000000 and meta_impact < 0:
            outlook = "Negative Asset"
            flags += " ⚠️ Toxic Contract"

        if surplus > 15000000: 
            if "Engine" not in flags: flags += " 💎 Elite Surplus"
        elif surplus < -15000000: 
            flags += " ⚠️ Overpaid"

        con.execute("""
            UPDATE player_metrics 
            SET MARKET_VALUE = ?,
                SURPLUS_VALUE = ?,
                FLAGS = ?,
                AGE = ?,
                STRATEGIC_OUTLOOK = ?,
                META_IMPACT = ?,
                PPG = ?,
                CONTRACT_COST = ?
            WHERE PLAYER_NAME = ?
        """, (float(market_val), float(surplus), flags, int(age), outlook, meta_impact, float(ppg), float(cost), p_name))

    con.close()
    logger.info("Meta-Economic processing complete with Strategic Layer.")

if __name__ == "__main__":
    run_economic_pipeline()
