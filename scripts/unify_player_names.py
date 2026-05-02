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

    meta_df = con.execute("SELECT PLAYER_NAME FROM player_metadata").df()
    meta_names = meta_df['PLAYER_NAME'].tolist()
    
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

    metrics_players = con.execute("SELECT PLAYER_NAME FROM player_metrics").df()['PLAYER_NAME'].tolist()
    
    updates = []
    success_count = 0
    
    for p in metrics_players:
        norm_p = normalize_name(p)
        
        if norm_p in match_map:
            new_name = match_map[norm_p]
            if new_name != p:
                updates.append((new_name, p))
                success_count += 1
            continue
            
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
        
        logger.info("Updating play_by_play table...")
        con.execute()

        logger.info("Merging player_metrics...")
        con.execute()
        
        con.execute("DROP TABLE player_metrics")
        con.execute("ALTER TABLE player_metrics_new RENAME TO player_metrics")
        
        con.unregister('temp_unify')
    
    con.close()
    logger.info(f"Unification complete. Fixed {success_count} names.")

if __name__ == "__main__":
    unify_player_names()