import duckdb
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
import joblib
import os

DB_PATH = 'data/courtalpha.duckdb'
MODEL_PATH = 'scripts/models/xp_model.joblib'

def train_xp_model():
    con = duckdb.connect(DB_PATH)
    
    print("Fetching training data (shots with location and results)...")
    # We use SHOT_MADE_FLAG as our target (0 or 1)
    df = con.execute("""
        SELECT 
            LOC_X, 
            LOC_Y, 
            SHOT_DISTANCE, 
            SHOT_ZONE, 
            PERIOD,
            CLOCK,
            SCORE_HOME,
            SCORE_AWAY,
            SHOT_MADE_FLAG
        FROM play_by_play 
        WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot') 
          AND LOC_X IS NOT NULL
          AND SHOT_MADE_FLAG IS NOT NULL
    """).df()

    if df.empty:
        print("Error: No data found for training.")
        return

    # Feature Engineering: Score Differential
    def get_diff(row):
        try:
            h = int(row['SCORE_HOME'] or 0)
            a = int(row['SCORE_AWAY'] or 0)
            return abs(h - a)
        except: return 10 # Default to non-clutch
        
    df['SCORE_DIFF'] = df.apply(get_diff, axis=1)

    print(f"Training on {len(df)} shots...")

    # Feature Engineering: Convert CLOCK (MM:SS) to total seconds remaining in period
    def clock_to_seconds(clock_str):
        if not isinstance(clock_str, str) or ':' not in clock_str:
            return 360 # Default to middle of quarter
        try:
            m, s = map(int, clock_str.split(':'))
            return m * 60 + s
        except:
            return 360

    df['SECONDS_REMAINING'] = df['CLOCK'].apply(clock_to_seconds)
    
    # Preprocessing: Convert SHOT_ZONE to dummy variables
    df = pd.get_dummies(df, columns=['SHOT_ZONE'])
    
    # Define features (including temporal and pressure ones)
    features = [c for c in df.columns if c not in ['SHOT_MADE_FLAG', 'CLOCK', 'GAME_ID', 'ACTION_NUMBER', 'SCORE_HOME', 'SCORE_AWAY']]
    X = df[features]
    y = df['SHOT_MADE_FLAG']

    # Train XGBoost Classifier
    model = XGBClassifier(
        n_estimators=150, # Increased capacity
        max_depth=6,      # Slightly deeper for temporal interactions
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X, y)

    # Ensure model directory exists
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump((model, features), MODEL_PATH.replace(".joblib", "_v2.joblib"))
    print(f"Enhanced model saved to {MODEL_PATH.replace('.joblib', '_v2.joblib')}")

    # Calculate Expected Points (xP)
    df['PROBABILITY'] = model.predict_proba(X)[:, 1]
    
    def get_points(row):
        # Precise 3PT identification based on Shot Zone
        three_pt_zones = [c for c in row.index if '3' in c and row[c] == 1]
        return 3 if three_pt_zones else 2

    df['X_POINTS'] = df['PROBABILITY'] * df.apply(get_points, axis=1)
    df['ACTUAL_POINTS'] = df['SHOT_MADE_FLAG'] * df.apply(get_points, axis=1)
    df['SURPLUS'] = df['ACTUAL_POINTS'] - df['X_POINTS']

    # Map zones to common archetypes for the UI
    def map_to_group(row):
        if row.get('SHOT_ZONE_Restricted Area', 0) == 1: return 'RIM'
        if any(row.get(f'SHOT_ZONE_{z}', 0) == 1 for z in ['In The Paint (Non-RA)', 'Mid-Range']): return 'MID'
        if any(row.get(f'SHOT_ZONE_{z}', 0) == 1 for z in ['Left Corner 3', 'Right Corner 3']): return 'CORNER_3'
        if row.get('SHOT_ZONE_Above the Break 3', 0) == 1: return 'ATB_3'
        return 'OTHER'

    df['ZONE_GROUP'] = df.apply(map_to_group, axis=1)

    print("Adding Zonal Metrics to database...")
    for zone in ['RIM', 'MID', 'CORNER_3', 'ATB_3']:
        try:
            con.execute(f"ALTER TABLE play_by_play ADD COLUMN XP_SURPLUS_{zone} FLOAT")
        except: pass

    # Prepare for bulk update
    ids = con.execute("""
        SELECT GAME_ID, ACTION_NUMBER 
        FROM play_by_play 
        WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot') 
          AND LOC_X IS NOT NULL
          AND SHOT_MADE_FLAG IS NOT NULL
    """).df()
    
    for zone in ['RIM', 'MID', 'CORNER_3', 'ATB_3']:
        ids[f'XP_SURPLUS_{zone}'] = np.where(df['ZONE_GROUP'] == zone, df['SURPLUS'], 0.0)

    print("Performing bulk update of Zonal Surplus...")
    con.register('temp_xp', ids)
    set_clause = ", ".join([f"XP_SURPLUS_{z} = temp_xp.XP_SURPLUS_{z}" for z in ['RIM', 'MID', 'CORNER_3', 'ATB_3']])
    con.execute(f"""
        UPDATE play_by_play
        SET X_POINTS = temp_xp.X_POINTS,
            {set_clause}
        FROM temp_xp
        WHERE play_by_play.GAME_ID = temp_xp.GAME_ID
          AND play_by_play.ACTION_NUMBER = temp_xp.ACTION_NUMBER
    """)
    
    con.unregister('temp_xp')
    con.close()
    print("xP Model training and application complete.")

if __name__ == "__main__":
    train_xp_model()
