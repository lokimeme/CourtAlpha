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

    # Calculate Total Points including Free Throws
    pts_query = f"""
        SELECT 
            PLAYER_NAME,
            SUM(CASE 
                WHEN ACTION_TYPE = 'Made Shot' THEN 
                    CASE WHEN SHOT_ZONE LIKE '%3' THEN 3 ELSE 2 END
                WHEN ACTION_TYPE = 'Free Throw' AND DESCRIPTION NOT LIKE 'MISS %' THEN 1
                ELSE 0 
            END) as TOTAL_PTS,
            COUNT(*) FILTER (WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot')) as FGA,
            SUM(CASE WHEN ACTION_TYPE = 'Made Shot' THEN 
                CASE WHEN SHOT_ZONE LIKE '%3' THEN 1.5 ELSE 1.0 END
                ELSE 0 END)::FLOAT / NULLIF(COUNT(*) FILTER (WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot')), 0) as EFG_PCT
        FROM play_by_play
        WHERE PLAYER_NAME IS NOT NULL
          AND SEASON = '{CURRENT_SEASON}'
          AND PLAYER_NAME NOT LIKE '%Putback%'
        GROUP BY PLAYER_NAME
    """
    pts_df = con.execute(pts_query).df()
    
    # Merge and filter
    eff_df = pts_df.merge(gp_df, on='PLAYER_NAME', how='inner')
    # Use 5 games / 50 FGA to keep stars like Curry
    eff_df = eff_df[(eff_df['GP'] >= 5) & (eff_df['FGA'] >= 50)]
    
    # NEW: Filter by Age (Exclude legacy/historic artifacts)
    logger.info("Purging legacy/historic players from active pool...")
    age_filter = """
        SELECT PLAYER_NAME 
        FROM player_metadata 
        WHERE date_diff('year', CAST(BIRTHDATE AS DATE), current_date) BETWEEN 18 AND 45
    """
    active_pool = con.execute(age_filter).df()['PLAYER_NAME'].tolist()
    eff_df = eff_df[eff_df['PLAYER_NAME'].isin(active_pool)]
    
    # Calculate real PPG (Cap GP at 82 to handle simulation artifacts)
    eff_df['PPG'] = eff_df['TOTAL_PTS'] / eff_df['GP'].clip(upper=82)
    
    # X_EFG_PCT needs a separate query or join to be safe
    xeff_query = f"""
        SELECT PLAYER_NAME, AVG(X_POINTS / CASE WHEN SHOT_ZONE LIKE '%3' THEN 3.0 ELSE 2.0 END) as X_EFG_PCT
        FROM play_by_play
        WHERE PLAYER_NAME IS NOT NULL AND ACTION_TYPE IN ('Made Shot', 'Missed Shot') AND SEASON = '{CURRENT_SEASON}'
        GROUP BY PLAYER_NAME
    """
    xeff_df = con.execute(xeff_query).df()
    eff_df = eff_df.merge(xeff_df, on='PLAYER_NAME', how='left').fillna(0)

    logger.info(f"Integrating impact for {len(eff_df)} active players...")
    
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
    
    feature_cols = [c for c in cluster_df.columns if 'FREQ' in c]
    features = cluster_df[feature_cols].fillna(0)
    
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)
    
    kmeans = KMeans(n_clusters=8, random_state=42, n_init=20)
    cluster_df['ARCHETYPE_ID'] = kmeans.fit_predict(scaled_features)

    # Dynamic Archetype Labeling v4.0 (Robust Heuristics)
    centroids = kmeans.cluster_centers_
    # Index order: 0:LOGO, 1:FLOATER, 2:LOB, 3:CUT, 4:POST, 5:SPOTUP, 6:ISOLATION, 7:RIM_PROT
    
    mapping = {}
    remaining_ids = list(range(8))
    
    # 1. Rim Protector: Highest RIM_PROT
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 7])]
    mapping[idx] = "Rim Protector"
    remaining_ids.remove(idx)
    
    # 2. Movement Shooter: Highest SPOTUP
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 5])]
    mapping[idx] = "Movement Shooter"
    remaining_ids.remove(idx)
    
    # 3. Floor General: Highest LOGO
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 0])]
    mapping[idx] = "Floor General"
    remaining_ids.remove(idx)
    
    # 4. Post Specialist: Highest POST
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 4])]
    mapping[idx] = "Post Specialist"
    remaining_ids.remove(idx)
    
    # 5. Self-Created Scorer: Highest ISOLATION
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 6])]
    mapping[idx] = "Self-Created Scorer"
    remaining_ids.remove(idx)
    
    # 6. High-Usage Slasher: Highest FLOATER
    idx = remaining_ids[np.argmax(centroids[remaining_ids, 1])]
    mapping[idx] = "High-Usage Slasher"
    remaining_ids.remove(idx)
    
    # 7. Two-Way Connector: Highest combined score of non-zero stats
    idx = remaining_ids[0]
    mapping[idx] = "Two-Way Connector"
    remaining_ids.remove(idx)

    # 8. Defensive Specialist: Last one
    mapping[remaining_ids[0]] = "Defensive Specialist"
    
    cluster_df['ARCHETYPE_NAME'] = cluster_df['ARCHETYPE_ID'].map(mapping)

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
    logger.info("Phase 2 ML Core successfully executed with accurate PPG and robust archetypes.")

if __name__ == "__main__":
    run_final_ml_pipeline()
