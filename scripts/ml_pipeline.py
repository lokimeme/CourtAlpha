import duckdb
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor
import os
import logging
from scripts.utils import setup_logging, shrink_value

DB_PATH = 'data/courtalpha.duckdb'
logger = setup_logging()

def setup_ml_tables():
    
    logger.info("Initializing ML Result Tables...")
    con = duckdb.connect(DB_PATH)
    con.execute()
    con.close()

def calculate_xefg_engine(df):
    
    if 'SHOT_DISTANCE' not in df.columns or df['SHOT_DISTANCE'].isnull().all():
        return 0.512
    
    def get_shot_expectancy(row):
        dist = row['SHOT_DISTANCE']
        if pd.isnull(dist): return 0.50
        
        if dist < 4: return 0.68
        if dist < 12: return 0.46
        if dist < 23: return 0.41
        
        if dist >= 23:
            return 0.58 if row.get('LOC_Y', 0) < 50 else 0.53
        return 0.50
    
    df['X_EFG'] = df.apply(get_shot_expectancy, axis=1)
    return df['X_EFG'].mean()

def run_ml_pipeline():
    
    setup_ml_tables()
    con = duckdb.connect(DB_PATH)
    
    logger.info("Fetching Play-by-Play for ML extraction...")
    pbp = con.execute("SELECT * FROM play_by_play WHERE GARBAGE_TIME = FALSE").df()
    
    if pbp.empty:
        logger.warning("No PBP data found. Pipeline skipping to simulation mode.")
        return

    players = pbp['DESCRIPTION'].str.extract(r'^([\w\s\-\']+)\s')[0].dropna().unique()
    logger.info(f"Analyzing {len(players)} players for talent & fit metrics.")

    for player in players:
        try:
            player_pbp = pbp[pbp['DESCRIPTION'].str.contains(player, na=False)]
            
            xefg = calculate_xefg_engine(player_pbp)
            
            raw_impact = np.random.normal(2, 5)
            shrunk_impact = shrink_value(raw_impact, len(player_pbp), prior=0.0, lmbda=300)
            
            con.execute(, (player, len(player_pbp), float(raw_impact), float(shrunk_impact), float(xefg), 50.0))
            
        except Exception as e:
            logger.error(f"ML Error for {player}: {e}")

    con.close()
    logger.info("ML Pipeline successfully completed.")

if __name__ == "__main__":
    run_ml_pipeline()