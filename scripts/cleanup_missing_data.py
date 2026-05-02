import duckdb
import pandas as pd
from nba_api.stats.endpoints import shotchartdetail
import time
import sys

DB_PATH = 'data/courtalpha.duckdb'

def fetch_shot_data_with_retry(game_id, retries=3, delay=5):
    """Retrieves shot data with a retry mechanism, checking both Regular Season and Playoffs."""
    season_types = ['Regular Season', 'Playoffs']
    
    for season_type in season_types:
        for attempt in range(retries):
            try:
                shot_data = shotchartdetail.ShotChartDetail(
                    team_id=0, 
                    player_id=0, 
                    game_id_nullable=game_id, 
                    context_measure_simple='FGA',
                    season_type_all_star=season_type,
                    timeout=30
                ).get_data_frames()[0]
                
                if not shot_data.empty:
                    print(f"  Successfully found data for {game_id} as {season_type}", flush=True)
                    return shot_data
                break
            except Exception as e:
                if "429" in str(e):
                    print(f"Rate limited on {game_id}. Sleeping 30s...", flush=True)
                    time.sleep(30)
                else:
                    print(f"Attempt {attempt+1} failed for {game_id} ({season_type}): {e}", flush=True)
                    time.sleep(delay * (attempt + 1))
    
    return pd.DataFrame()

def cleanup(limit=None):
    con = duckdb.connect(DB_PATH)
    
    query = """
        SELECT DISTINCT GAME_ID 
        FROM play_by_play 
        WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot') 
          AND LOC_X IS NULL
    """
    affected_games = [row[0] for row in con.execute(query).fetchall()]
    
    total = len(affected_games)
    if limit:
        affected_games = affected_games[:limit]
        print(f"Processing {len(affected_games)} out of {total} affected games...")
    else:
        print(f"Total games to cleanup: {total}")

    success_count = 0
    
    for i, game_id in enumerate(affected_games):
        print(f"[{i+1}/{len(affected_games)}] Fixing {game_id}...", flush=True)
        
        shots = fetch_shot_data_with_retry(game_id)
        
        if not shots.empty:
            try:
                shots_df = shots[['GAME_EVENT_ID', 'LOC_X', 'LOC_Y', 'SHOT_DISTANCE', 'SHOT_MADE_FLAG']].copy()
                shots_df['GAME_EVENT_ID'] = shots_df['GAME_EVENT_ID'].astype(int)
                con.register('temp_shots', shots_df)
                
                con.execute(f"""
                    UPDATE play_by_play
                    SET 
                        LOC_X = temp_shots.LOC_X,
                        LOC_Y = temp_shots.LOC_Y,
                        SHOT_DISTANCE = temp_shots.SHOT_DISTANCE,
                        SHOT_MADE_FLAG = temp_shots.SHOT_MADE_FLAG
                    FROM temp_shots
                    WHERE play_by_play.GAME_ID = '{game_id}'
                      AND play_by_play.ACTION_NUMBER = temp_shots.GAME_EVENT_ID
                """)
                success_count += 1
                con.unregister('temp_shots')
            except Exception as e:
                print(f"Update error for {game_id}: {e}", flush=True)
        else:
            print(f"Skipping {game_id} - no shot data retrieved.", flush=True)
        
        time.sleep(1.2)

    con.close()
    print(f"Cleanup complete. Successfully updated {success_count} games.")

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    cleanup(limit)
