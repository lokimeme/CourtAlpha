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
    df = con.execute().df()

    if df.empty:
        print("Error: No data found for training.")
        return

    def get_diff(row):
        try:
            h = int(row['SCORE_HOME'] or 0)
            a = int(row['SCORE_AWAY'] or 0)
            return abs(h - a)
        except: return 10
        
    df['SCORE_DIFF'] = df.apply(get_diff, axis=1)

    print(f"Training on {len(df)} shots...")

    def clock_to_seconds(clock_str):
        if not isinstance(clock_str, str) or ':' not in clock_str:
            return 360
        try:
            m, s = map(int, clock_str.split(':'))
            return m * 60 + s
        except:
            return 360

    df['SECONDS_REMAINING'] = df['CLOCK'].apply(clock_to_seconds)
    
    df = pd.get_dummies(df, columns=['SHOT_ZONE'])
    
    features = [c for c in df.columns if c not in ['SHOT_MADE_FLAG', 'CLOCK', 'GAME_ID', 'ACTION_NUMBER', 'SCORE_HOME', 'SCORE_AWAY']]
    X = df[features]
    y = df['SHOT_MADE_FLAG']

    model = XGBClassifier(
        n_estimators=150,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump((model, features), MODEL_PATH.replace(".joblib", "_v2.joblib"))
    print(f"Enhanced model saved to {MODEL_PATH.replace('.joblib', '_v2.joblib')}")

    df['PROBABILITY'] = model.predict_proba(X)[:, 1]
    
    def get_points(row):
        three_pt_zones = [c for c in row.index if '3' in c and row[c] == 1]
        return 3 if three_pt_zones else 2

    df['X_POINTS'] = df['PROBABILITY'] * df.apply(get_points, axis=1)
    df['ACTUAL_POINTS'] = df['SHOT_MADE_FLAG'] * df.apply(get_points, axis=1)
    df['SURPLUS'] = df['ACTUAL_POINTS'] - df['X_POINTS']

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

    ids = con.execute().df()
    
    for zone in ['RIM', 'MID', 'CORNER_3', 'ATB_3']:
        ids[f'XP_SURPLUS_{zone}'] = np.where(df['ZONE_GROUP'] == zone, df['SURPLUS'], 0.0)

    print("Performing bulk update of Zonal Surplus...")
    con.register('temp_xp', ids)
    set_clause = ", ".join([f"XP_SURPLUS_{z} = temp_xp.XP_SURPLUS_{z}" for z in ['RIM', 'MID', 'CORNER_3', 'ATB_3']])
    con.execute(f)
    
    con.unregister('temp_xp')
    con.close()
    print("xP Model training and application complete.")

if __name__ == "__main__":
    train_xp_model()