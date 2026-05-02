import duckdb
import pandas as pd
import numpy as np
try:
    from utils import shrink_value
except ImportError:
    from scripts.utils import shrink_value

DB_PATH = 'data/courtalpha.duckdb'

def generate_talent_profiles():
    con = duckdb.connect(DB_PATH)
    
    print("Calculating Scoring Value (Surplus Points)...")
    scoring_query = 
    scoring_df = con.execute(scoring_query).df()
    
    print("Calculating Creation Value (Assisted xPoints)...")
    creation_query = 
    creation_df = con.execute(creation_query).df()

    print("Calculating Defensive Value (Suppressed xPoints)...")
    defense_query = 
    defense_df = con.execute(defense_query).df()

    df = pd.merge(scoring_df, creation_df, on='PLAYER_NAME', how='outer')
    df = pd.merge(df, defense_df, on='PLAYER_NAME', how='outer').fillna(0)

    print(f"Calculating holistic metrics for {len(df)} players...")
    
    df['SCORING_SURPLUS'] = df['TOTAL_POINTS'] - df['TOTAL_X_POINTS']
    
    df['TOTAL_OFFENSIVE_IMPACT'] = df['SCORING_SURPLUS'] + df['CREATION_VALUE']
    
    df['TOTAL_IMPACT'] = df['TOTAL_OFFENSIVE_IMPACT'] + df['DEFENSIVE_VALUE']
    
    df['SAMPLE_SIZE'] = df['FGA'] + df['ASSISTS'] + df['DEFENSIVE_STOPS']
    df['SHRUNK_TOTAL_IMPACT'] = df.apply(
        lambda row: shrink_value(row['TOTAL_IMPACT'], row['SAMPLE_SIZE'], prior=0.0, lmbda=300), 
        axis=1
    )

    print("Updating player_metrics table...")
    con.register('temp_metrics', df)
    con.execute("DROP TABLE IF EXISTS player_metrics")
    con.execute()
    con.execute()
    
    con.unregister('temp_metrics')
    con.close()
    print("Holistic talent profiling complete.")

if __name__ == "__main__":
    generate_talent_profiles()