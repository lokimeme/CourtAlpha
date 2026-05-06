import duckdb
import pandas as pd
import numpy as np
import logging
import os
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FinalMLCore")

DB_PATH = 'data/courtalpha.duckdb'

def run_final_ml_pipeline():
    con = duckdb.connect(DB_PATH)
    
    CURRENT_SEASON = '2025-26'
    logger.info(f"Phase 2.1: Filtering for active players in {CURRENT_SEASON}...")
    
    # Calculate Current Season Games Played (GP)
    gp_query = f"""
        SELECT PLAYER_NAME, COUNT(DISTINCT GAME_ID) as GP
        FROM play_by_play
        WHERE PLAYER_NAME IS NOT NULL AND SEASON = '{CURRENT_SEASON}'
        GROUP BY PLAYER_NAME
    """
    gp_df = con.execute(gp_query).df()

    efficiency_query = f"""
        SELECT 
            PLAYER_NAME,
            COUNT(*) as FGA,
            SUM(CASE WHEN SHOT_MADE_FLAG = 1 THEN 
                CASE WHEN SHOT_ZONE LIKE '%3' THEN 1.5 ELSE 1.0 END
                ELSE 0 END) / COUNT(*) as EFG_PCT,
            SUM(X_POINTS / CASE WHEN SHOT_ZONE LIKE '%3' THEN 3.0 ELSE 2.0 END) / COUNT(*) as X_EFG_PCT
        FROM play_by_play
        WHERE PLAYER_NAME IS NOT NULL
          AND ACTION_TYPE IN ('Made Shot', 'Missed Shot')
          AND PLAYER_NAME NOT LIKE '%Putback%'
          AND SEASON = '{CURRENT_SEASON}'
        GROUP BY PLAYER_NAME
        HAVING COUNT(*) > 50
    """
    eff_df = con.execute(efficiency_query).df()
    
    # Merge GP and filter by 20 games in the CURRENT season and 100 FGA
    eff_df = eff_df.merge(gp_df, on='PLAYER_NAME', how='inner')
    eff_df = eff_df[(eff_df['GP'] >= 20) & (eff_df['FGA'] >= 100)]

    logger.info(f"Integrating impact for {len(eff_df)} active players...")
    
    rapm_df = con.execute("SELECT PLAYER_NAME, ADJUSTED_IMPACT FROM player_metrics").df()
    
    master_df = eff_df.merge(rapm_df, on='PLAYER_NAME', how='left').fillna(0)
    
    lmbda = 500
    master_df['SHRUNK_IMPACT'] = master_df['ADJUSTED_IMPACT'] * (master_df['FGA'] / (master_df['FGA'] + lmbda))

    logger.info("Phase 2.3: Skill-DNA Clustering (using recent playstyle)...")
    skill_DNA = con.execute(f"""
        SELECT 
            PLAYER_NAME,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Logo Range')::FLOAT / COUNT(*) as LOGO_FREQ,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Floater / Touch')::FLOAT / COUNT(*) as FLOATER_FREQ,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Lob Finish')::FLOAT / COUNT(*) as LOB_FREQ,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Off-Ball Cut')::FLOAT / COUNT(*) as CUT_FREQ,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Post-Up / Hook')::FLOAT / COUNT(*) as POST_FREQ,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Assisted 3PT')::FLOAT / COUNT(*) as SPOTUP_FREQ,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Self-Created (Space)')::FLOAT / COUNT(*) as ISOLATION_FREQ,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Interior Wall (Contest)')::FLOAT / COUNT(*) as RIM_PROT_FREQ
        FROM play_by_play
        WHERE PLAYER_NAME IS NOT NULL
          AND ACTION_TYPE IN ('Made Shot', 'Missed Shot')
          AND PLAYER_NAME NOT LIKE '%Putback%'
          AND SEASON >= '2024-25'
        GROUP BY PLAYER_NAME
    """).df()
    
    cluster_df = master_df.merge(skill_DNA, on='PLAYER_NAME', how='inner')
    
    # Archetype features should be style-based, NOT impact-based to avoid bias
    feature_cols = [c for c in cluster_df.columns if 'FREQ' in c]
    features = cluster_df[feature_cols].fillna(0)
    
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)
    
    # Refined Archetypes mapping based on centroid dominance
    archetypes = {
        0: "Self-Created Scorer", # High Isolation
        1: "Two-Way Connector",   # High Rim Prot, moderate everything
        2: "Interior Finisher",   # High Floater / Rim Freq
        3: "Defensive Specialist", # Low offense, High Rim Prot
        4: "Movement Shooter",    # High Spot-up
        5: "Post Specialist",     # High Post freq
        6: "Floor General",       # High Logo / Creation
        7: "Rim Protector"        # High Rim Prot, Low Spotup
    }
    
    kmeans = KMeans(n_clusters=8, random_state=42, n_init=20)
    cluster_df['ARCHETYPE_ID'] = kmeans.fit_predict(scaled_features)
    cluster_df['ARCHETYPE_NAME'] = cluster_df['ARCHETYPE_ID'].map(archetypes)

    logger.info("Updating player_metrics table with high-fidelity scores...")
    
    con.execute("DROP TABLE IF EXISTS player_metrics")
    con.execute("""
        CREATE TABLE player_metrics (
            PLAYER_NAME VARCHAR PRIMARY KEY,
            FGA INTEGER,
            GP INTEGER,
            EFG_PCT FLOAT,
            X_EFG_PCT FLOAT,
            ADJUSTED_IMPACT FLOAT,
            SHRUNK_IMPACT FLOAT,
            ARCHETYPE_NAME VARCHAR,
            LOGO_FREQ FLOAT,
            FLOATER_FREQ FLOAT,
            POST_FREQ FLOAT,
            SPOTUP_FREQ FLOAT,
            ISOLATION_FREQ FLOAT,
            RIM_PROT_FREQ FLOAT
        )
    """)
    
    con.register('final_data', cluster_df)
    con.execute("""
        INSERT INTO player_metrics 
        SELECT 
            PLAYER_NAME, FGA, GP, EFG_PCT, X_EFG_PCT, ADJUSTED_IMPACT, SHRUNK_IMPACT, ARCHETYPE_NAME,
            LOGO_FREQ, FLOATER_FREQ, POST_FREQ, SPOTUP_FREQ, ISOLATION_FREQ, RIM_PROT_FREQ
        FROM final_data
    """)

    con.close()
    logger.info("Phase 2 ML Core successfully executed.")

if __name__ == "__main__":
    run_final_ml_pipeline()
