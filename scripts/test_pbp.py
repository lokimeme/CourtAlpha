from nba_api.stats.endpoints import playbyplayv3
import pandas as pd

def test_pbp(game_id):
    try:
        pbp = playbyplayv3.PlayByPlayV3(game_id=game_id)
        df = pbp.get_data_frames()[0]
        print("PBP Columns:", df.columns.tolist())
        print("\nSample Row:")
        print(df.iloc[10].to_dict())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_pbp("0022400001")
