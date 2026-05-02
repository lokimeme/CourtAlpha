import duckdb
import re
import pandas as pd
import unicodedata

DB_PATH = 'data/courtalpha.duckdb'

def normalize_name(name):
    if not name: return None
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    return name.strip()

def extract_assister_name(description):
    if not description:
        return None
    
    match = re.search(r'\(([^)]+)\s\d+\sAST\)', description)
    if match:
        return normalize_name(match.group(1))
    return None

def populate_assister_names():
    con = duckdb.connect(DB_PATH)
    
    print("Fetching assist descriptions...")
    df = con.execute().df()
    
    if df.empty:
        print("No new assists found to process.")
        return

    print(f"Extracting assister names for {len(df)} events...")
    df['EXTRACTED_ASSISTER'] = df['DESCRIPTION'].apply(extract_assister_name)
    
    print("Updating database...")
    con.register('temp_assists', df[['GAME_ID', 'ACTION_NUMBER', 'EXTRACTED_ASSISTER']])
    con.execute()
    
    con.unregister('temp_assists')
    con.close()
    print("Assister name population complete.")

if __name__ == "__main__":
    populate_assister_names()