import duckdb
import pandas as pd
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TrueDefenders")

DB_PATH = 'data/courtalpha.duckdb'

def populate_foul_contests():
    con = duckdb.connect(DB_PATH)

    logger.info("Searching for missed shots followed by fouls (Windowed)...")

    query = 
    df = con.execute(query).df()

    if df.empty:
        logger.info("No shot-foul sequences found.")
        con.close()
        return

    df = df.sort_values(['GAME_ID', 'ACTION_NUMBER']).groupby(['GAME_ID', 'ACTION_NUMBER']).first().reset_index()

    def extract_fouler(desc):
        import re
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
    con.execute()

    con.unregister('temp_foul_defenders')
    con.close()
    logger.info("Foul-Link population complete.")

if __name__ == "__main__":
    populate_foul_contests()