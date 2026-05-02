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
    
    # Format: "... (Player 1 AST)"
    match = re.search(r'\(([^)]+)\s\d+\sAST\)', description)
    if match:
        return normalize_name(match.group(1))
    return None

def populate_assister_names():
    con = duckdb.connect(DB_PATH)
    
    print("Fetching assist descriptions...")
    df = con.execute("""
        SELECT GAME_ID, ACTION_NUMBER, DESCRIPTION 
        FROM play_by_play 
        WHERE DESCRIPTION LIKE '%AST)'
          AND ASSISTER_NAME IS NULL
    """).df()
    
    if df.empty:
        print("No new assists found to process.")
        return

    print(f"Extracting assister names for {len(df)} events...")
    df['EXTRACTED_ASSISTER'] = df['DESCRIPTION'].apply(extract_assister_name)
    
    print("Updating database...")
    con.register('temp_assists', df[['GAME_ID', 'ACTION_NUMBER', 'EXTRACTED_ASSISTER']])
    con.execute("""
        UPDATE play_by_play
        SET ASSISTER_NAME = temp_assists.EXTRACTED_ASSISTER
        FROM temp_assists
        WHERE play_by_play.GAME_ID = temp_assists.GAME_ID
          AND play_by_play.ACTION_NUMBER = temp_assists.ACTION_NUMBER
    """)
    
    con.unregister('temp_assists')
    con.close()
    print("Assister name population complete.")

if __name__ == "__main__":
    populate_assister_names()
