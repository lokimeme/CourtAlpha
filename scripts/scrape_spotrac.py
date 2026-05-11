import requests
from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import re
import logging
import unicodedata

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SpotracScraper")

DB_PATH = 'data/courtalpha.duckdb'
URL = 'https://www.spotrac.com/nba/contracts/'

def normalize_name(name):
    if not name: return None
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    # Keep Jr., III, etc. but clean extra whitespace
    return name.strip()

def scrape_spotrac():
    all_players = []
    page = 1
    
    while True:
        url = URL if page == 1 else f"{URL}_/page/{page}/"
        logger.info(f"Fetching Spotrac data from {url}...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        try:
            r = requests.get(url, headers=headers)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch Spotrac data for page {page}: {e}")
            break

        soup = BeautifulSoup(r.text, 'html.parser')
        rows = soup.select('table tbody tr')
        
        if not rows:
            break
            
        logger.info(f"Parsing {len(rows)} player rows from page {page}...")
        
        page_players = 0
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 9: continue
            
            name_a = tds[0].find('a')
            if not name_a: continue
            
            raw_name = name_a.text.strip()
            norm_name = normalize_name(raw_name)
            
            pos = tds[1].text.strip()
            team = tds[2].text.strip().split('\n')[0]
            
            try:
                length = int(re.sub(r'[^\d]', '', tds[6].text.strip()))
                total_val = int(re.sub(r'[^\d]', '', tds[7].text.strip()))
                avg_salary = int(re.sub(r'[^\d]', '', tds[8].text.strip()))
            except:
                length, total_val, avg_salary = 0, 0, 0

            all_players.append({
                'PLAYER_NAME': norm_name,
                'RAW_NAME': raw_name,
                'TEAM': team,
                'POSITION': pos,
                'SALARY': avg_salary,
                'TOTAL_VALUE': total_val,
                'LENGTH': length
            })
            page_players += 1
            
        if page_players == 0:
            break
            
        page += 1
        if page > 10: break

    if not all_players:
        logger.warning("No players extracted. Spotrac structure might have changed.")
        return

    df = pd.DataFrame(all_players)
    logger.info(f"Successfully extracted {len(df)} player contracts across {page-1} pages.")

    con = duckdb.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS contracts")
    con.execute("""
        CREATE TABLE contracts (
            PLAYER_NAME VARCHAR,
            RAW_NAME VARCHAR,
            TEAM VARCHAR,
            POSITION VARCHAR,
            SALARY BIGINT,
            TOTAL_VALUE BIGINT,
            LENGTH INTEGER
        )
    """)
    
    con.register('temp_contracts', df)
    con.execute("INSERT INTO contracts SELECT * FROM temp_contracts")
    con.unregister('temp_contracts')
    
    con.execute("UPDATE player_metrics SET CONTRACT_COST = 0")

    logger.info("Updating player_metrics with real contract costs (Fuzzy Matching)...")
    
    con.execute("""
        UPDATE player_metrics
        SET CONTRACT_COST = contracts.SALARY
        FROM contracts
        WHERE player_metrics.PLAYER_NAME = contracts.PLAYER_NAME
    """)
    
    pending = con.execute("SELECT PLAYER_NAME FROM player_metrics WHERE CONTRACT_COST = 0").df()
    if not pending.empty:
        init_map = {}
        for _, row in df.iterrows():
            name = row['RAW_NAME']
            parts = name.split()
            if len(parts) >= 2:
                init_name = f"{parts[0][0]}. {' '.join(parts[1:])}"
                init_map[init_name] = row['SALARY']
        
        updates = []
        for p in pending['PLAYER_NAME']:
            if p in init_map:
                updates.append((init_map[p], p))
        
        if updates:
            logger.info(f"Found {len(updates)} additional matches via Initials.")
            up_df = pd.DataFrame(updates, columns=['SALARY', 'NAME'])
            con.register('temp_fuzzy', up_df)
            con.execute("""
                UPDATE player_metrics
                SET CONTRACT_COST = temp_fuzzy.SALARY
                FROM temp_fuzzy
                WHERE player_metrics.PLAYER_NAME = temp_fuzzy.NAME
            """)
            con.unregister('temp_fuzzy')

    con.execute("UPDATE player_metrics SET CONTRACT_COST = 1121428 WHERE CONTRACT_COST = 0 AND FGA > 0")
    
    con.close()
    logger.info("Spotrac data integration complete.")

if __name__ == "__main__":
    scrape_spotrac()
