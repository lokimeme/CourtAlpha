import duckdb
import pandas as pd
from nba_api.stats.endpoints import boxscoretraditionalv3
import time
import re
import logging
import os
import sys
import unicodedata

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("lineup_reconstruction.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("LineupEngine")

DB_PATH = 'data/courtalpha.duckdb'

def normalize_name(name):
    if not isinstance(name, str): return None
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    return name.strip()

def setup_columns(con):
    logger.info("Ensuring lineup columns exist...")
    cols = [f"OFF_{i}" for i in range(1, 6)] + [f"DEF_{i}" for i in range(1, 6)]
    existing_cols = [c[1] for c in con.execute("PRAGMA table_info(play_by_play)").fetchall()]
    for col in cols:
        if col not in existing_cols:
            logger.info(f"Adding column {col}")
            con.execute(f"ALTER TABLE play_by_play ADD COLUMN {col} VARCHAR")

def get_pending_games(con):
    query = """
    SELECT DISTINCT GAME_ID 
    FROM play_by_play 
    WHERE OFF_1 IS NULL
    LIMIT 100
    """
    res = con.execute(query).fetchall()
    return [r[0] for r in res]

def fetch_box_score(game_id):
    try:
        box = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        data = box.get_dict()['boxScoreTraditional']
        return data
    except Exception as e:
        logger.error(f"Error fetching box score for {game_id}: {e}")
        return None

def process_game(game_id, con):
    box_data = fetch_box_score(game_id)
    if not box_data:
        return False

    home_team_id = box_data['homeTeam']['teamId']
    away_team_id = box_data['awayTeam']['teamId']
    
    player_info = {}
    name_to_ids = {home_team_id: {}, away_team_id: {}}
    
    def map_team_players(team_data, team_id):
        players = team_data['players']
        family_names = [normalize_name(p['familyName']) for p in players]
        for p in players:
            pid = p['personId']
            fname = normalize_name(p['firstName'])
            lname = normalize_name(p['familyName'])
            full_name = f"{fname} {lname}"
            
            pbp_name = f"{fname[0]}. {lname}"
            
            player_info[pid] = {
                'teamId': team_id, 
                'pbpName': pbp_name,
                'familyName': lname,
                'fullName': full_name
            }
            
            for name_form in [pbp_name, lname, full_name]:
                if name_form not in name_to_ids[team_id]:
                    name_to_ids[team_id][name_form] = []
                name_to_ids[team_id][name_form].append(pid)

    map_team_players(box_data['homeTeam'], home_team_id)
    map_team_players(box_data['awayTeam'], away_team_id)

    current_lineups = {
        home_team_id: set(p['personId'] for p in box_data['homeTeam']['players'] if p['position'] != ""),
        away_team_id: set(p['personId'] for p in box_data['awayTeam']['players'] if p['position'] != "")
    }

    pbp_df = con.execute(f"SELECT * FROM play_by_play WHERE GAME_ID = '{game_id}' ORDER BY PERIOD, ACTION_NUMBER").df()
    
    updates = []
    
    for _, row in pbp_df.iterrows():
        action_type = row['ACTION_TYPE']
        description = row['DESCRIPTION']
        player_name = normalize_name(row['PLAYER_NAME'])
        
        if action_type == 'Substitution' and " FOR " in description:
            match = re.search(r"SUB: (.*) FOR (.*)", description)
            if match:
                p_in_name = normalize_name(match.group(1).strip())
                p_out_name = normalize_name(match.group(2).strip())
                
                target_team_id = None
                p_out_id = None
                
                for tid, lineup in current_lineups.items():
                    for pid in lineup:
                        info = player_info[pid]
                        if p_out_name in [info['pbpName'], info['familyName'], info['fullName']] or info['pbpName'].endswith(p_out_name) or info['fullName'].endswith(p_out_name):
                            p_out_id = pid
                            target_team_id = tid
                            break
                    if target_team_id: break
                
                if target_team_id and p_out_id:
                    p_in_id = None
                    candidates = name_to_ids[target_team_id].get(p_in_name, [])
                    if not candidates:
                        for name, ids in name_to_ids[target_team_id].items():
                            if name.endswith(p_in_name):
                                candidates = ids
                                break
                    
                    if candidates:
                        p_in_id = candidates[0]
                        
                    if p_in_id:
                        current_lineups[target_team_id].discard(p_out_id)
                        current_lineups[target_team_id].add(p_in_id)
        
        off_team_id = None
        if player_name:
            for tid in [home_team_id, away_team_id]:
                if player_name in name_to_ids[tid]:
                    off_team_id = tid
                    break
            
            if not off_team_id:
                for tid in [home_team_id, away_team_id]:
                    for name in name_to_ids[tid]:
                        if name.endswith(player_name):
                            off_team_id = tid
                            break
                    if off_team_id: break
        
        if not off_team_id:
            off_team_id = home_team_id
            def_team_id = away_team_id
        else:
            def_team_id = away_team_id if off_team_id == home_team_id else home_team_id
        
        off_lineup = sorted([player_info[pid]['pbpName'] for pid in current_lineups[off_team_id]])
        def_lineup = sorted([player_info[pid]['pbpName'] for pid in current_lineups[def_team_id]])
        
        while len(off_lineup) < 5: off_lineup.append(None)
        while len(def_lineup) < 5: def_lineup.append(None)
        
        updates.append((*off_lineup[:5], *def_lineup[:5], game_id, row['ACTION_NUMBER']))

    if updates:
        cols = [f"OFF_{i}" for i in range(1, 6)] + [f"DEF_{i}" for i in range(1, 6)]
        up_df = pd.DataFrame(updates, columns=cols + ['GAME_ID', 'ACTION_NUMBER'])
        con.register('up_view', up_df)
        set_clause = ", ".join([f"{c} = up_view.{c}" for c in cols])
        con.execute(f"""
            UPDATE play_by_play 
            SET {set_clause}
            FROM up_view
            WHERE play_by_play.GAME_ID = up_view.GAME_ID 
              AND play_by_play.ACTION_NUMBER = up_view.ACTION_NUMBER
        """)
        con.unregister('up_view')
    
    return True

def main():
    con = duckdb.connect(DB_PATH)
    setup_columns(con)
    con.close()
    
    while True:
        con = duckdb.connect(DB_PATH)
        pending_games = get_pending_games(con)
        
        if not pending_games:
            logger.info("No more pending games found. Lineup reconstruction complete.")
            con.close()
            break
            
        logger.info(f"Found {len(pending_games)} games to process in this batch.")
        
        for i, game_id in enumerate(pending_games):
            start_time = time.time()
            logger.info(f"[{i+1}/{len(pending_games)}] Processing Game: {game_id}")
            
            try:
                success = process_game(game_id, con)
                if success:
                    logger.info(f"Successfully processed {game_id} in {time.time() - start_time:.2f}s")
                else:
                    logger.error(f"Failed to process {game_id}")
            except Exception as e:
                logger.error(f"Critical error processing {game_id}: {e}")
                
            time.sleep(0.8)
            
        con.close()
        logger.info("Batch complete. Checking for more games...")

if __name__ == "__main__":
    main()
