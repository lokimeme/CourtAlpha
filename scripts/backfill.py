import duckdb
import pandas as pd
from nba_api.stats.endpoints import playbyplayv3, leaguegamefinder, shotchartdetail
import time
import os

DB_PATH = 'data/courtalpha.duckdb'

def setup_db():
    con = duckdb.connect(DB_PATH)
    # Ensure schema is correct and up to date
    con.execute("""
        CREATE TABLE IF NOT EXISTS play_by_play (
            GAME_ID VARCHAR,
            ACTION_NUMBER INTEGER,
            PERIOD INTEGER,
            CLOCK VARCHAR,
            ACTION_TYPE VARCHAR,
            SUB_TYPE VARCHAR,
            DESCRIPTION VARCHAR,
            SCORE_HOME VARCHAR,
            SCORE_AWAY VARCHAR,
            GARBAGE_TIME BOOLEAN,
            OPP_DEF_RATING FLOAT,
            LOC_X FLOAT,
            LOC_Y FLOAT,
            SHOT_DISTANCE FLOAT,
            SHOT_MADE_FLAG INTEGER,
            SEASON VARCHAR,
            MICRO_ACTION VARCHAR,
            PRIMARY KEY (GAME_ID, ACTION_NUMBER)
        )
    """)
    con.close()

def fetch_shot_data(game_id):
    """Retrieves spatial coordinates (X, Y) for every field goal attempt."""
    try:
        shot_data = shotchartdetail.ShotChartDetail(
            team_id=0, 
            player_id=0, 
            game_id_nullable=game_id, 
            context_measure_simple='FGA'
        ).get_data_frames()[0]
        return shot_data
    except Exception as e:
        print(f"Shot Data Error (Game {game_id}): {e}", flush=True)
        return pd.DataFrame()

def get_games_for_seasons(seasons):
    all_games = []
    for season in seasons:
        print(f"Fetching game list for {season}...", flush=True)
        gamefinder = leaguegamefinder.LeagueGameFinder(season_nullable=season, league_id_nullable='00')
        df = gamefinder.get_data_frames()[0]
        df = df[df['GAME_ID'].str.startswith(('002', '004'))]
        df['SEASON_TAG'] = season
        all_games.append(df[['GAME_ID', 'MATCHUP', 'SEASON_TAG']])
        time.sleep(1)
    if not all_games:
        return pd.DataFrame()
    return pd.concat(all_games).drop_duplicates('GAME_ID')

def backfill_seasons(seasons_list, limit=None, regular_only=True):
    setup_db()
    games_df = get_games_for_seasons(seasons_list)
    
    if games_df.empty:
        print("No games found for the specified seasons.", flush=True)
        return

    if regular_only:
        games_df = games_df[games_df['GAME_ID'].str.startswith('002')]
        
    if limit:
        games_df = games_df.head(limit)
        
    total = len(games_df)
    print(f"Total games to process: {total}", flush=True)

    con = duckdb.connect(DB_PATH)
    
    for i, (_, row) in enumerate(games_df.iterrows()):
        game_id = row['GAME_ID']
        season = row['SEASON_TAG']
        
        try:
            print(f"[{i+1}/{total}] Ingesting {game_id} ({season})...", flush=True)
            pbp_raw = playbyplayv3.PlayByPlayV3(game_id=game_id)
            df = pbp_raw.get_data_frames()[0]
            
            # Shot Data Enrichment
            shots = fetch_shot_data(game_id)
            if not shots.empty:
                shots = shots[['GAME_EVENT_ID', 'LOC_X', 'LOC_Y', 'SHOT_DISTANCE', 'SHOT_MADE_FLAG']]
                # Ensure types match for merge
                df['actionNumber'] = df['actionNumber'].astype(int)
                shots['GAME_EVENT_ID'] = shots['GAME_EVENT_ID'].astype(int)
                df = df.merge(shots, left_on='actionNumber', right_on='GAME_EVENT_ID', how='left')
            else:
                for col in ['LOC_X', 'LOC_Y', 'SHOT_DISTANCE', 'SHOT_MADE_FLAG']:
                    df[col] = None

            # Garbage Time Logic
            df['GARBAGE_TIME'] = False
            if 'scoreHome' in df.columns and 'scoreAway' in df.columns:
                def check_gt(r):
                    try:
                        if r['period'] >= 4:
                            diff = abs(int(r['scoreHome'] or 0) - int(r['scoreAway'] or 0))
                            return diff > 15
                    except: pass
                    return False
                df['GARBAGE_TIME'] = df.apply(check_gt, axis=1)

            # Prepare for insertion
            df_insert = pd.DataFrame()
            df_insert['GAME_ID'] = [game_id] * len(df)
            df_insert['ACTION_NUMBER'] = df['actionNumber']
            df_insert['PERIOD'] = df['period']
            df_insert['CLOCK'] = df['clock']
            df_insert['ACTION_TYPE'] = df['actionType']
            df_insert['SUB_TYPE'] = df['subType']
            df_insert['DESCRIPTION'] = df['description']
            df_insert['SCORE_HOME'] = df['scoreHome']
            df_insert['SCORE_AWAY'] = df['scoreAway']
            df_insert['GARBAGE_TIME'] = df['GARBAGE_TIME']
            df_insert['OPP_DEF_RATING'] = 110.0
            df_insert['LOC_X'] = df['LOC_X']
            df_insert['LOC_Y'] = df['LOC_Y']
            df_insert['SHOT_DISTANCE'] = df['SHOT_DISTANCE']
            df_insert['SHOT_MADE_FLAG'] = df['SHOT_MADE_FLAG']
            df_insert['SEASON'] = season
            df_insert['MICRO_ACTION'] = None
            
            cols = "(GAME_ID, ACTION_NUMBER, PERIOD, CLOCK, ACTION_TYPE, SUB_TYPE, DESCRIPTION, SCORE_HOME, SCORE_AWAY, GARBAGE_TIME, OPP_DEF_RATING, LOC_X, LOC_Y, SHOT_DISTANCE, SHOT_MADE_FLAG, SEASON, MICRO_ACTION)"
            con.register('df_view', df_insert)
            
            # Use INSERT OR REPLACE to update existing games with new columns
            con.execute(f"INSERT OR REPLACE INTO play_by_play {cols} SELECT * FROM df_view")
            
            time.sleep(0.8) # Respect API
        except Exception as e:
            print(f"Error {game_id}: {e}", flush=True)
            time.sleep(5)

    con.close()

if __name__ == "__main__":
    # Standard configuration for 8 seasons (Regular + Playoffs)
    target_seasons = [
        '2018-19', '2019-20', '2020-21', '2021-22', 
        '2022-23', '2023-24', '2024-25', '2025-26'
    ] 
    
    # Toggle this to True for a quick verification batch
    IS_TEST = False
    
    if IS_TEST:
        backfill_seasons(['2024-25'], limit=10, regular_only=False)
    else:
        backfill_seasons(target_seasons, regular_only=False)
