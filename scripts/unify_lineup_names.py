import duckdb
import pandas as pd
import logging
import unicodedata
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GlobalLineupUnify")

DB_PATH = 'data/courtalpha.duckdb'

def normalize_name(name):
    if not name: return ""
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'\s+(Jr\.|III|II|IV|Sr\.)$', '', name)
    return name.strip()

def unify_lineups():
    con = duckdb.connect(DB_PATH)
    logger.info("Starting Global Lineup Name Unification (Full Database)...")

    # 1. Create the master mapping (Initial Name -> Full Name)
    meta_df = con.execute("SELECT PLAYER_NAME FROM player_metadata").df()
    match_map = {}
    for full_name in meta_df['PLAYER_NAME']:
        norm_full = normalize_name(full_name)
        parts = norm_full.split()
        if len(parts) >= 2:
            init_name = f"{parts[0][0]}. {' '.join(parts[1:])}"
            match_map[init_name] = full_name

    # 2. Update each of the 10 lineup columns
    columns = [f'OFF_{i}' for i in range(1, 6)] + [f'DEF_{i}' for i in range(1, 6)]
    
    # We'll use a temporary mapping table for high performance
    map_df = pd.DataFrame(list(match_map.items()), columns=['OLD', 'NEW'])
    con.register('name_map_table', map_df)
    
    for col in columns:
        logger.info(f"Unifying names in {col}...")
        con.execute(f"""
            UPDATE play_by_play
            SET {col} = name_map_table.NEW
            FROM name_map_table
            WHERE play_by_play.{col} = name_map_table.OLD
        """)
        
    con.unregister('name_map_table')
    con.close()
    logger.info("Global Lineup Unification Complete.")

if __name__ == "__main__":
    unify_lineups()
