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
    # Strict filter: Only players who passed the 20-game / 100-FGA metric threshold
    density_query = """
        SELECT 
            pbp.PLAYER_NAME,
            ROUND(LOC_X / 10) * 10 as BIN_X,
            ROUND(LOC_Y / 10) * 10 as BIN_Y,
            COUNT(*) as SHOT_COUNT
        FROM main.play_by_play pbp
        JOIN tgt.player_metrics m ON pbp.PLAYER_NAME = m.PLAYER_NAME
        WHERE pbp.PLAYER_NAME IS NOT NULL 
          AND LOC_X IS NOT NULL
          AND ACTION_TYPE IN ('Made Shot', 'Missed Shot')
          AND pbp.SEASON = '2025-26'
        GROUP BY 1, 2, 3
    """
    src_conn.execute("CREATE TABLE tgt.player_shot_density AS " + density_query)

    print("Building PBP Tape for production...")
    tape_query = """
        SELECT pbp.PLAYER_NAME, pbp.PERIOD, pbp.CLOCK, pbp.ACTION_TYPE, pbp.SUB_TYPE, pbp.DESCRIPTION, pbp.GAME_ID, pbp.ACTION_NUMBER
        FROM main.play_by_play pbp
        JOIN tgt.player_metrics m ON pbp.PLAYER_NAME = m.PLAYER_NAME
        WHERE pbp.SEASON = '2025-26'
    """
    src_conn.execute("CREATE TABLE tgt.player_pbp_tape AS " + tape_query)
    
    src_conn.close()
    
    old_size = os.path.getsize(SOURCE_DB) / (1024*1024)
    new_size = os.path.getsize(TARGET_DB) / (1024*1024)
    print(f"Deployment DB created: {TARGET_DB}")
    print(f"Size reduced from {old_size:.1f}MB to {new_size:.1f}MB")

if __name__ == "__main__":
    prepare_deploy_db()
