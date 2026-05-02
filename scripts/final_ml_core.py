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
    
    logger.info("Phase 2.1: Calculating Efficiency Metrics (eFG% vs xEFG%)...")
    
    efficiency_query = """
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
        GROUP BY PLAYER_NAME
        HAVING COUNT(*) > 20
    """
    eff_df = con.execute(efficiency_query).df()

    logger.info("Phase 2.2: Integrating RAPM and Skill-DNA...")
    
    rapm_df = con.execute("SELECT PLAYER_NAME, ADJUSTED_IMPACT FROM player_metrics").df()
    
    master_df = eff_df.merge(rapm_df, on='PLAYER_NAME', how='left').fillna(0)
    
    lmbda = 500
    master_df['SHRUNK_IMPACT'] = master_df['ADJUSTED_IMPACT'] * (master_df['FGA'] / (master_df['FGA'] + lmbda))

    logger.info("Phase 2.3: Skill-DNA Clustering...")
    skill_DNA = con.execute("""
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
        GROUP BY PLAYER_NAME
    """).df()
    
    cluster_df = master_df.merge(skill_DNA, on='PLAYER_NAME', how='inner')
    
    feature_cols = [c for c in cluster_df.columns if 'FREQ' in c] + ['SHRUNK_IMPACT', 'X_EFG_PCT']
    features = cluster_df[feature_cols].fillna(0)
    
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)
    
    archetypes = {
        0: "Elite Rim Protector",
        1: "3&D Wing",
        2: "Movement Shooter",
        3: "High-Usage Slasher",
        4: "Connector / High-IQ Big",
        5: "Point-of-Attack Defender",
        6: "Floor General",
        7: "Versatile Forward"
    }
    
    kmeans = KMeans(n_clusters=8, random_state=42, n_init=10)
    cluster_df['ARCHETYPE_ID'] = kmeans.fit_predict(scaled_features)
    cluster_df['ARCHETYPE_NAME'] = cluster_df['ARCHETYPE_ID'].map(archetypes)

    logger.info("Updating player_metrics table with high-fidelity scores...")
    
    con.execute("DROP TABLE IF EXISTS player_metrics")
    con.execute("""
        CREATE TABLE player_metrics (
            PLAYER_NAME VARCHAR PRIMARY KEY,
            FGA INTEGER,
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
            PLAYER_NAME, FGA, EFG_PCT, X_EFG_PCT, ADJUSTED_IMPACT, SHRUNK_IMPACT, ARCHETYPE_NAME,
            LOGO_FREQ, FLOATER_FREQ, POST_FREQ, SPOTUP_FREQ, ISOLATION_FREQ, RIM_PROT_FREQ
        FROM final_data
    """)

    con.close()
    logger.info("Phase 2 ML Core successfully executed.")

if __name__ == "__main__":
    run_final_ml_pipeline()
