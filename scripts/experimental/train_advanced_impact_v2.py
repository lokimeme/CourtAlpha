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
    query = 
    df = con.execute(query).df()
    
    if df.empty:
        logger.warning("No lineup-tagged shots found. Reconstruct more lineups first.")
        con.close()
        return

    logger.info(f"Training on {len(df)} shot events...")

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
        for j in range(1, 6): 
            p = getattr(row, f"OFF_{j}")
            if p in player_to_idx:
                rows.append(i)
                cols.append(player_to_idx[p])
                data.append(1)
                player_counts[p] += 1
        for j in range(1, 6):
            p = getattr(row, f"DEF_{j}")
            if p in player_to_idx:
                rows.append(i)
                cols.append(player_to_idx[p])
                data.append(-1)
                player_counts[p] += 1
                
    X = csr_matrix((data, (rows, cols)), shape=(num_events, num_players))
    y = df['SURPLUS'].values

    logger.info("Fitting Ridge Regression (Regularized Adjusted Plus-Minus)...")
    model = Ridge(alpha=2000)
    model.fit(X, y)

    impact_df = pd.DataFrame({
        'PLAYER_NAME': all_players,
        'ADJUSTED_SURPLUS_IMPACT': model.coef_,
        'EVENT_COUNT': [player_counts[p] for p in all_players]
    })

    impact_df.loc[impact_df['EVENT_COUNT'] < 50, 'ADJUSTED_SURPLUS_IMPACT'] = 0.0

    logger.info("Updating player_metrics with Adjusted Impact...")
    try:
        con.execute("ALTER TABLE player_metrics ADD COLUMN ADJUSTED_IMPACT FLOAT")
    except: pass

    con.register('temp_impact', impact_df)
    con.execute()
    
    con.unregister('temp_impact')
    con.close()
    
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump((model, all_players), MODEL_PATH)
    logger.info("Advanced Impact model training complete.")

if __name__ == "__main__":
    train_advanced_impact()