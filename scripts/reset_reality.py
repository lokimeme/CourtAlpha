import duckdb
import pandas as pd
from nba_api.stats.static import teams
from nba_api.stats.endpoints import commonteamroster
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RosterReset")

def reset_to_real_rosters():
    """
    Purges all hypothetical trade overrides and pulls 100% real current rosters 
    directly from the NBA API.
    """
    con = duckdb.connect('data/courtalpha.duckdb')
    
    # 1. Clear everything first
    logger.info("Purging all hypothetical overrides...")
    con.execute("DROP TABLE IF EXISTS player_teams")
    con.execute("CREATE TABLE player_teams (PLAYER_NAME VARCHAR, TEAM VARCHAR)")
    
    # 2. Pull from live NBA API
    nba_teams = teams.get_teams()
    all_players = []
    
    logger.info(f"Fetching rosters for {len(nba_teams)} NBA teams...")
    for t in nba_teams:
        team_id = t['id']
        tricode = t['abbreviation']
        
        for attempt in range(3):
            try:
                roster_df = commonteamroster.CommonTeamRoster(team_id=team_id, timeout=15).get_data_frames()[0]
                for _, row in roster_df.iterrows():
                    all_players.append({
                        'PLAYER_NAME': row['PLAYER'],
                        'TEAM': tricode
                    })
                logger.info(f"  Successfully synced {tricode}")
                time.sleep(1.0)
                break
            except Exception as e:
                logger.warning(f"  Timeout on {tricode} ({attempt+1}/3)")
                time.sleep(2)

    if all_players:
        df = pd.DataFrame(all_players)
        con.register('temp_roster', df)
        con.execute("INSERT INTO player_teams SELECT PLAYER_NAME, TEAM FROM temp_roster")
        logger.info(f"Successfully rebuilt player_teams with {len(df)} real-world players.")
    
    # 3. Clean up contracts teams to match reality
    logger.info("Cleaning up contracts teams...")
    con.execute("""
        UPDATE contracts
        SET TEAM = player_teams.TEAM
        FROM player_teams
        WHERE contracts.PLAYER_NAME = player_teams.PLAYER_NAME
    """)

    con.close()
    logger.info("REALITY RESTORED: All hypothetical trades purged.")

if __name__ == "__main__":
    reset_to_real_rosters()
