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

    print(f"Training on {len(df)} shots...")

    df = pd.get_dummies(df, columns=['SHOT_ZONE', 'MICRO_ACTION'])
    
    X = df.drop('SHOT_MADE_FLAG', axis=1)
    y = df['SHOT_MADE_FLAG']

    model = XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump((model, X.columns.tolist()), MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

    df['PROBABILITY'] = model.predict_proba(X)[:, 1]
    
    def get_points(row):
        three_pt_zones = ['SHOT_ZONE_Left Corner 3', 'SHOT_ZONE_Right Corner 3', 'SHOT_ZONE_Above the Break 3']
        for zone in three_pt_zones:
            if zone in row and row[zone] == 1:
                return 3
        return 2

    df['X_POINTS'] = df['PROBABILITY'] * df.apply(get_points, axis=1)

    print("Adding X_POINTS column to database...")
    try:
        con.execute("ALTER TABLE play_by_play ADD COLUMN X_POINTS FLOAT")
    except: pass

    ids = con.execute().df()
    
    ids['X_POINTS'] = df['X_POINTS']

    print("Performing bulk update of X_POINTS...")
    con.register('temp_xp', ids)
    con.execute()
    
    con.unregister('temp_xp')
    con.close()
    print("xP Model training and application complete.")

if __name__ == "__main__":
    train_xp_model()