import duckdb
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
import joblib
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AdvancedImpact")

DB_PATH = 'data/courtalpha.duckdb'
MODEL_PATH = 'scripts/models/advanced_impact.joblib'

def train_advanced_impact():
    con = duckdb.connect(DB_PATH)
    
    logger.info("Fetching possession-level surplus data...")
    # We only want events where we have full lineup data
    # Result = Actual Points - xPoints
    query = """
    SELECT 
        GAME_ID,
        CASE 
            WHEN SHOT_ZONE IN ('Left Corner 3', 'Right Corner 3', 'Above the Break 3') THEN SHOT_MADE_FLAG * 3
            ELSE SHOT_MADE_FLAG * 2
        END - X_POINTS as SURPLUS,
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

    logger.info(f"Training on {len(df)} shot events...")

    # Build Sparse Matrix
    # Players are features. 
    # Offensive players get +1, Defensive players get -1.
    all_players = pd.unique(df[[f"OFF_{i}" for i in range(1, 6)] + [f"DEF_{i}" for i in range(1, 6)]].values.ravel('K'))
    all_players = [p for p in all_players if p is not None]
    player_to_idx = {player: i for i, player in enumerate(all_players)}
    
    num_events = len(df)
    num_players = len(all_players)
    
    from scipy.sparse import csr_matrix
    
    rows = []
    cols = []
    data = []
    
    for i, row in enumerate(df.itertuples()):
        # Offense
        for j in range(3, 8): # OFF_1 to OFF_5
            p = getattr(row, f"OFF_{j-2}")
            if p in player_to_idx:
                rows.append(i)
                cols.append(player_to_idx[p])
                data.append(1)
        # Defense
        for j in range(8, 13): # DEF_1 to DEF_5
            p = getattr(row, f"DEF_{j-7}")
            if p in player_to_idx:
                rows.append(i)
                cols.append(player_to_idx[p])
                data.append(-1)
                
    X = csr_matrix((data, (rows, cols)), shape=(num_events, num_players))
    y = df['SURPLUS'].values

    logger.info("Fitting Ridge Regression (Regularized Adjusted Plus-Minus)...")
    # alpha is the regularization strength. 
    # High alpha = more shrinkage to 0.
    model = Ridge(alpha=1000) 
    model.fit(X, y)

    # Extract Results
    impact_df = pd.DataFrame({
        'PLAYER_NAME': all_players,
        'ADJUSTED_SURPLUS_IMPACT': model.coef_
    })

    # Update player_metrics
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
    
    # Save model for later use
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump((model, all_players), MODEL_PATH)
    logger.info("Advanced Impact model training complete.")

if __name__ == "__main__":
    train_advanced_impact()
