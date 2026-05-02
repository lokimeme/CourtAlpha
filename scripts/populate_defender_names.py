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
    match = re.search(r'^(.*?)\sREBOUND', description)
    if match:
        return normalize_name(match.group(1))
    return None

def populate_defender_names():
    con = duckdb.connect(DB_PATH)
    
    print("Fetching missed shots and following rebounds...")
    query = 
    df = con.execute(query).df()
    
    if df.empty:
        print("No new defensive stops found.")
        return

    print(f"Extracting defender names for {len(df)} defensive stops...")
    df['EXTRACTED_DEFENDER'] = df['REBOUND_DESC'].apply(extract_player_name)
    
    print("Updating database...")
    con.register('temp_defenders', df[['GAME_ID', 'ACTION_NUMBER', 'EXTRACTED_DEFENDER']])
    con.execute()
    
    con.unregister('temp_defenders')
    con.close()
    print("Defender name population complete.")

if __name__ == "__main__":
    populate_defender_names()