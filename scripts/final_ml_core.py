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
                CASE WHEN SHOT_ZONE LIKE '%3' THEN 3 ELSE 2 END
                ELSE 0 END) as TOTAL_PTS,
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
    
    # Merge GP and filter by 5 games in the CURRENT season and 50 FGA
    eff_df = eff_df.merge(gp_df, on='PLAYER_NAME', how='inner')
    eff_df = eff_df[(eff_df['GP'] >= 5) & (eff_df['FGA'] >= 50)]
    
    # Calculate real PPG
    eff_df['PPG'] = eff_df['TOTAL_PTS'] / eff_df['GP']

    logger.info(f"Integrating impact for {len(eff_df)} active players...")
    
    # NEW: Pull from standalone player_impact table
    rapm_df = con.execute("SELECT PLAYER_NAME, ADJUSTED_IMPACT FROM player_impact").df()
    
    master_df = eff_df.merge(rapm_df, on='PLAYER_NAME', how='left').fillna(0)
    
    lmbda = 500
    master_df['SHRUNK_IMPACT'] = master_df['ADJUSTED_IMPACT'] * (master_df['FGA'] / (master_df['FGA'] + lmbda))

    logger.info("Phase 2.3: Skill-DNA Clustering (using recent playstyle)...")
    skill_DNA = con.execute(f"""
        SELECT 
            PLAYER_NAME,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Logo Range')::FLOAT / COUNT(*) as LOGO_FREQ,
            COUNT(*) FILTER (WHERE MICRO_ACTION = 'Floater / Touch')::FLOAT / COUNT(*) as FLOATER_FREQ,
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
    
    kmeans = KMeans(n_clusters=8, random_state=42, n_init=20)
    cluster_df['ARCHETYPE_ID'] = kmeans.fit_predict(scaled_features)

    # Dynamic Archetype Labeling
    centroids = kmeans.cluster_centers_
    # LOGO, FLOATER, POST, SPOTUP, ISOLATION, RIM_PROT
    
    mapping = {}
    remaining_ids = list(range(8))
    
    # 1. Floor General: Highest LOGO
    idx = np.argmax(centroids[:, 0])
    mapping[idx] = "Floor General"
    remaining_ids.remove(idx)
    
    # 2. Self-Created Scorer: Highest ISOLATION (among remaining)
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 4])]
    mapping[idx] = "Self-Created Scorer"
    remaining_ids.remove(idx)
    
    # 3. Post Specialist: Highest POST (among remaining)
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 2])]
    mapping[idx] = "Post Specialist"
    remaining_ids.remove(idx)
    
    # 4. Movement Shooter: Highest SPOTUP (among remaining)
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 3])]
    mapping[idx] = "Movement Shooter"
    remaining_ids.remove(idx)
    
    # 5. Defensive Specialist: Highest RIM_PROT (among remaining)
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 5])]
    mapping[idx] = "Defensive Specialist"
    remaining_ids.remove(idx)
    
    # 6. Two-Way Connector: Highest FLOATER (among remaining)
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 1])]
    mapping[idx] = "Two-Way Connector"
    remaining_ids.remove(idx)

    # 7. Rim Protector: Highest RIM_PROT (of last 2)
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 5])]
    mapping[idx] = "Rim Protector"
    remaining_ids.remove(idx)
    
    # 8. Interior Finisher: Last one
    mapping[remaining_ids[0]] = "Interior Finisher"
    
    cluster_df['ARCHETYPE_NAME'] = cluster_df['ARCHETYPE_ID'].map(mapping)

    logger.info("Updating player_metrics table with high-fidelity scores...")
    
    con.execute("DROP TABLE IF EXISTS player_metrics")
    con.execute("""
        CREATE TABLE player_metrics (
            PLAYER_NAME VARCHAR PRIMARY KEY,
            FGA INTEGER,
            GP INTEGER,
            PPG FLOAT,
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
            PLAYER_NAME, FGA, GP, PPG, EFG_PCT, X_EFG_PCT, ADJUSTED_IMPACT, SHRUNK_IMPACT, ARCHETYPE_NAME,
            LOGO_FREQ, FLOATER_FREQ, POST_FREQ, SPOTUP_FREQ, ISOLATION_FREQ, RIM_PROT_FREQ
        FROM final_data
    """)

    con.close()
    logger.info("Phase 2 ML Core successfully executed.")

if __name__ == "__main__":
    run_final_ml_pipeline()
