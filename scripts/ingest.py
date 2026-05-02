import duckdb
import pandas as pd
from nba_api.stats.endpoints import playbyplayv3, leaguegamefinder, leaguedashteamstats, shotchartdetail
from nba_api.stats.static import teams
from datetime import datetime, timedelta
import time
import os
import logging
from scripts.utils import setup_logging

DB_PATH = 'data/courtalpha.duckdb'
logger = setup_logging()

def setup_db():
    
    logger.info("Initializing Database Schema...")
    os.makedirs('data', exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute()
    con.close()

def get_yesterdays_games():
    
    logger.info("Searching for recent NBA games...")
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    gamefinder = leaguegamefinder.LeagueGameFinder(date_from_nullable=yesterday, date_to_nullable=yesterday)
    games = gamefinder.get_data_frames()[0]
    
    nba_teams = [t['id'] for t in teams.get_teams()]
    nba_games = games[games['TEAM_ID'].isin(nba_teams)]
    
    if nba_games.empty:
        logger.warning("No games found yesterday. Expanding search window.")
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        gamefinder = leaguegamefinder.LeagueGameFinder(date_from_nullable=three_days_ago, date_to_nullable=yesterday)
        games = gamefinder.get_data_frames()[0]
        nba_games = games[games['TEAM_ID'].isin(nba_teams)]
        
    return nba_games[['GAME_ID', 'TEAM_ID', 'MATCHUP']].drop_duplicates('GAME_ID')

def fetch_shot_data(game_id):
    
    try:
        shot_data = shotchartdetail.ShotChartDetail(
            team_id=0, 
            player_id=0, 
            game_id_nullable=game_id, 
            context_measure_simple='FGA'
        ).get_data_frames()[0]
        return shot_data
    except Exception as e:
        logger.error(f"Shot Data Error (Game {game_id}): {e}")
        return pd.DataFrame()

def tag_garbage_time(df):
    
    def is_garbage(row):
        try:
            if row['period'] >= 4:
                sh = int(row['scoreHome'] or 0)
                sa = int(row['scoreAway'] or 0)
                if abs(sh - sa) > 15:
                    return True
        except: pass
        return False
    
    df['GARBAGE_TIME'] = df.apply(is_garbage, axis=1)
    return df

def ingest_daily():
    
    setup_db()
    games = get_yesterdays_games()
    
    if games.empty:
        logger.info("Nothing to ingest today.")
        return

    con = duckdb.connect(DB_PATH)
    for _, game in games.iterrows():
        gid = game['GAME_ID']
        logger.info(f"Processing Game: {gid}")
        
        try:
            pbp = playbyplayv3.PlayByPlayV3(game_id=gid).get_data_frames()[0]
            pbp = tag_garbage_time(pbp)
            shots = fetch_shot_data(gid)
            
            if not shots.empty:
                shots = shots[['GAME_EVENT_ID', 'LOC_X', 'LOC_Y', 'SHOT_DISTANCE', 'SHOT_MADE_FLAG']]
                pbp = pbp.merge(shots, left_on='actionNumber', right_on='GAME_EVENT_ID', how='left')
            
            time.sleep(1.0)
        except Exception as e:
            logger.error(f"Pipeline failure for {gid}: {e}")
            
    con.close()
    logger.info("Daily ingestion cycle complete.")

if __name__ == "__main__":
    ingest_daily()