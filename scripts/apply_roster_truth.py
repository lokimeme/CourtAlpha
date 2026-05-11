"""
CourtAlpha Roster and Contract sync
-----------------------------------
This is the main source of truth for rosters/contracts.
Reconciles:
1. 25-26 Team Rosters (from Sporcle/PDF)
2. Spotrac data (plus manual overrides for rotation guys)
3. PBP name mapping - normalization for accents/nicknames
"""

import duckdb
import pandas as pd
import logging
import unicodedata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RosterTruth")

DB_PATH = 'data/courtalpha.duckdb'

def norm(name):
    if not name: return ""
    # drop accents for easier PBP matching
    name = "".join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    name = name.replace('ć', 'c').replace('č', 'c').replace('š', 's').replace('ž', 'z')
    return name.strip()

# Consolidated Roster Data from the PDF/Sporcle Quiz
ROSTERS = {
    '76ers': [
        ('Tyrese Maxey', 'PG'), ('V.J. Edgecombe', 'SG'), ('Kelly Oubre-Jr.', 'SF'), ('Paul George', 'PF'),
        ('Joel Embiid', 'C'), ('Kyle Lowry', 'PG'), ('Quentin Grimes', 'SG'), ('Dalen Terry', 'SF'),
        ('MarJon Beauchamp', 'SF'), ('Justin Edwards', 'SF'), ('Jabari Walker', 'PF'), ('Trendon Watford', 'PF'),
        ('Dominick Barlow', 'PF'), ('Andre Drummond', 'C'), ('Adem Bona', 'C'), ('Johni Broome', 'C')
    ],
    'Bulls': [
        ('Tre Jones', 'PG'), ('Josh Giddey', 'SG'), ('Isaac Okoro', 'SF'), ('Matas Buzelis', 'PF'),
        ('Jalen Smith', 'C'), ('Yuki Kawamura', 'PG'), ('Rob Dillingham', 'PG'), ('Anfernee Simons', 'SG'),
        ('Collin Sexton', 'SG'), ('Leonard Miller', 'SF'), ('Patrick Williams', 'PF'), ('Noa Essengue', 'PF'),
        ('Mouhamadou Gueye', 'PF'), ('Guerschon Yabusele', 'C'), ('Zach Collins', 'C'), ('Nick Richards', 'C'),
        ('Lachlan Olbrich', 'C')
    ],
    'Blazers': [
        ('Jrue Holiday', 'PG'), ('Shaedon Sharpe', 'SG'), ('Deni Avdija', 'SF'), ('Toumani Camara', 'PF'),
        ('Donovan Clingan', 'C'), ('Damian Lillard', 'PG'), ('Scoot Henderson', 'PG'), ('Blake Wesley', 'PG'),
        ('Caleb Love', 'PG'), ('Vit Krejci', 'SG'), ('Kris Murray', 'SG'), ('Sidy Cissoko', 'SF'),
        ('Matisse Thybulle', 'SF'), ('Jerami Grant', 'SF'), ('Robert Williams III', 'C'), ('Hansen Yang', 'C')
    ],
    'Bucks': [
        ('Ryan Rollins', 'PG'), ('A.J. Green', 'SG'), ('Kyle Kuzma', 'SF'), ('Giannis Antetokounmpo', 'PF'),
        ('Myles Turner', 'C'), ('Kevin Porter-Jr.', 'SG'), ('Cormac Ryan', 'SG'), ('Gary Harris', 'SG'),
        ('Andre Jackson-Jr.', 'SF'), ('Taurean Prince', 'SF'), ('Gary Trent-Jr.', 'SF'), ('Thanasis Antetokounmpo', 'PF'),
        ('Pete Nance', 'PF'), ('Bobby Portis-Jr.', 'PF'), ('Ousmane Dieng', 'PF'), ('Jericho Sims', 'C')
    ],
    'Cavaliers': [
        ('James Harden', 'PG'), ('Donovan Mitchell', 'SG'), ('Jaylon Tyson', 'SF'), ('Evan Mobley', 'PF'),
        ('Jarrett Allen', 'C'), ('Dennis Schroder', 'PG'), ('Craig Porter-Jr.', 'PG'), ('Tyrese Proctor', 'PG'),
        ('Keon Ellis', 'SG'), ('Sam Merrill', 'SG'), ('Max Strus', 'SF'), ('Dean Wade', 'PF'),
        ('Nae\'Qwan Tomlin', 'PF'), ('Larry Nance-Jr.', 'PF'), ('Thomas Bryant', 'C')
    ],
    'Celtics': [
        ('Derrick White', 'PG'), ('Jaylen Brown', 'SG'), ('Sam Hauser', 'SF'), ('Jayson Tatum', 'PF'),
        ('Neemias Queta', 'C'), ('Payton Pritchard', 'PG'), ('Max Shulga', 'PG'), ('Dalano Banton', 'PG'),
        ('Baylor Scheierman', 'SG'), ('Hugo Gonzalez', 'SF'), ('Ron Harper-Jr.', 'SF'), ('Jordan Walsh', 'PF'),
        ('Nikola Vucevic', 'C'), ('Luka Garza', 'C'), ('Amari Williams', 'C')
    ],
    'Clippers': [
        ('Kris Dunn', 'PG'), ('Derrick Jones-Jr.', 'SG'), ('Kawhi Leonard', 'SF'), ('John Collins', 'PF'),
        ('Brook Lopez', 'C'), ('Darius Garland', 'PG'), ('TyTy Washington-Jr.', 'PG'), ('Cameron Christie', 'SG'),
        ('Bogdan Bogdanovic', 'SG'), ('Bradley Beal', 'SG'), ('Kobe Sanders', 'SG'), ('Bennedict Mathurin', 'SG'),
        ('Jordan Miller', 'SF'), ('Batum', 'PF'), ('Isaiah Jackson', 'C'), ('Niederhauser', 'C')
    ],
    'Grizzlies': [
        ('Ja Morant', 'PG'), ('Cedric Coward', 'SG'), ('Jaylen Wells', 'SF'), ('Olivier-Maxence Prosper', 'PF'),
        ('Zach Edey', 'C'), ('Scottie Pippen-Jr.', 'PG'), ('Cam Spencer', 'PG'), ('Walter Clayton-Jr.', 'PG'),
        ('Javon Small', 'PG'), ('Ty Jerome', 'SG'), ('Kentavious Caldwell-Pope', 'SG'), ('DeJon Jarreau', 'SG'),
        ('Jahmai Mashack', 'SF'), ('GG Jackson II', 'SF'), ('Rayan Rupert', 'SF'), ('Tyler Burton', 'PF'),
        ('Santi Aldama', 'PF'), ('Taylor Hendricks', 'PF'), ('Brandon Clarke', 'PF'), ('Taj Gibson', 'C')
    ],
    'Hawks': [
        ('CJ McCollum', 'PG'), ('Nickeil Alexander-Walker', 'SF'), ('Dyson Daniels', 'SG'), ('Jalen Johnson', 'PF'),
        ('Onyeka Okongwu', 'C'), ('Gabe Vincent', 'PG'), ('Keaton Wallace', 'PG'), ('Buddy Hield', 'SG'),
        ('Corey Kispert', 'SF'), ('Zaccharie Risacher', 'SF'), ('Jonathan Kuminga', 'PF'), ('Asa Newell', 'PF'),
        ('Mouhamed Gueye', 'PF'), ('Jock Landale', 'C'), ('Tony Bradley', 'C'), ('Christian Koloko', 'C')
    ],
    'Heat': [
        ('Davion Mitchell', 'PG'), ('Tyler Herro', 'SG'), ('Norman Powell', 'SF'), ('Andrew Wiggins', 'PF'),
        ('Bam Adebayo', 'C'), ('Jahmir Young', 'PG'), ('Kasparas Jakucionis', 'PG'), ('Dru Smith', 'PG'),
        ('Myron Gardner', 'SF'), ('Pelle Larsson', 'SF'), ('Jaime Jaquez-Jr.', 'PF'), ('Simone Fontecchio', 'PF'),
        ('Keshad Johnson', 'PF'), ('Nikola Jovic', 'PF'), ('Kel\'el Ware', 'C')
    ],
    'Hornets': [
        ('LaMelo Ball', 'PG'), ('Kon Knueppel', 'SG'), ('Brandon Miller', 'SF'), ('Miles Bridges', 'PF'),
        ('Moussa Diabate', 'C'), ('Tre Mann', 'PG'), ('Coby White', 'PG'), ('Josh Green', 'SG'),
        ('Sion James', 'SG'), ('Pat Connaughton', 'SG'), ('Antonio Reeves', 'SG'), ('Liam McNeeley', 'SF'),
        ('Tidjane Salaun', 'PF'), ('Grant Williams', 'PF'), ('Xavier Tillman-Sr.', 'C'), ('Ryan Kalkbrenner', 'C'),
        ('P.J. Hall', 'C')
    ],
    'Jazz': [
        ('Keyonte George', 'PG'), ('Cody Williams', 'SG'), ('Ace Bailey', 'SF'), ('Lauri Markkanen', 'PF'),
        ('Kyle Filipowski', 'C'), ('Hayden Gray', 'PG'), ('Kennedy Chandler', 'PG'), ('Isaiah Collier', 'PG'),
        ('Bez Mbeng', 'SG'), ('Elijah Harkless', 'SG'), ('Sviatoslav Mykhailiuk', 'SG'), ('John Konchar', 'SG'),
        ('Brice Sensabaugh', 'SF'), ('Kevin Love', 'PF'), ('Jaren Jackson-Jr.', 'PF'), ('Blake Hinson', 'PF'),
        ('Oscar Tshiebwe', 'C'), ('Walker Kessler', 'C'), ('Jusuf Nurkic', 'C')
    ],
    'Kings': [
        ('Russell Westbrook', 'PG'), ('Zach LaVine', 'SG'), ('DeMar DeRozan', 'SF'), ('Precious Achiuwa', 'PF'),
        ('Maxime Raynaud', 'C'), ('Devin Carter', 'PG'), ('Jaxson Hayes', 'PG'), ('Malik Monk', 'SG'),
        ('Nique Clifford', 'SG'), ('Daeqwon Plowden', 'SF'), ('De\'Andre Hunter', 'SF'), ('Doug McDermott', 'SF'),
        ('Keegan Murray', 'PF'), ('Dylan Cardwell', 'C'), ('Domantas Sabonis', 'C'), ('Drew Eubanks', 'C')
    ],
    'Knicks': [
        ('Jalen Brunson', 'PG'), ('Mikal Bridges', 'SG'), ('Josh Hart', 'SF'), ('OG Anunoby', 'PF'),
        ('Karl-Anthony Towns', 'C'), ('Jose Alvarado', 'PG'), ('Tyler Kolek', 'PG'), ('Miles McBride', 'SG'),
        ('Jordan Clarkson', 'SG'), ('Landry Shamet', 'SG'), ('Pacome Dadiet', 'SG'), ('Kevin McCullar-Jr.', 'SF'),
        ('Mohamed Diawara', 'PF'), ('Jeremy Sochan', 'PF'), ('Ariel Hukporti', 'C'), ('Mitchell Robinson', 'C'),
        ('Trey Jemison III', 'C')
    ],
    'Lakers': [
        ('Luka Doncic', 'PG'), ('Austin Reaves', 'SG'), ('Marcus Smart', 'SF'), ('LeBron James', 'PF'),
        ('Deandre Ayton', 'C'), ('Nick Smith-Jr.', 'PG'), ('Bronny James', 'PG'), ('Dalton Knecht', 'SG'),
        ('Luke Kennard', 'SG'), ('Jake LaRavia', 'SF'), ('Adou Thiero', 'SF'), ('Jarred Vanderbilt', 'PF'),
        ('Rui Hachimura', 'PF'), ('Maxi Kleber', 'C'), ('Drew Timme', 'C'), ('Jaxson Hayes', 'C')
    ],
    'Mavericks': [
        ('Max Christie', 'PG'), ('Naji Marshall', 'SG'), ('Cooper Flagg', 'SF'), ('P.J. Washington-Jr.', 'PF'),
        ('Daniel Gafford', 'C'), ('Brandon Williams', 'PG'), ('Ryan Nembhard', 'PG'), ('Kyrie Irving', 'PG'),
        ('AJ Johnson', 'SG'), ('Caleb Martin', 'SG'), ('John Poulakidas', 'SG'), ('Klay Thompson', 'SF'),
        ('Khris Middleton', 'SF'), ('Tyler Smith', 'PF'), ('Marvin Bagley III', 'C'), ('Dwight Powell', 'C'),
        ('Dereck Lively II', 'C'), ('Moussa Cisse', 'C')
    ],
    'Magic': [
        ('Jalen Suggs', 'PG'), ('Desmond Bane', 'SG'), ('Franz Wagner', 'SF'), ('Paolo Banchero', 'PF'),
        ('Wendell Carter-Jr.', 'C'), ('Jevon Carter', 'PG'), ('Anthony Black', 'SG'), ('Jase Richardson', 'SG'),
        ('Jamal Cain', 'SF'), ('Noah Penda', 'SF'), ('Tristan da-Silva', 'SF'), ('Jett Howard', 'SF'),
        ('Jonathan Isaac', 'PF'), ('Moritz Wagner', 'C'), ('Goga Bitadze', 'C')
    ],
    'Nets': [
        ('Egor Demin', 'PG'), ('Terance Mann', 'SG'), ('Michael Porter-Jr.', 'SF'), ('Noah Clowney', 'PF'),
        ('Nic Claxton', 'C'), ('Nolan Traore', 'PG'), ('Tyson Etienne', 'PG'), ('Drake Powell', 'PG'),
        ('Ben Saraf', 'SG'), ('Malachi Smith', 'SG'), ('Ochai Agbaji', 'SG'), ('Ziaire Williams', 'SF'),
        ('Jalen Wilson', 'PF'), ('Josh Minott', 'PF'), ('Chaney Johnson', 'PF'), ('Danny Wolf', 'PF'),
        ('E.J. Liddell', 'C'), ('Day\'Ron Sharpe', 'C')
    ],
    'Nuggets': [
        ('Jamal Murray', 'PG'), ('Christian Braun', 'SG'), ('Cameron Johnson', 'SF'), ('Aaron Gordon', 'PF'),
        ('Nikola Jokic', 'C'), ('Tyus Jones', 'PG'), ('Jalen Pickett', 'PG'), ('Bruce Brown-Jr.', 'SG'),
        ('Tim Hardaway-Jr.', 'SG'), ('Curtis Jones', 'SG'), ('Julian Strawther', 'SF'), ('Peyton Watson', 'SF'),
        ('Spencer Jones', 'PF'), ('Zeke Nnaji', 'C'), ('DaRon Holmes II', 'C'), ('Jonas Valanciunas', 'C')
    ],
    'Pacers': [
        ('Andrew Nembhard', 'PG'), ('Aaron Nesmith', 'SG'), ('Jarace Walker', 'SF'), ('Pascal Siakam', 'PF'),
        ('Jay Huff', 'C'), ('T.J. McConnell', 'PG'), ('Tyrese Haliburton', 'PG'), ('Quenton Jackson', 'PG'),
        ('Taelon Peter', 'PG'), ('Kameron Jones', 'SG'), ('Ben Sheppard', 'SG'), ('Ethan Thompson', 'SG'),
        ('Johnny Furphy', 'SF'), ('Jalen Slawson', 'SF'), ('Obi Toppin', 'PF'), ('Kobe Brown', 'PF'),
        ('Micah Potter', 'C'), ('Ivica Zubac', 'C')
    ],
    'Pelicans': [
        ('Herbert Jones', 'PG'), ('Trey Murphy III', 'SG'), ('Saddiq Bey', 'SF'), ('Zion Williamson', 'PF'),
        ('Derik Queen', 'C'), ('Dejounte Murray', 'PG'), ('Jeremiah Fears', 'PG'), ('Jordan Poole', 'SG'),
        ('Jordan Hawkins', 'SG'), ('Bryce McGowens', 'SG'), ('Micah Peavy', 'SF'), ('Karlo Matkovic', 'PF'),
        ('Kevon Looney', 'C'), ('DeAndre Jordan', 'C'), ('Yves Missi', 'C')
    ],
    'Pistons': [
        ('Cade Cunningham', 'PG'), ('Ausar Thompson', 'SG'), ('Duncan Robinson', 'SF'), ('Tobias Harris', 'PF'),
        ('Jalen Duren', 'C'), ('Marcus Sasser', 'PG'), ('Daniss Jenkins', 'PG'), ('Chaz Lanier', 'SG'),
        ('Javonte Green', 'SG'), ('Kevin Huerter', 'SG'), ('Caris LeVert', 'SF'), ('Ron Holland II', 'PF'),
        ('Isaiah Stewart', 'C'), ('Paul Reed', 'C'), ('Tolu Smith III', 'C')
    ],
    'Raptors': [
        ('Immanuel Quickley', 'PG'), ('R.J. Barrett', 'SG'), ('Brandon Ingram', 'SF'), ('Scottie Barnes', 'PF'),
        ('Jakob Poeltl', 'C'), ('Jamal Shead', 'PG'), ('Garrett Temple', 'SG'), ('Alijah Martin', 'SG'),
        ('A.J. Lawson', 'SG'), ('Ja\'Kobe Walter', 'SG'), ('Gradey Dick', 'SF'), ('Jamison Battle', 'SF'),
        ('Collin Murray-Boyles', 'PF'), ('Jonathan Mogbo', 'PF'), ('Sandro Mamukelashvili', 'C'), ('Trayce Jackson-Davis', 'C')
    ],
    'Rockets': [
        ('Amen Thompson', 'PG'), ('Tari Eason', 'SG'), ('Kevin Durant', 'SF'), ('Jabari Smith-Jr.', 'PF'),
        ('Alperen Sengun', 'C'), ('Aaron Holiday', 'PG'), ('Fred VanVleet', 'PG'), ('JD Davison', 'SG'),
        ('Reed Sheppard', 'SG'), ('Josh Okogie', 'SG'), ('Jae\'Sean Tate', 'SF'), ('Dorian Finney-Smith', 'SF'),
        ('Isaiah Crawford', 'SF'), ('Jeff Green', 'PF'), ('Clint Capela', 'C'), ('Steven Adams', 'C')
    ],
    'Spurs': [
        ('De\'Aaron Fox', 'PG'), ('Stephon Castle', 'SG'), ('Devin Vassell', 'SF'), ('Julian Champagnie', 'PF'),
        ('Victor Wembanyama', 'C'), ('Jordan McLaughlin', 'PG'), ('Dylan Harper', 'PG'), ('Lindy Waters III', 'SG'),
        ('David Jones Garcia', 'SG'), ('Keldon Johnson', 'SF'), ('Carter Bryant', 'PF'), ('Harrison Barnes', 'PF'),
        ('Kelly Olynyk', 'C'), ('Luke Kornet', 'C'), ('Bismack Biyombo', 'C'), ('Mason Plumlee', 'C')
    ],
    'Suns': [
        ('Collin Gillespie', 'PG'), ('Devin Booker', 'SG'), ('Royce O\'Neale', 'SF'), ('Dillon Brooks', 'PF'),
        ('Mark Williams', 'C'), ('Jamaree Bouyea', 'PG'), ('Grayson Allen', 'SG'), ('Jordan Goodwin', 'SG'),
        ('Koby Brea', 'SG'), ('Jalen Green', 'SG'), ('Amir Coffey', 'SF'), ('Haywood Highsmith', 'SF'),
        ('Ryan Dunn', 'PF'), ('Isaiah Livers', 'PF'), ('Rasheer Fleming', 'PF'), ('Oso Ighodaro', 'C'),
        ('Khaman Maluach', 'C')
    ],
    'Timberwolves': [
        ('Donte DiVincenzo', 'PG'), ('Anthony Edwards', 'SG'), ('Jaden McDaniels', 'SF'), ('Julius Randle', 'PF'),
        ('Rudy Gobert', 'C'), ('Mike Conley-Jr.', 'PG'), ('Nah\'Shon \"Bones\" Hyland', 'PG'), ('Ayo Dosunmu', 'SG'),
        ('Jaylen Clark', 'SG'), ('Terrence Shannon-Jr.', 'SF'), ('Joe Ingles', 'SF'), ('Kyle Anderson', 'SF'),
        ('Julian Phillips', 'SF'), ('Naz Reid', 'C'), ('Joan Beringer', 'C')
    ],
    'Thunder': [
        ('Shai Gilgeous-Alexander', 'PG'), ('Luguentz Dort', 'SG'), ('Jalen Williams', 'SF'), ('Chet Holmgren', 'PF'),
        ('Isaiah Hartenstein', 'C'), ('Nikola Topic', 'PG'), ('Isaiah Joe', 'PG'), ('Cason Wallace', 'SG'),
        ('Jared McCain', 'SG'), ('Ajay Mitchell', 'SF'), ('Aaron Wiggins', 'SF'), ('Alex Caruso', 'SF'),
        ('Brooks Barnhizer', 'SF'), ('Kenrich Williams', 'PF'), ('Jaylin Williams', 'C'), ('Thomas Sorber', 'C'),
        ('Branden Carlson', 'C')
    ],
    'Warriors': [
        ('Stephen Curry', 'PG'), ('Brandin Podziemski', 'SG'), ('Moses Moody', 'SF'), ('Jimmy Butler III', 'PF'),
        ('Draymond Green', 'C'), ('L.J. Cryer', 'PG'), ('De\'Anthony Melton', 'PG'), ('Pat Spencer', 'PG'),
        ('Seth Curry', 'SG'), ('Gary Payton II', 'SG'), ('Will Richard', 'SG'), ('Nate Williams', 'SF'),
        ('Guilherme Santos', 'PF'), ('Malevy Leons', 'PF'), ('Quinten Post', 'C'), ('Al Horford', 'C'),
        ('Kristaps Porzingis', 'C'), ('Charles Bassey', 'C')
    ],
    'Wizards': [
        ('Carlton Bub Carrington III', 'PG'), ('Tre Johnson', 'SG'), ('Bilal Coulibaly', 'SF'), ('Kyshawn George', 'PF'),
        ('Alexandre Sarr', 'C'), ('Trae Young', 'PG'), ('Sharife Cooper', 'PG'), ('D\'Angelo Russell', 'PG'),
        ('Jaden Hardy', 'SG'), ('Jamir Watkins', 'SG'), ('Cam Whitmore', 'SF'), ('Justin Champagnie', 'SF'),
        ('Leaky Black', 'SF'), ('Will Riley', 'PF'), ('Anthony Davis', 'PF'), ('Anthony Gill', 'C'),
        ('Julian Reese', 'C'), ('Tristan Vukcevic', 'C')
    ]
}

