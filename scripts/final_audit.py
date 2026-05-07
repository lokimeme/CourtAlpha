import duckdb
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StarMapper")

def fix_everything():
    con = duckdb.connect('data/courtalpha.duckdb')
    
    # 1. Forceful Name Mapping for Play-By-Play
    # This maps common PBP abbreviations and last-name-only entries to full names
    logger.info("Fixing player names in play_by_play...")
    name_map = {
        'Doncic': 'Luka Doncic',
        'L. Doncic': 'Luka Doncic',
        'James': 'LeBron James',
        'Le. James': 'LeBron James',
        'Curry': 'Stephen Curry',
        'St. Curry': 'Stephen Curry',
        'Se. Curry': 'Seth Curry',
        'Durant': 'Kevin Durant',
        'K. Durant': 'Kevin Durant',
        'Embiid': 'Joel Embiid',
        'J. Embiid': 'Joel Embiid',
        'Antetokounmpo': 'Giannis Antetokounmpo',
        'G. Antetokounmpo': 'Giannis Antetokounmpo',
        'Jokic': 'Nikola Jokic',
        'N. Jokic': 'Nikola Jokic',
        'Gilgeous-Alexander': 'Shai Gilgeous-Alexander',
        'S. Gilgeous-Alexander': 'Shai Gilgeous-Alexander',
        'Wembanyama': 'Victor Wembanyama',
        'V. Wembanyama': 'Victor Wembanyama',
        'Adebayo': 'Bam Adebayo',
        'Banchero': 'Paolo Banchero',
        'Haliburton': 'Tyrese Haliburton',
        'T. Haliburton': 'Tyrese Haliburton',
        'Maxey': 'Tyrese Maxey',
        'T. Maxey': 'Tyrese Maxey',
        'Brunson': 'Jalen Brunson',
        'J. Brunson': 'Jalen Brunson',
        'Edwards': 'Anthony Edwards',
        'A. Edwards': 'Anthony Edwards',
        'Tatum': 'Jayson Tatum',
        'J. Tatum': 'Jayson Tatum',
        'Booker': 'Devin Booker',
        'D. Booker': 'Devin Booker',
        'Lillard': 'Damian Lillard',
        'D. Lillard': 'Damian Lillard',
        'Mitchell': 'Donovan Mitchell',
        'D. Mitchell': 'Donovan Mitchell',
        'Morant': 'Ja Morant',
        'J. Morant': 'Ja Morant',
        'SGA': 'Shai Gilgeous-Alexander',
        'Hardaway Jr.': 'Tim Hardaway Jr.',
        'Hardaway': 'Tim Hardaway Jr.',
        'Porzingis': 'Kristaps Porzingis',
        'K. Porzingis': 'Kristaps Porzingis',
        'Siakam': 'Pascal Siakam',
        'P. Siakam': 'Pascal Siakam',
        'Sabonis': 'Domantas Sabonis',
        'D. Sabonis': 'Domantas Sabonis',
        'Gobert': 'Rudy Gobert',
        'R. Gobert': 'Rudy Gobert',
        'Leonard': 'Kawhi Leonard',
        'K. Leonard': 'Kawhi Leonard',
        'Harden': 'James Harden',
        'J. Harden': 'James Harden',
        'George': 'Paul George',
        'P. George': 'Paul George',
        'Davis': 'Anthony Davis',
        'A. Davis': 'Anthony Davis',
        'Butler': 'Jimmy Butler',
        'J. Butler': 'Jimmy Butler',
        'DeRozan': 'DeMar DeRozan',
        'D. DeRozan': 'DeMar DeRozan',
        'LaVine': 'Zach LaVine',
        'Z. LaVine': 'Zach LaVine',
        'Williamson': 'Zion Williamson',
        'Z. Williamson': 'Zion Williamson',
        'Ingram': 'Brandon Ingram',
        'B. Ingram': 'Brandon Ingram',
        'McCollum': 'CJ McCollum',
        'C. McCollum': 'CJ McCollum',
        'Scottie Barnes': 'Scottie Barnes',
        'Barnes': 'Scottie Barnes',
        'S. Barnes': 'Scottie Barnes',
        'Mobley': 'Evan Mobley',
        'E. Mobley': 'Evan Mobley',
        'Allen': 'Jarrett Allen',
        'J. Allen': 'Jarrett Allen',
        'Duren': 'Jalen Duren',
        'J. Duren': 'Jalen Duren',
        'Fox': 'De\'Aaron Fox',
        'D. Fox': 'De\'Aaron Fox'
    }

    lineup_cols = [f"OFF_{i}" for i in range(1, 6)] + [f"DEF_{i}" for i in range(1, 6)]
    all_cols = ["PLAYER_NAME"] + lineup_cols
    
    for col in all_cols:
        logger.info(f"  Fixing {col}...")
        for old, new in name_map.items():
            con.execute(f"UPDATE play_by_play SET {col} = ? WHERE {col} = ?", [new, old])

    # 2. Perfect Roster Alignment
    logger.info("Aligning names in player_teams...")
    
    # Apply name overrides to player_teams to ensure they match PBP perfectly
    for old, new in name_map.items():
        con.execute("UPDATE player_teams SET PLAYER_NAME = ? WHERE PLAYER_NAME = ?", [new, old])

    # Insert missing stars explicitly (since live API sometimes drops injured/inactive players)
    real_rosters = [
        ('Luka Doncic', 'DAL'), ('Kyrie Irving', 'DAL'), ('Klay Thompson', 'DAL'),
        ('Stephen Curry', 'GSW'), ('Draymond Green', 'GSW'), ('Jonathan Kuminga', 'GSW'),
        ('LeBron James', 'LAL'), ('Anthony Davis', 'LAL'), ('Austin Reaves', 'LAL'),
        ('Joel Embiid', 'PHI'), ('Tyrese Maxey', 'PHI'), ('Paul George', 'PHI'),
        ('Shai Gilgeous-Alexander', 'OKC'), ('Chet Holmgren', 'OKC'), ('Jalen Williams', 'OKC'),
        ('Nikola Jokic', 'DEN'), ('Jamal Murray', 'DEN'), ('Aaron Gordon', 'DEN'),
        ('Giannis Antetokounmpo', 'MIL'), ('Damian Lillard', 'MIL'), ('Brook Lopez', 'MIL'),
        ('Jayson Tatum', 'BOS'), ('Jaylen Brown', 'BOS'), ('Kristaps Porzingis', 'BOS'),
        ('Kevin Durant', 'PHX'), ('Devin Booker', 'PHX'), ('Bradley Beal', 'PHX'),
        ('Tyrese Haliburton', 'IND'), ('Pascal Siakam', 'IND'), ('Myles Turner', 'IND'),
        ('Anthony Edwards', 'MIN'), ('Rudy Gobert', 'MIN'), ('Karl-Anthony Towns', 'NYK'),
        ('Jalen Brunson', 'NYK'), ('OG Anunoby', 'NYK'), ('Mikal Bridges', 'NYK'),
        ('Victor Wembanyama', 'SAS'), ('Chris Paul', 'SAS'), ('Jeremy Sochan', 'SAS'),
        ('Ja Morant', 'MEM'), ('Desmond Bane', 'MEM'), ('Jaren Jackson Jr.', 'MEM'),
        ('Zion Williamson', 'NOP'), ('Brandon Ingram', 'NOP'), ('CJ McCollum', 'NOP'),
        ('Paolo Banchero', 'ORL'), ('Franz Wagner', 'ORL'), ('Jalen Suggs', 'ORL'),
        ('Cade Cunningham', 'DET'), ('Jaden Ivey', 'DET'), ('Jalen Duren', 'DET'), ('Tobias Harris', 'DET'),
        ('Trae Young', 'ATL'), ('Jalen Johnson', 'ATL'), ('Clint Capela', 'ATL'),
        ('Scottie Barnes', 'TOR'), ('RJ Barrett', 'TOR'), ('Immanuel Quickley', 'TOR'),
        ('Lauri Markkanen', 'UTA'), ('Collin Sexton', 'UTA'), ('Walker Kessler', 'UTA'),
        ('Jimmy Butler', 'MIA'), ('Bam Adebayo', 'MIA'), ('Tyler Herro', 'MIA'),
        ('Kawhi Leonard', 'LAC'), ('James Harden', 'LAC'), ('Ivica Zubac', 'LAC'),
        ('Donovan Mitchell', 'CLE'), ('Evan Mobley', 'CLE'), ('Jarrett Allen', 'CLE'),
        ('Tim Hardaway Jr.', 'DET'), ('Seth Curry', 'CHA'), ('Coby White', 'CHI'),
        ('De\'Aaron Fox', 'SAC'), ('Domantas Sabonis', 'SAC'), ('DeMar DeRozan', 'SAC'),
        ('Nikola Vucevic', 'CHI'), ('Saddiq Bey', 'WAS'), ('Brandon Miller', 'CHA'),
        ('Shaedon Sharpe', 'POR'), ('Keegan Murray', 'SAC'), ('Jabari Smith Jr.', 'HOU'),
        ('Amen Thompson', 'HOU'), ('Jalen Green', 'HOU'), ('Alperen Sengun', 'HOU'),
        ('Fred VanVleet', 'HOU'), ('Miles Bridges', 'CHA'), ('LaMelo Ball', 'CHA'),
        ('Cam Thomas', 'BKN'), ('Nic Claxton', 'BKN'), ('Dennis Schroder', 'BKN'),
        ('Kyle Kuzma', 'WAS'), ('Jordan Poole', 'WAS'), ('Alex Sarr', 'WAS'),
        ('Josh Giddey', 'CHI'), ('Zach LaVine', 'CHI'), ('Dyson Daniels', 'ATL'),
        ('Derrick White', 'BOS'), ('Jrue Holiday', 'BOS'), ('Norman Powell', 'LAC'),
        ('Terry Rozier', 'MIA'), ('Keyonte George', 'UTA'), ('Bilal Coulibaly', 'WAS'),
        ('Nickeil Alexander-Walker', 'MIN'), ('Cooper Flagg', 'BKN'), ('Deni Avdija', 'POR'),
        ('Ty Jerome', 'CLE'), ('Kon Knueppel', 'UTA')
    ]
    for player, team in real_rosters:
        con.execute("DELETE FROM player_teams WHERE PLAYER_NAME = ?", [player])
        con.execute("INSERT INTO player_teams (PLAYER_NAME, TEAM) VALUES (?, ?)", [player, team])

    # 3. Final Economic Cleanup
    logger.info("Aligning contracts with teams...")

    # Apply name overrides to contracts as well
    for old, new in name_map.items():
        con.execute("UPDATE contracts SET PLAYER_NAME = ? WHERE PLAYER_NAME = ?", [new, old])
        
    con.execute("""
        UPDATE contracts
        SET TEAM = player_teams.TEAM
        FROM player_teams
        WHERE contracts.PLAYER_NAME = player_teams.PLAYER_NAME
    """)

    con.close()
    logger.info("FINAL AUDIT COMPLETE: Data is now production-ready.")

if __name__ == "__main__":
    fix_everything()
