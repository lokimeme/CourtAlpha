import duckdb
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
import joblib
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AdvancedImpact")

DB_PATH = 'data/courtalpha.duckdb'
MODEL_PATH = 'scripts/models/advanced_impact.joblib'

def train_advanced_impact():
    con = duckdb.connect(DB_PATH)
    
    logger.info("Fetching possession-level surplus data...")
    query = """
    SELECT 
        GAME_ID,
        CASE 
            WHEN SHOT_ZONE IN ('Left Corner 3', 'Right Corner 3', 'Above the Break 3') THEN SHOT_MADE_FLAG * 3
            ELSE SHOT_MADE_FLAG * 2
        END - X_POINTS as SURPLUS,
        SEASON,
        OFF_1, OFF_2, OFF_3, OFF_4, OFF_5,
        DEF_1, DEF_2, DEF_3, DEF_4, DEF_5
    FROM play_by_play
    WHERE OFF_1 IS NOT NULL
      AND X_POINTS IS NOT NULL
      AND GARBAGE_TIME = FALSE
    """
    df = con.execute(query).df()
    
    if df.empty:
        logger.warning("No lineup-tagged shots found. Reconstruct more lineups first.")
        con.close()
        return

    season_weights = {
        '2025-26': 1.0,
        '2024-25': 0.9,
        '2023-24': 0.75,
        '2022-23': 0.6,
        '2021-22': 0.45,
        '2020-21': 0.35,
        '2019-20': 0.25,
        '2018-19': 0.2
    }
    df['WEIGHT'] = df['SEASON'].map(season_weights).fillna(0.1)

    logger.info(f"Training on {len(df)} shot events with Temporal Decay...")

    all_players_raw = pd.unique(df[[f"OFF_{i}" for i in range(1, 6)] + [f"DEF_{i}" for i in range(1, 6)]].values.ravel('K'))
    all_players = [p for p in all_players_raw if p is not None and isinstance(p, str)]
    player_to_idx = {player: i for i, player in enumerate(all_players)}
    
    num_events = len(df)
    num_players = len(all_players)
    
    from scipy.sparse import csr_matrix
    
    rows = []
    cols = []
    data = []
    
    player_counts = {p: 0 for p in all_players}
    
    for i, row in enumerate(df.itertuples()):
        w = row.WEIGHT
        for j in range(1, 6): 
            p = getattr(row, f"OFF_{j}")
            if p in player_to_idx:
                rows.append(i)
                cols.append(player_to_idx[p])
                data.append(w)
                player_counts[p] += 1
        for j in range(1, 6):
            p = getattr(row, f"DEF_{j}")
            if p in player_to_idx:
                rows.append(i)
                cols.append(player_to_idx[p])
                data.append(-w)
                player_counts[p] += 1
                
    X = csr_matrix((data, (rows, cols)), shape=(num_events, num_players))
    y = df['SURPLUS'].values * df['WEIGHT'].values

    logger.info("Fitting Ridge Regression (Regularized Adjusted Plus-Minus)...")
    model = Ridge(alpha=500)
    model.fit(X, y)

    coefs = model.coef_ * 100 

    impact_df = pd.DataFrame({
        'PLAYER_NAME': all_players,
        'ADJUSTED_SURPLUS_IMPACT': coefs,
        'EVENT_COUNT': [player_counts[p] for p in all_players]
    })

    logger.info("Updating player_metrics with Adjusted Impact...")
    try:
        con.execute("ALTER TABLE player_metrics ADD COLUMN ADJUSTED_IMPACT FLOAT")
    except: pass

    con.register('temp_impact', impact_df)
    con.execute("""
        UPDATE player_metrics
        SET ADJUSTED_IMPACT = temp_impact.ADJUSTED_SURPLUS_IMPACT
        FROM temp_impact
        WHERE player_metrics.PLAYER_NAME = temp_impact.PLAYER_NAME
    """)
    
    con.unregister('temp_impact')
    con.close()
    
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump((model, all_players), MODEL_PATH)
    logger.info("Advanced Impact model training complete.")

if __name__ == "__main__":
    train_advanced_impact()
