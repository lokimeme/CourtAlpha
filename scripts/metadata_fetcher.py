import duckdb
import pandas as pd
from nba_api.stats.static import players
from nba_api.stats.endpoints import commonplayerinfo
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MetadataFetcher")

DB_PATH = 'data/courtalpha.duckdb'

def setup_metadata_table():
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS player_metadata (
            PLAYER_NAME VARCHAR PRIMARY KEY,
            NBA_ID INTEGER,
            HEIGHT VARCHAR,
            WEIGHT VARCHAR,
            BIRTHDATE VARCHAR,
            DRAFT_YEAR VARCHAR,
            DRAFT_NUMBER VARCHAR,
            COUNTRY VARCHAR
        )
    """)
    con.close()

def get_unique_players():
    con = duckdb.connect(DB_PATH, read_only=True)
    query = "SELECT DISTINCT name FROM ("
    query += " UNION ".join([f"SELECT DISTINCT {col} as name FROM play_by_play" for col in [f"OFF_{i}" for i in range(1, 6)] + [f"DEF_{i}" for i in range(1, 6)]])
    query += ") WHERE name IS NOT NULL"
    
    lineup_players = con.execute(query).df()['name'].tolist()
    con.close()
    
    logger.info(f"Found {len(lineup_players)} unique players in lineup data.")
    
    all_nba_players = players.get_players()
    
    target_list = []
    for pbp_name in lineup_players:
        match = None
        
        for nba_p in all_nba_players:
            if nba_p['full_name'] == pbp_name:
                match = nba_p
                break
        
        if not match and ". " in pbp_name:
            initial, last = pbp_name.split(". ", 1)
            for nba_p in all_nba_players:
                if nba_p['last_name'] == last and nba_p['first_name'].startswith(initial):
                    match = nba_p
                    break
        
        if not match:
            for nba_p in all_nba_players:
                if nba_p['last_name'] == pbp_name:
                    match = nba_p
                    break

        if match:
            target_list.append({'full_name': match['full_name'], 'id': match['id']})
        else:
            logger.warning(f"Could not find NBA ID for: {pbp_name}")
            
    seen = set()
    unique_targets = []
    for t in target_list:
        if t['id'] not in seen:
            unique_targets.append(t)
            seen.add(t['id'])
            
    return unique_targets

def fetch_and_populate():
    setup_metadata_table()
    
    target_players = get_unique_players()
    
    con = duckdb.connect(DB_PATH)
    
    existing = con.execute("SELECT PLAYER_NAME FROM player_metadata").df()['PLAYER_NAME'].tolist()
    
    count = 0
    for p in target_players:
        if p['full_name'] in existing:
            continue
            
        try:
            logger.info(f"Fetching metadata for {p['full_name']}...")
            info = commonplayerinfo.CommonPlayerInfo(player_id=p['id']).get_dict()['resultSets'][0]['rowSet'][0]
            
            data = {
                'PLAYER_NAME': p['full_name'],
                'NBA_ID': p['id'],
                'HEIGHT': info[11],
                'WEIGHT': info[12],
                'BIRTHDATE': info[7],
                'DRAFT_YEAR': info[29],
                'DRAFT_NUMBER': info[31],
                'COUNTRY': info[9]
            }
            
            con.execute("""
                INSERT OR IGNORE INTO player_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, list(data.values()))
            
            count += 1
            time.sleep(0.8)
            
            if count % 10 == 0:
                logger.info(f"Populated {count} new player profiles.")
                
        except Exception as e:
            logger.error(f"Error fetching {p['full_name']}: {e}")
            time.sleep(2)

    con.close()
    logger.info("Metadata population complete.")

if __name__ == "__main__":
    fetch_and_populate()
