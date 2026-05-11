import duckdb
import pandas as pd
from nba_api.stats.static import teams
from nba_api.stats.endpoints import commonteamroster
import time
import logging
import unicodedata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RosterSync")

def norm(name):
    if not name: return ""
    # Strip accents
    name = "".join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    name = name.replace('ć', 'c').replace('č', 'c').replace('š', 's').replace('ž', 'z')
    return name.strip()

def build_full_roster():
    nba_teams = teams.get_teams()
    all_players = []
    
    logger.info(f"Fetching rosters for {len(nba_teams)} NBA teams...")
    
    for t in nba_teams:
        team_id = t['id']
        tricode = t['abbreviation']
        
        success = False
        for attempt in range(3):
            try:
                roster_df = commonteamroster.CommonTeamRoster(team_id=team_id, timeout=15).get_data_frames()[0]
                for _, row in roster_df.iterrows():
                    all_players.append({
                        'PLAYER_NAME': norm(row['PLAYER']),
                        'TEAM': tricode,
                        'POSITION': row['POSITION']
                    })
                logger.info(f"  Successfully synced {tricode}")
                success = True
                time.sleep(1.0)
                break
            except Exception as e:
                logger.warning(f"Timeout on {tricode}, attempt {attempt+1}/3: {e}")
                time.sleep(3)
                
        if not success:
            logger.error(f"Failed to fetch roster for {tricode}")

    if not all_players:
        logger.error("No roster data retrieved.")
        return
        
    df = pd.DataFrame(all_players)
    logger.info(f"Successfully retrieved {len(df)} players.")
    
    con = duckdb.connect('data/courtalpha.duckdb')
        
    con.execute("DROP TABLE IF EXISTS player_teams")
    con.execute("CREATE TABLE player_teams (PLAYER_NAME VARCHAR, TEAM VARCHAR, POSITION VARCHAR)")
    
    con.register('temp_roster', df)
    con.execute("INSERT INTO player_teams SELECT PLAYER_NAME, TEAM, POSITION FROM temp_roster")
    
    con.close()
    logger.info("Full roster sync complete.")

if __name__ == "__main__":
    build_full_roster()
