import duckdb
import pandas as pd
import re
import unicodedata

DB_PATH = 'data/courtalpha.duckdb'

def normalize_name(name):
    if not name: return None
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    return name.strip()

def extract_player_name(description):
    if not description or 'REBOUND' not in description:
        return None
    # "Horford REBOUND (Off:0 Def:1)" -> "Horford"
    match = re.search(r'^(.*?)\sREBOUND', description)
    if match:
        return normalize_name(match.group(1))
    return None

def populate_defender_names():
    con = duckdb.connect(DB_PATH)
    
    print("Fetching missed shots and following rebounds...")
    # Using a self-join to find the event immediately after a missed shot
    query = """
        SELECT 
            p1.GAME_ID, 
            p1.ACTION_NUMBER, 
            p2.DESCRIPTION as REBOUND_DESC
        FROM play_by_play p1
        JOIN play_by_play p2 ON p1.GAME_ID = p2.GAME_ID 
          AND p1.ACTION_NUMBER + 1 = p2.ACTION_NUMBER
        WHERE p1.ACTION_TYPE = 'Missed Shot'
          AND p2.ACTION_TYPE = 'Rebound'
          AND p2.DESCRIPTION LIKE '%Def:1%'
          AND p1.DEFENDER_NAME IS NULL
    """
    df = con.execute(query).df()
    
    if df.empty:
        print("No new defensive stops found.")
        return

    print(f"Extracting defender names for {len(df)} defensive stops...")
    df['EXTRACTED_DEFENDER'] = df['REBOUND_DESC'].apply(extract_player_name)
    
    print("Updating database...")
    con.register('temp_defenders', df[['GAME_ID', 'ACTION_NUMBER', 'EXTRACTED_DEFENDER']])
    con.execute("""
        UPDATE play_by_play
        SET DEFENDER_NAME = temp_defenders.EXTRACTED_DEFENDER
        FROM temp_defenders
        WHERE play_by_play.GAME_ID = temp_defenders.GAME_ID
          AND play_by_play.ACTION_NUMBER = temp_defenders.ACTION_NUMBER
    """)
    
    con.unregister('temp_defenders')
    con.close()
    print("Defender name population complete.")

if __name__ == "__main__":
    populate_defender_names()
