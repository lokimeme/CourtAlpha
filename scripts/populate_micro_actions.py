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

    # 1. INITIAL BROAD CATEGORIZATION (creation context)
    logger.info("Step 1: Identifying Creation Context...")
    con.execute("""
        UPDATE play_by_play
        SET MICRO_ACTION = CASE 
            WHEN ASSISTER_NAME IS NOT NULL AND SHOT_ZONE LIKE '%3' THEN 'Assisted 3PT'
            WHEN ASSISTER_NAME IS NOT NULL THEN 'Assisted Bucket'
            WHEN SUB_TYPE LIKE '%Alley Oop%' THEN 'Lob Finish'
            WHEN SUB_TYPE LIKE '%Cutting%' THEN 'Off-Ball Cut'
            WHEN SUB_TYPE LIKE '%Putback%' OR DESCRIPTION LIKE '%Putback%' THEN 'Second Chance'
            WHEN SUB_TYPE IN ('Pullup Jump shot', 'Step Back Jump shot', 'Fadeaway Jump Shot') THEN 'Self-Created (Space)'
            WHEN SUB_TYPE LIKE 'Driving%' THEN 'Self-Created (Drive)'
            ELSE 'Standard Action'
        END
        WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot')
    """)

    # 2. ENRICH WITH SKILL-SPECIFIC DATA (without overwriting context)
    # We use || to append if it's high-value, or just update generic actions
    logger.info("Step 2: Enriching with Skill-Specific details (Floaters, Post-ups, Logo)...")
    
    # Identify Logo Range
    con.execute("UPDATE play_by_play SET MICRO_ACTION = 'Logo Range' WHERE SHOT_DISTANCE >= 28 AND ACTION_TYPE IN ('Made Shot', 'Missed Shot')")
    
    # Identify Floaters
    con.execute("""
        UPDATE play_by_play 
        SET MICRO_ACTION = 'Floater / Touch' 
        WHERE SUB_TYPE LIKE '%Floating%' 
          AND MICRO_ACTION NOT IN ('Assisted 3PT', 'Assisted Bucket', 'Lob Finish')
    """)

    # Identify Post-Ups
    con.execute("""
        UPDATE play_by_play 
        SET MICRO_ACTION = 'Post-Up / Hook' 
        WHERE (SUB_TYPE LIKE '%Hook%' OR SUB_TYPE LIKE '%Turnaround%') 
          AND MICRO_ACTION NOT IN ('Assisted 3PT', 'Assisted Bucket', 'Self-Created (Space)')
    """)

    # 3. OVERLAY DEFENSIVE CONTEXT (Physical Contests & Interior Wall)
    logger.info("Step 3: Overlaying Defensive Context...")
    
    # 3a. Foul Contests (Foul within 1 second of miss)
    # We already have some tagged, but let's re-run carefully with Game ID join
    con.execute("""
        UPDATE play_by_play
        SET MICRO_ACTION = 'Physical Contest (Foul)'
        WHERE GAME_ID || ACTION_NUMBER IN (
            SELECT p1.GAME_ID || p1.ACTION_NUMBER
            FROM play_by_play p1
            JOIN play_by_play p2 ON p1.GAME_ID = p2.GAME_ID 
              AND p2.ACTION_NUMBER > p1.ACTION_NUMBER
              AND p2.ACTION_NUMBER < p1.ACTION_NUMBER + 5
              AND p1.PERIOD = p2.PERIOD
            WHERE p1.ACTION_TYPE = 'Missed Shot'
              AND p2.ACTION_TYPE = 'Foul'
              AND p2.SUB_TYPE IN ('Personal', 'Shooting', 'Loose Ball')
        )
    """)

    # 3b. And-1 Detection (FIXED: Game-specific join)
    logger.info("Tagging And-1 Opportunities (Fixed Logic)...")
    con.execute("""
        UPDATE play_by_play
        SET MICRO_ACTION = 'And-1 Effort'
        WHERE ACTION_TYPE = 'Made Shot'
          AND EXISTS (
              SELECT 1 FROM play_by_play p2 
              WHERE p2.GAME_ID = play_by_play.GAME_ID 
              AND p2.ACTION_NUMBER > play_by_play.ACTION_NUMBER
              AND p2.ACTION_NUMBER < play_by_play.ACTION_NUMBER + 5
              AND p2.ACTION_TYPE = 'Foul'
          )
    """)

    # 3c. Interior Wall (Tallest defender on rim miss)
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

    rim_shots = con.execute("""
        SELECT GAME_ID, ACTION_NUMBER, DEF_1, DEF_2, DEF_3, DEF_4, DEF_5
        FROM play_by_play
        WHERE SHOT_DISTANCE <= 4
          AND ACTION_TYPE = 'Missed Shot'
          AND (MICRO_ACTION IS NULL OR MICRO_ACTION IN ('Standard Action', 'Self-Created (Drive)'))
    """).df()

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
            con.execute("""
                UPDATE play_by_play
                SET DEFENDER_NAME = temp_rim.TALLEST_DEF,
                    MICRO_ACTION = 'Interior Wall (Contest)'
                FROM temp_rim
                WHERE play_by_play.GAME_ID = temp_rim.GAME_ID
                  AND play_by_play.ACTION_NUMBER = temp_rim.ACTION_NUMBER
            """)
            con.unregister('temp_rim')

    con.close()
    logger.info("Micro-Action tagging v3.0 complete.")

if __name__ == "__main__":
    populate_micro_actions()
