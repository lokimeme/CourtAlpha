import duckdb
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Sanitizer")

FORBIDDEN = ['Putback', 'Reverse', 'Tip', 'Quarter', 'Final', 'End of', 'Shot Clock']

def sanitize_db(db_path):
    logger.info(f"Sanitizing {db_path}...")
    con = duckdb.connect(db_path)
    
    tables = con.execute("SHOW TABLES").df()['name'].tolist()
    
    for t in tables:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})").fetchall()]
        if 'PLAYER_NAME' in cols:
            logger.info(f"  Cleaning {t}...")
            for word in FORBIDDEN:
                con.execute(f"DELETE FROM {t} WHERE PLAYER_NAME LIKE '%{word}%'")
                
        # Specialized cleaning for play_by_play which might have noise in other cols
        if t == 'play_by_play':
            for word in FORBIDDEN:
                con.execute(f"DELETE FROM {t} WHERE DESCRIPTION LIKE '%{word}%' AND ACTION_TYPE NOT IN ('Made Shot', 'Missed Shot')")

    con.close()

if __name__ == "__main__":
    sanitize_db('data/courtalpha.duckdb')
    sanitize_db('data/courtalpha_deploy.duckdb')
    logger.info("Sanitization complete.")
