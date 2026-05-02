import duckdb
import pandas as pd
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MicroActions")

DB_PATH = 'data/courtalpha.duckdb'

def populate_micro_actions():
    con = duckdb.connect(DB_PATH)
    
    logger.info("Starting Master Micro-Action Tagging (v3.0 - Robust Multi-Factor)...")

    logger.info("Step 1: Identifying Creation Context...")
    con.execute()

    logger.info("Step 2: Enriching with Skill-Specific details (Floaters, Post-ups, Logo)...")
    
    con.execute("UPDATE play_by_play SET MICRO_ACTION = 'Logo Range' WHERE SHOT_DISTANCE >= 28 AND ACTION_TYPE IN ('Made Shot', 'Missed Shot')")
    
    con.execute()

    con.execute()

    logger.info("Step 3: Overlaying Defensive Context...")
    
    con.execute()

    logger.info("Tagging And-1 Opportunities (Fixed Logic)...")
    con.execute()

    logger.info("Applying Interior Wall logic...")
    def height_to_inches(h):
        if not h or '-' not in str(h): return 0
        try:
            f, i = str(h).split('-')
            if f.isdigit() and i.isdigit():
                return int(f) * 12 + int(i)
        except: pass
        return 0

    metadata = con.execute("SELECT PLAYER_NAME, HEIGHT FROM player_metadata").df()
    metadata['HEIGHT_INCHES'] = metadata['HEIGHT'].apply(height_to_inches)
    
    height_map = {}
    for _, row in metadata.iterrows():
        full_name = row['PLAYER_NAME']
        h = row['HEIGHT_INCHES']
        height_map[full_name] = h
        parts = full_name.split()
        if len(parts) >= 2:
            init_name = f"{parts[0][0]}. {' '.join(parts[1:])}"
            height_map[init_name] = h

    rim_shots = con.execute().df()

    if not rim_shots.empty:
        updates = []
        for _, row in rim_shots.iterrows():
            defenders = [row[f'DEF_{i}'] for i in range(1, 6)]
            tallest = None
            max_h = 0
            for d in defenders:
                if not d: continue
                h = height_map.get(d, 0)
                if h > max_h:
                    max_h = h
                    tallest = d
            if tallest:
                updates.append((tallest, row['GAME_ID'], row['ACTION_NUMBER']))

        if updates:
            up_df = pd.DataFrame(updates, columns=['TALLEST_DEF', 'GAME_ID', 'ACTION_NUMBER'])
            con.register('temp_rim', up_df)
            con.execute()
            con.unregister('temp_rim')

    con.close()
    logger.info("Micro-Action tagging v3.0 complete.")

if __name__ == "__main__":
    populate_micro_actions()