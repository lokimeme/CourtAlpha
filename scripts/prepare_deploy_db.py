import duckdb
import os

SOURCE_DB = 'data/courtalpha.duckdb'
TARGET_DB = 'data/courtalpha_deploy.duckdb'

def prepare_deploy_db():
    print("Preparing lightweight deployment database...")
    
    if os.path.exists(TARGET_DB):
        os.remove(TARGET_DB)
        
    src_conn = duckdb.connect(SOURCE_DB)
    
    # Standard tables
    tables = ['contracts', 'player_metadata', 'player_metrics', 'player_teams']
    
    src_conn.execute(f"ATTACH '{TARGET_DB}' AS tgt")
    
    for t in tables:
        print(f"Copying {t}...")
        src_conn.execute(f"CREATE TABLE tgt.{t} AS SELECT * FROM main.{t}")

    print("Aggregating shot density data...")
    density_query = """
        SELECT 
            PLAYER_NAME,
            ROUND(LOC_X / 10) * 10 as BIN_X,
            ROUND(LOC_Y / 10) * 10 as BIN_Y,
            COUNT(*) as SHOT_COUNT
        FROM main.play_by_play
        WHERE PLAYER_NAME IS NOT NULL 
          AND LOC_X IS NOT NULL
          AND ACTION_TYPE IN ('Made Shot', 'Missed Shot')
          AND PLAYER_NAME NOT LIKE '%Putback%'
          AND PLAYER_NAME NOT LIKE '%Reverse%'
          AND PLAYER_NAME NOT LIKE '%Tip%'
        GROUP BY 1, 2, 3
    """
    src_conn.execute("CREATE TABLE tgt.player_shot_density AS " + density_query)
    
    src_conn.close()
    
    old_size = os.path.getsize(SOURCE_DB) / (1024*1024)
    new_size = os.path.getsize(TARGET_DB) / (1024*1024)
    print(f"Deployment DB created: {TARGET_DB}")
    print(f"Size reduced from {old_size:.1f}MB to {new_size:.1f}MB")

if __name__ == "__main__":
    prepare_deploy_db()
