import duckdb
import pandas as pd
import logging
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TrueDefenders")

DB_PATH = 'data/courtalpha.duckdb'

def populate_foul_contests():
    con = duckdb.connect(DB_PATH)

    logger.info("Searching for missed shots followed by fouls (Windowed)...")

    # Improved query: Find the smallest ACTION_NUMBER > current that is a Foul
    # within the same period and game.
    query = """
        SELECT 
            p1.GAME_ID, 
            p1.ACTION_NUMBER, 
            p2.DESCRIPTION as FOUL_DESC
        FROM play_by_play p1
        JOIN play_by_play p2 ON p1.GAME_ID = p2.GAME_ID 
          AND p2.ACTION_NUMBER > p1.ACTION_NUMBER
          AND p2.ACTION_NUMBER < p1.ACTION_NUMBER + 10
          AND p1.PERIOD = p2.PERIOD
        WHERE p1.ACTION_TYPE = 'Missed Shot'
          AND p2.ACTION_TYPE = 'Foul'
          AND p2.SUB_TYPE IN ('Personal', 'Shooting', 'Loose Ball')
    """
    # We take the first foul found after the shot
    df = con.execute(query).df()

    if df.empty:
        logger.info("No shot-foul sequences found.")
        con.close()
        return

    # Keep only the closest foul for each shot
    df = df.sort_values(['GAME_ID', 'ACTION_NUMBER']).groupby(['GAME_ID', 'ACTION_NUMBER']).first().reset_index()

    def extract_fouler(desc):
        import re
        # Support various foul formats
        match = re.search(r'^(.*?)\s[PSL]\.FOUL', desc)
        if not match:
            match = re.search(r'^(.*?)\sOffensive', desc)
        if match:
            return match.group(1).strip()
        return None

    df['TRUE_DEFENDER'] = df['FOUL_DESC'].apply(extract_fouler)
    df = df.dropna(subset=['TRUE_DEFENDER'])

    logger.info(f"Updating {len(df)} shots with Foul-Link defender data...")

    con.register('temp_foul_defenders', df[['GAME_ID', 'ACTION_NUMBER', 'TRUE_DEFENDER']])
    con.execute("""
        UPDATE play_by_play
        SET DEFENDER_NAME = temp_foul_defenders.TRUE_DEFENDER,
            MICRO_ACTION = 'Physical Contest (Foul)'
        FROM temp_foul_defenders
        WHERE play_by_play.GAME_ID = temp_foul_defenders.GAME_ID
          AND play_by_play.ACTION_NUMBER = temp_foul_defenders.ACTION_NUMBER
    """)

    con.unregister('temp_foul_defenders')
    con.close()
    logger.info("Foul-Link population complete.")


if __name__ == "__main__":
    populate_foul_contests()
