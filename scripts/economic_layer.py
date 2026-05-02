import duckdb
import pandas as pd
import numpy as np
import logging
from scripts.utils import setup_logging, format_currency

DB_PATH = 'data/courtalpha.duckdb'
logger = setup_logging()

def calculate_market_value(meta_impact, dura_coeff, age=27):
    
    replacement_buffer = 2.0
    impact_over_replacement = meta_impact + replacement_buffer
    
    total_points = impact_over_replacement * 45.0 
    wins_added = total_points / 30.0
    
    REPLACEMENT_VAL = 1121428 
    
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

    if wins_added > 12:
        win_rate = 6500000
    elif wins_added > 8:
        win_rate = 5500000
    elif wins_added > 4:
        win_rate = 4500000
    else:
        win_rate = 3500000
    
    impact_value = wins_added * win_rate
    
    market_val = (REPLACEMENT_VAL + impact_value) * traj_multiplier * dura_coeff
    
    return max(REPLACEMENT_VAL, market_val)

def run_economic_pipeline():
    
    logger.info("Starting Meta-Adjusted Economic Layer (v2.5)...")
    con = duckdb.connect(DB_PATH)
    
    query = 
    df = con.execute(query).df()
    
    if df.empty:
        logger.warning("No metrics found.")
        return

    for idx, row in df.iterrows():
        p_name = row['PLAYER_NAME']
        age = row['CALC_AGE'] if not pd.isnull(row['CALC_AGE']) else 27 
        cost = row['CONTRACT_COST'] if row['CONTRACT_COST'] > 0 else 1121428
        arch = row['ARCHETYPE_NAME']
        
        meta_impact = row['META_IMPACT'] if not pd.isnull(row['META_IMPACT']) else 0.0
        market_val = calculate_market_value(meta_impact, 0.95, age)
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
        
        elif meta_impact < -1.0:
            outlook = "Replacement Candidate"
            flags += " ❌ Replacement"

        if surplus > 15000000: 
            if "Engine" not in flags: flags += " 💎 Elite Surplus"
        elif surplus < -15000000: 
            flags += " ⚠️ Overpaid"

        con.execute(, (float(market_val), float(surplus), flags, int(age), outlook, p_name))

    con.close()
    logger.info("Meta-Economic processing complete with Strategic Layer.")

if __name__ == "__main__":
    run_economic_pipeline()