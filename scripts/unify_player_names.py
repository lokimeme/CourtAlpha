import duckdb
import pandas as pd
import logging
import unicodedata
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UnifyNames")

DB_PATH = 'data/courtalpha.duckdb'

def normalize_name(name):
    if not name: return ""
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'\s+(Jr\.|III|II|IV|Sr\.)$', '', name)
    return name.strip()

def unify_player_names():
    con = duckdb.connect(DB_PATH)
    logger.info("Starting Player Name Unification...")

    # 1. Get all unique metadata names
    meta_df = con.execute("SELECT PLAYER_NAME FROM player_metadata").df()
    meta_names = meta_df['PLAYER_NAME'].tolist()
    
    # Create matching maps
    # Full Name -> Full Name (Self)
    # I. Lastname -> Full Name
    # Lastname -> Full Name (Only if unique)
    
    match_map = {}
    last_name_buckets = {}
    
    for full_name in meta_names:
        norm_full = normalize_name(full_name)
        match_map[norm_full] = full_name
        
        parts = norm_full.split()
        if len(parts) >= 2:
            init_name = f"{parts[0][0]}. {' '.join(parts[1:])}"
            match_map[init_name] = full_name
            
            last_name = parts[-1]
            if last_name not in last_name_buckets:
                last_name_buckets[last_name] = []
            last_name_buckets[last_name].append(full_name)

    # 2. Get current metrics names
    metrics_players = con.execute("SELECT PLAYER_NAME FROM player_metrics").df()['PLAYER_NAME'].tolist()
    
    updates = []
    success_count = 0
    
    for p in metrics_players:
        norm_p = normalize_name(p)
        
        # Priority 1: Direct or Initial Match
        if norm_p in match_map:
            new_name = match_map[norm_p]
            if new_name != p:
                updates.append((new_name, p))
                success_count += 1
            continue
            
        # Priority 2: Unique Last Name Match
        if norm_p in last_name_buckets and len(last_name_buckets[norm_p]) == 1:
            new_name = last_name_buckets[norm_p][0]
            if new_name != p:
                updates.append((new_name, p))
                success_count += 1
            continue

    if updates:
        logger.info(f"Applying {len(updates)} name unifications...")
        up_df = pd.DataFrame(updates, columns=['NEW', 'OLD'])
        con.register('temp_unify', up_df)
        
        # 1. Update play_by_play (Do this FIRST so we can re-calculate metrics if needed)
        logger.info("Updating play_by_play table...")
        con.execute("""
            UPDATE play_by_play
            SET PLAYER_NAME = temp_unify.NEW
            FROM temp_unify
            WHERE play_by_play.PLAYER_NAME = temp_unify.OLD
        """)

        # 2. Merge player_metrics (Aggregate then replace)
        logger.info("Merging player_metrics...")
        # Create a new table with aggregated data
        con.execute("""
            CREATE TABLE player_metrics_new AS
            SELECT 
                COALESCE(u.NEW, m.PLAYER_NAME) as PLAYER_NAME,
                SUM(FGA) as FGA,
                AVG(EFG_PCT) as EFG_PCT,
                AVG(X_EFG_PCT) as X_EFG_PCT,
                AVG(ADJUSTED_IMPACT) as ADJUSTED_IMPACT,
                AVG(SHRUNK_IMPACT) as SHRUNK_IMPACT,
                MAX(ARCHETYPE_NAME) as ARCHETYPE_NAME,
                MAX(LOGO_FREQ) as LOGO_FREQ,
                MAX(FLOATER_FREQ) as FLOATER_FREQ,
                MAX(POST_FREQ) as POST_FREQ,
                MAX(SPOTUP_FREQ) as SPOTUP_FREQ,
                MAX(ISOLATION_FREQ) as ISOLATION_FREQ,
                MAX(RIM_PROT_FREQ) as RIM_PROT_FREQ,
                MAX(CONTRACT_COST) as CONTRACT_COST,
                MAX(MARKET_VALUE) as MARKET_VALUE,
                MAX(SURPLUS_VALUE) as SURPLUS_VALUE,
                MAX(FLAGS) as FLAGS,
                MAX(AGE) as AGE
            FROM player_metrics m
            LEFT JOIN temp_unify u ON m.PLAYER_NAME = u.OLD
            GROUP BY 1
        """)
        
        con.execute("DROP TABLE player_metrics")
        con.execute("ALTER TABLE player_metrics_new RENAME TO player_metrics")
        
        con.unregister('temp_unify')
    
    con.close()
    logger.info(f"Unification complete. Fixed {success_count} names.")

if __name__ == "__main__":
    unify_player_names()
