import duckdb
import numpy as np
import pandas as pd
import time

DB_PATH = 'data/courtalpha.duckdb'

def calculate_spatial_features():
    con = duckdb.connect(DB_PATH)
    
    print("Adding spatial columns to play_by_play...")
    try:
        con.execute("ALTER TABLE play_by_play ADD COLUMN SHOT_ZONE VARCHAR")
    except: pass
    try:
        con.execute("ALTER TABLE play_by_play ADD COLUMN SHOT_ANGLE FLOAT")
    except: pass

    print("Fetching shots for processing...")
    df = con.execute().df()

    if df.empty:
        print("No shots found to process.")
        return

    print(f"Processing {len(df)} shots...")

    df['SHOT_ANGLE'] = np.degrees(np.arctan2(df['LOC_X'], df['LOC_Y']))
    
    def get_zone(row):
        x, y, dist = row['LOC_X'], row['LOC_Y'], row['SHOT_DISTANCE']
        
        if dist <= 4:
            return 'Restricted Area'
        
        if abs(x) >= 220 and y <= 140:
            return 'Left Corner 3' if x < 0 else 'Right Corner 3'
        
        if dist >= 23.75 or (abs(x) >= 220 and y > 140):
            return 'Above the Break 3'
        
        if abs(x) <= 80 and y <= 190:
            if dist <= 10: return 'Short Paint'
            return 'Long Paint'
        
        if dist <= 16: return 'Short Mid-Range'
        return 'Long Mid-Range'

    df['SHOT_ZONE'] = df.apply(get_zone, axis=1)

    print("Registering temporary table for bulk update...")
    con.register('temp_features', df[['GAME_ID', 'ACTION_NUMBER', 'SHOT_ZONE', 'SHOT_ANGLE']])
    
    print("Updating play_by_play table...")
    con.execute()
    
    con.unregister('temp_features')
    con.close()
    print("Spatial feature engineering complete.")

if __name__ == "__main__":
    calculate_spatial_features()