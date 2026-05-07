import duckdb
import pandas as pd
import logging
import unicodedata
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UnifyNames")

DB_PATH = 'data/courtalpha.duckdb'

def normalize_name(name):
    if not name: return ""
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    # Preserve suffixes but strip edges
    return name.strip()

def unify_player_names():
    con = duckdb.connect(DB_PATH)
    logger.info("Starting Player Name Unification...")

    # Manual Overrides for common abbreviations in PBP
    manual_overrides = {
        'St. Curry': 'Stephen Curry',
        'Se. Curry': 'Seth Curry',
        'L. Doncic': 'Luka Doncic',
        'Le. James': 'LeBron James',
        'K. Durant': 'Kevin Durant',
        'J. Embiid': 'Joel Embiid',
        'G. Antetokounmpo': 'Giannis Antetokounmpo',
        'S. Gilgeous-Alexander': 'Shai Gilgeous-Alexander',
        'Ja. Williams': 'Jalen Williams',
        'Jal. Williams': 'Jalen Williams',
        'Jay. Williams': 'Jaylin Williams',
        'M. Porter Jr.': 'Michael Porter Jr.',
        'K. Towns': 'Karl-Anthony Towns',
        'D. Sabonis': 'Domantas Sabonis'
    }

    meta_df = con.execute("SELECT PLAYER_NAME FROM player_metadata").df()
    contract_df = con.execute("SELECT PLAYER_NAME FROM contracts").df()
    
    meta_names = list(set(meta_df['PLAYER_NAME'].tolist() + contract_df['PLAYER_NAME'].tolist()))
    
    match_map = {}
    last_name_buckets = {}
    
    # Absolute Star Disambiguation (When only last name is scraped)
    star_disambiguation = {
        'Curry': 'Stephen Curry',
        'James': 'LeBron James',
        'Durant': 'Kevin Durant',
        'Doncic': 'Luka Doncic',
        'Embiid': 'Joel Embiid',
        'Antetokounmpo': 'Giannis Antetokounmpo',
        'Jokic': 'Nikola Jokic',
        'Tatum': 'Jayson Tatum',
        'Booker': 'Devin Booker',
        'Lillard': 'Damian Lillard',
        'Mitchell': 'Donovan Mitchell',
        'Brunson': 'Jalen Brunson',
        'Morant': 'Ja Morant',
        'Wembanyama': 'Victor Wembanyama',
        'Gilgeous-Alexander': 'Shai Gilgeous-Alexander',
        'Adebayo': 'Bam Adebayo',
        'Banchero': 'Paolo Banchero',
        'Haliburton': 'Tyrese Haliburton',
        'Maxey': 'Tyrese Maxey',
        'Fox': 'De\'Aaron Fox',
        'Sabonis': 'Domantas Sabonis',
        'Gobert': 'Rudy Gobert',
        'Porzingis': 'Kristaps Porzingis',
        'Siakam': 'Pascal Siakam',
        'Bridges': 'Mikal Bridges',
        'Towns': 'Karl-Anthony Towns',
        'Leonard': 'Kawhi Leonard',
        'Harden': 'James Harden',
        'George': 'Paul George',
        'Davis': 'Anthony Davis',
        'Edwards': 'Anthony Edwards',
        'Butler': 'Jimmy Butler',
        'DeRozan': 'DeMar DeRozan',
        'LaVine': 'Zach LaVine',
        'Williamson': 'Zion Williamson',
        'Ingram': 'Brandon Ingram',
        'McCollum': 'CJ McCollum',
        'Barnes': 'Scottie Barnes',
        'Mobley': 'Evan Mobley',
        'Allen': 'Jarrett Allen',
        'Duren': 'Jalen Duren',
        'Vucevic': 'Nikola Vucevic',
        'Bey': 'Saddiq Bey',
        'White': 'Coby White',
        'Miller': 'Brandon Miller',
        'Gordon': 'Aaron Gordon',
        'Sharpe': 'Shaedon Sharpe',
        'Brown': 'Jaylen Brown',
        'Murray': 'Keegan Murray',
        'Smith Jr.': 'Jabari Smith Jr.'
    }
    
    for full_name in meta_names:
        if not full_name: continue
        norm_full = normalize_name(full_name)
        match_map[norm_full] = full_name
        
        parts = norm_full.split()
        if len(parts) >= 2:
            init_name = f"{parts[0][0]}. {' '.join(parts[1:])}"
            match_map[init_name] = full_name
            
            last_name = parts[-1]
            if last_name not in last_name_buckets:
                last_name_buckets[last_name] = []
            if full_name not in last_name_buckets[last_name]:
                last_name_buckets[last_name].append(full_name)

    # We pull from all relevant columns to find every name that needs fixing
    lineup_cols = [f"OFF_{i}" for i in range(1, 6)] + [f"DEF_{i}" for i in range(1, 6)]
    all_cols = ["PLAYER_NAME"] + lineup_cols
    
    logger.info("Scanning all columns for names to unify...")
    names_query = " UNION ".join([f"SELECT DISTINCT {c} as name FROM play_by_play WHERE {c} IS NOT NULL" for c in all_cols])
    raw_players = con.execute(names_query).df()['name'].tolist()
    
    updates = []
    success_count = 0
    
    for p in raw_players:
        if p in manual_overrides:
            updates.append((manual_overrides[p], p))
            success_count += 1
            continue
            
        if p in star_disambiguation:
            updates.append((star_disambiguation[p], p))
            success_count += 1
            continue

        norm_p = normalize_name(p)
        
        if norm_p in match_map:
            new_name = match_map[norm_p]
            if new_name != p:
                updates.append((new_name, p))
                success_count += 1
            continue
            
        if norm_p in last_name_buckets and len(last_name_buckets[norm_p]) == 1:
            new_name = last_name_buckets[norm_p][0]
            if new_name != p:
                updates.append((new_name, p))
                success_count += 1
            continue

    if updates:
        logger.info(f"Applying {len(updates)} name unifications to source tables...")
        up_df = pd.DataFrame(updates, columns=['NEW', 'OLD'])
        con.register('temp_unify', up_df)
        
        logger.info("Updating play_by_play table (main column)...")
        con.execute("""
            UPDATE play_by_play
            SET PLAYER_NAME = temp_unify.NEW
            FROM temp_unify
            WHERE play_by_play.PLAYER_NAME = temp_unify.OLD
        """)

        # NEW: Update all lineup columns to ensure consistent RAPM training
        lineup_cols = [f"OFF_{i}" for i in range(1, 6)] + [f"DEF_{i}" for i in range(1, 6)]
        for col in lineup_cols:
            logger.info(f"  Updating {col}...")
            con.execute(f"""
                UPDATE play_by_play
                SET {col} = temp_unify.NEW
                FROM temp_unify
                WHERE play_by_play.{col} = temp_unify.OLD
            """)

        con.unregister('temp_unify')
    
    con.close()
    logger.info(f"Unification complete. Fixed {success_count} names.")

if __name__ == "__main__":
    unify_player_names()
