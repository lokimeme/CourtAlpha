import duckdb
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PPGFix")

def fix_missing_pbp_names():
    con = duckdb.connect('data/courtalpha.duckdb')
    
    # Absolute Star Mapping for Free Throws (Non-ambiguous)
    star_ft_map = {
        'James': 'LeBron James',
        'Doncic': 'Luka Doncic',
        'Embiid': 'Joel Embiid',
        'Antetokounmpo': 'Giannis Antetokounmpo',
        'Jokic': 'Nikola Jokic',
        'Tatum': 'Jayson Tatum',
        'Gilgeous-Alexander': 'Shai Gilgeous-Alexander',
        'SGA': 'Shai Gilgeous-Alexander',
        'Young': 'Trae Young',
        'McCollum': 'CJ McCollum',
        'Harden': 'James Harden',
        'Davis': 'Anthony Davis',
        'Booker': 'Devin Booker',
        'Lillard': 'Damian Lillard',
        'Mitchell': 'Donovan Mitchell',
        'Butler': 'Jimmy Butler III',
        'Wembanyama': 'Victor Wembanyama'
    }
    
    logger.info("Fixing non-ambiguous star names in Free Throws...")
    for last_name, full_name in star_ft_map.items():
        con.execute(f"""
            UPDATE play_by_play 
            SET PLAYER_NAME = ? 
            WHERE ACTION_TYPE = 'Free Throw' 
              AND (DESCRIPTION LIKE '{last_name} %' OR DESCRIPTION LIKE 'MISS {last_name} %')
        """, [full_name])

    # Ambiguous Stars (Curry, Thompson, Williams)
    # We use a join with player_teams or roster logic
    logger.info("Fixing ambiguous 'Curry' Free Throws...")
    # Map 'Curry' to Stephen Curry if he is on GSW and the game involved GSW
    # Actually, simpler: just map 'Curry' to whoever has more FGA in the database?
    # No, let's be more precise.
    
    con.execute("""
        UPDATE play_by_play
        SET PLAYER_NAME = 'Stephen Curry'
        WHERE ACTION_TYPE = 'Free Throw'
          AND (DESCRIPTION LIKE 'Curry %' OR DESCRIPTION LIKE 'MISS Curry %')
          AND GAME_ID IN (SELECT DISTINCT GAME_ID FROM play_by_play WHERE PLAYER_NAME = 'Stephen Curry')
    """)
    
    con.execute("""
        UPDATE play_by_play
        SET PLAYER_NAME = 'Seth Curry'
        WHERE ACTION_TYPE = 'Free Throw'
          AND (DESCRIPTION LIKE 'Curry %' OR DESCRIPTION LIKE 'MISS Curry %')
          AND GAME_ID IN (SELECT DISTINCT GAME_ID FROM play_by_play WHERE PLAYER_NAME = 'Seth Curry')
    """)

    con.close()
    logger.info("Star PPG fix complete.")

if __name__ == "__main__":
    fix_missing_pbp_names()
