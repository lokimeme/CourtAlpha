import duckdb
import re
import pandas as pd
import unicodedata

DB_PATH = 'data/courtalpha.duckdb'

def normalize_name(name):
    if not name: return None
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'\s3PT$', '', name)
    return name.strip()

def extract_player_name(description):
    if not description:
        return None
    
    name = re.sub(r'^MISS\s', '', description)
    
    match = re.search(r'^(.*?)(?=\s\d+\'|\sTip|\sAlley|\sLayup|\sDunk|\sJump|\sHook|\sBank|\sFloating|\sDriving|\sFadeaway|\sStep|\sPullup|\sRunning|\sCutting|\sTurnaround)', name)
    
    extracted = None
    if match:
        extracted = match.group(1).strip()
    else:
        parts = name.split()
        if len(parts) >= 2:
            extracted = f"{parts[0]} {parts[1]}"
        else:
            extracted = parts[0] if parts else None
    
    return normalize_name(extracted)

def populate_player_names():
    con = duckdb.connect(DB_PATH)
    
    print("Fetching shot descriptions...")
    df = con.execute().df()
    
    if df.empty:
        print("No shots without player names found.")
        return

    print(f"Extracting names for {len(df)} shots...")
    df['EXTRACTED_NAME'] = df['DESCRIPTION'].apply(extract_player_name)
    
    print("Updating database...")
    con.register('temp_names', df[['GAME_ID', 'ACTION_NUMBER', 'EXTRACTED_NAME']])
    con.execute()
    
    con.unregister('temp_names')
    con.close()
    print("Player name population complete.")

if __name__ == "__main__":
    populate_player_names()