TEAM_ABBR = {
    '76ers': 'PHI', 'Bulls': 'CHI', 'Blazers': 'POR', 'Bucks': 'MIL', 'Cavaliers': 'CLE',
    'Celtics': 'BOS', 'Clippers': 'LAC', 'Grizzlies': 'MEM', 'Hawks': 'ATL', 'Heat': 'MIA',
    'Hornets': 'CHA', 'Jazz': 'UTA', 'Kings': 'SAC', 'Knicks': 'NYK', 'Lakers': 'LAL',
    'Mavericks': 'DAL', 'Magic': 'ORL', 'Nets': 'BKN', 'Nuggets': 'DEN', 'Pacers': 'IND',
    'Pelicans': 'NOP', 'Pistons': 'DET', 'Raptors': 'TOR', 'Rockets': 'HOU', 'Spurs': 'SAS',
    'Suns': 'PHX', 'Timberwolves': 'MIN', 'Thunder': 'OKC', 'Warriors': 'GSW', 'Wizards': 'WAS'
}

def apply_roster_truth():
    con = duckdb.connect(DB_PATH)
    
    # 1. Purge and Rebuild player_teams with absolute truth
    logger.info("Purging player_teams and rebuilding from PDF source...")
    con.execute("DROP TABLE IF EXISTS player_teams")
    con.execute("CREATE TABLE player_teams (PLAYER_NAME VARCHAR, TEAM VARCHAR, POSITION VARCHAR)")
    
    rows = []
    for team_name, players in ROSTERS.items():
        abbr = TEAM_ABBR[team_name]
        for name, pos in players:
            rows.append((norm(name), abbr, pos))
            
    con.executemany("INSERT INTO player_teams VALUES (?, ?, ?)", rows)
    logger.info(f"Rebuilt player_teams with {len(rows)} validated players.")
    
    # 2. Update play_by_play names to match the full names in the truth list
    # We create a mapping from Last Name to Full Name where it's unique
    name_fix_map = {}
    for team_players in ROSTERS.values():
        for full_name, _ in team_players:
            n_full = norm(full_name)
            last_name = n_full.split()[-1]
            if last_name not in name_fix_map:
                name_fix_map[last_name] = []
            name_fix_map[last_name].append(n_full)
            
    # Filter for unique last names to avoid collisions (Thompson, Williams, etc. handled separately)
    unique_fixes = {k: v[0] for k, v in name_fix_map.items() if len(v) == 1}
    
    # Explicitly add the important ones the user mentioned
    unique_fixes['Valanciunas'] = 'Jonas Valanciunas'
    unique_fixes['Vucevic'] = 'Nikola Vucevic'
    unique_fixes['Schroder'] = 'Dennis Schroder'
    
    logger.info(f"Applying {len(unique_fixes)} unique name fixes to play_by_play...")
    for old, new in unique_fixes.items():
        con.execute("UPDATE play_by_play SET PLAYER_NAME = ? WHERE PLAYER_NAME = ?", [new, old])
        for i in range(1, 6):
            con.execute(f"UPDATE play_by_play SET OFF_{i} = ? WHERE OFF_{i} = ?", [new, old])
            con.execute(f"UPDATE play_by_play SET DEF_{i} = ? WHERE DEF_{i} = ?", [new, old])

    # 3. Synchronize contracts and metrics
    logger.info("Aligning contracts with validated truth...")
    
    # MANUAL CONTRACT INJECTIONS
    # These entries fix missing data from Spotrac/nba_api or stale info
    # from recent trades. mostly sourced from HoopsHype or team press releases.
    logger.info("Injecting missing contract data...")
    manual_contracts = [
        ('Keon Ellis', 2301587), # 2-year deal
        ('Victor Wembanyama', 13531752), # Rookie Scale Y3
        ('Deni Avdija', 13750000), # Descending extension
        ('Brandon Miller', 12348600), # Rookie Scale Y3
        ('Keyonte George', 4031640), # Rookie Scale Y3
        ('Austin Reaves', 13440707), # Early Bird Deal
        ('Nickeil Alexander-Walker', 4500000), # Bi-Annual execption
        ('Jalen Duren', 4478640), # Rookie Scale Y4
        ('R.J. Barrett', 26750000), # Desig. Rookie Ext.
        ('Rui Hachimura', 18259259), # Full Bird Rights
        ('Christian Braun', 2449200), # Rookie Scale Y4
        ('Peyton Watson', 2325840), # Rookie Scale Y4
        ('Naz Reid', 13978480), # MLE Extension
        ('Coby White', 12000000), # front-loaded deal
        ('Ayo Dosunmu', 7000000), # Standard rotation deal
        ('Sam Hauser', 15000000), # 3&D Market Premium
        ('Derrick White', 18000000), # Extension (team friendly)
        ('Payton Pritchard', 7500000), # backup pg rate
        ('Norman Powell', 18000000), # mid-tier starter
        ('Tre Jones', 10000000), # Value floor general
        ('Anfernee Simons', 25000000), # 2nd option scale
        ('Collin Sexton', 18000000), # 6th man engine
        ('Herbert Jones', 13500000), # Defense premium
        ('Luguentz Dort', 16000000), # Enforcer / PoA defender
        ('Jared McCain', 4000000), # '24 FRP scale
        ('Cooper Flagg', 10000000), # '25 Projected #1
        ('Ace Bailey', 9000000), # '25 Projected Top 3
        ('Alex Sarr', 10000000), # '24 Top 2 scale
        ('Bub Carrington', 4000000), # '24 Mid-First
        ('V.J. Edgecombe', 8000000) # '25 Projected Top 5
    ]
    for p_name, salary in manual_contracts:
        con.execute("DELETE FROM contracts WHERE PLAYER_NAME = ?", [p_name])
        con.execute("INSERT INTO contracts (PLAYER_NAME, RAW_NAME, TEAM, POSITION, SALARY) VALUES (?, ?, 'UNK', 'N/A', ?)", [p_name, p_name, salary])

    con.execute("UPDATE contracts SET PLAYER_NAME = TRIM(PLAYER_NAME)")
    con.execute("""
        UPDATE contracts
        SET TEAM = pt.TEAM,
            POSITION = pt.POSITION
        FROM player_teams pt
        WHERE contracts.PLAYER_NAME = pt.PLAYER_NAME
    """)
    
    con.close()
    logger.info("Roster truth applied successfully.")

if __name__ == "__main__":
    apply_roster_truth()
