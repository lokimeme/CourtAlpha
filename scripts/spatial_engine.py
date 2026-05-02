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
    # Fetch only shots that haven't been processed yet
    df = con.execute("""
        SELECT GAME_ID, ACTION_NUMBER, LOC_X, LOC_Y, SHOT_DISTANCE 
        FROM play_by_play 
        WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot') 
          AND LOC_X IS NOT NULL
    """).df()

    if df.empty:
        print("No shots found to process.")
        return

    print(f"Processing {len(df)} shots...")

    # Vectorized calculations
    # Angle in degrees: 0 is straight ahead, -90 is left baseline, 90 is right baseline
    # Using arctan2(x, y) because NBA Y increases away from the basket
    df['SHOT_ANGLE'] = np.degrees(np.arctan2(df['LOC_X'], df['LOC_Y']))
    
    # Zone classification
    def get_zone(row):
        x, y, dist = row['LOC_X'], row['LOC_Y'], row['SHOT_DISTANCE']
        
        # 1. Restricted Area (4ft)
        if dist <= 4:
            return 'Restricted Area'
        
        # 2. Corner 3s (X > 22ft, Y < 14ft)
        if abs(x) >= 220 and y <= 140:
            return 'Left Corner 3' if x < 0 else 'Right Corner 3'
        
        # 3. Above the Break 3
        if dist >= 23.75 or (abs(x) >= 220 and y > 140):
            return 'Above the Break 3'
        
        # 4. Paint Zones (Lane is 16ft wide: -80 to 80)
        if abs(x) <= 80 and y <= 190:
            if dist <= 10: return 'Short Paint'
            return 'Long Paint'
        
        # 5. Mid-Range Zones
        if dist <= 16: return 'Short Mid-Range'
        return 'Long Mid-Range'

    df['SHOT_ZONE'] = df.apply(get_zone, axis=1)

    print("Registering temporary table for bulk update...")
    con.register('temp_features', df[['GAME_ID', 'ACTION_NUMBER', 'SHOT_ZONE', 'SHOT_ANGLE']])
    
    print("Updating play_by_play table...")
    con.execute("""
        UPDATE play_by_play
        SET 
            SHOT_ZONE = temp_features.SHOT_ZONE,
            SHOT_ANGLE = temp_features.SHOT_ANGLE
        FROM temp_features
        WHERE play_by_play.GAME_ID = temp_features.GAME_ID
          AND play_by_play.ACTION_NUMBER = temp_features.ACTION_NUMBER
    """)
    
    con.unregister('temp_features')
    con.close()
    print("Spatial feature engineering complete.")

if __name__ == "__main__":
    calculate_spatial_features()
