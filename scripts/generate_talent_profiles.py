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
    scoring_query = """
        SELECT 
            PLAYER_NAME,
            COUNT(*) as FGA,
            SUM(CASE 
                WHEN SHOT_ZONE IN ('Left Corner 3', 'Right Corner 3', 'Above the Break 3') THEN SHOT_MADE_FLAG * 3
                ELSE SHOT_MADE_FLAG * 2
            END) as TOTAL_POINTS,
            SUM(X_POINTS) as TOTAL_X_POINTS
        FROM play_by_play 
        WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot')
          AND PLAYER_NAME IS NOT NULL
          AND X_POINTS IS NOT NULL
        GROUP BY PLAYER_NAME
    """
    scoring_df = con.execute(scoring_query).df()
    
    print("Calculating Creation Value (Assisted xPoints)...")
    creation_query = """
        SELECT 
            ASSISTER_NAME as PLAYER_NAME,
            COUNT(*) as ASSISTS,
            SUM(X_POINTS) as CREATION_VALUE
        FROM play_by_play 
        WHERE ASSISTER_NAME IS NOT NULL
          AND X_POINTS IS NOT NULL
        GROUP BY ASSISTER_NAME
    """
    creation_df = con.execute(creation_query).df()

    print("Calculating Defensive Value (Suppressed xPoints)...")
    defense_query = """
        SELECT 
            DEFENDER_NAME as PLAYER_NAME,
            COUNT(*) as DEFENSIVE_STOPS,
            SUM(X_POINTS) as DEFENSIVE_VALUE
        FROM play_by_play 
        WHERE DEFENDER_NAME IS NOT NULL
          AND X_POINTS IS NOT NULL
        GROUP BY DEFENDER_NAME
    """
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
    con.execute("""
        CREATE TABLE player_metrics (
            PLAYER_NAME VARCHAR PRIMARY KEY,
            FGA INTEGER,
            ASSISTS INTEGER,
            DEFENSIVE_STOPS INTEGER,
            TOTAL_POINTS FLOAT,
            SCORING_SURPLUS FLOAT,
            CREATION_VALUE FLOAT,
            DEFENSIVE_VALUE FLOAT,
            TOTAL_IMPACT FLOAT,
            SHRUNK_TOTAL_IMPACT FLOAT
        )
    """)
    con.execute("""
        INSERT INTO player_metrics 
        SELECT 
            PLAYER_NAME, FGA, ASSISTS, DEFENSIVE_STOPS, TOTAL_POINTS, 
            SCORING_SURPLUS, CREATION_VALUE, DEFENSIVE_VALUE, 
            TOTAL_IMPACT, SHRUNK_TOTAL_IMPACT 
        FROM temp_metrics
    """)
    
    con.unregister('temp_metrics')
    con.close()
    print("Holistic talent profiling complete.")

if __name__ == "__main__":
    generate_talent_profiles()
