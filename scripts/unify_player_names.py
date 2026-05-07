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
    # Preserve suffixes but strip edges
    return name.strip()

def unify_player_names():
    con = duckdb.connect(DB_PATH)
    logger.info("Starting Player Name Unification...")

    # Manual Overrides for common abbreviations in PBP
    manual_overrides = {
        'St. Curry': 'Stephen Curry',
        'Se. Curry': 'Seth Curry',
        'L. Doncic': 'Luka Doncic',
        'Le. James': 'LeBron James',
        'K. Durant': 'Kevin Durant',
        'J. Embiid': 'Joel Embiid',
        'G. Antetokounmpo': 'Giannis Antetokounmpo',
        'S. Gilgeous-Alexander': 'Shai Gilgeous-Alexander',
        'Ja. Williams': 'Jalen Williams',
        'Jal. Williams': 'Jalen Williams',
        'Jay. Williams': 'Jaylin Williams',
        'M. Porter Jr.': 'Michael Porter Jr.',
        'K. Towns': 'Karl-Anthony Towns',
        'D. Sabonis': 'Domantas Sabonis'
    }

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

    # We pull from play_by_play directly to fix the source
    raw_players = con.execute("SELECT DISTINCT PLAYER_NAME FROM play_by_play WHERE PLAYER_NAME IS NOT NULL").df()['PLAYER_NAME'].tolist()
    
    updates = []
    success_count = 0
    
    for p in raw_players:
        if p in manual_overrides:
            updates.append((manual_overrides[p], p))
            success_count += 1
            continue

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
        logger.info(f"Applying {len(updates)} name unifications to source tables...")
        up_df = pd.DataFrame(updates, columns=['NEW', 'OLD'])
        con.register('temp_unify', up_df)
        
        logger.info("Updating play_by_play table...")
        con.execute("""
            UPDATE play_by_play
            SET PLAYER_NAME = temp_unify.NEW
            FROM temp_unify
            WHERE play_by_play.PLAYER_NAME = temp_unify.OLD
        """)
        con.unregister('temp_unify')
    
    con.close()
    logger.info(f"Unification complete. Fixed {success_count} names.")

if __name__ == "__main__":
    unify_player_names()
