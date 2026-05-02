from nba_api.stats.endpoints import boxscoretraditionalv3
import pandas as pd
import time

def test_boxscore(game_id):
    try:
        box = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        data = box.get_dict()
        print("Keys in BoxScoreTraditionalV3 dict:", data.keys())
        if 'boxScoreTraditional' in data:
            box_data = data['boxScoreTraditional']
            home_team = box_data['homeTeam']
            away_team = box_data['awayTeam']
            
            print(f"Home Team: {home_team['teamName']} ({home_team['teamId']})")
            print(f"Away Team: {away_team['teamName']} ({away_team['teamId']})")
            
            home_players = pd.DataFrame(home_players_data := home_team['players'])
            away_players = pd.DataFrame(away_players_data := away_team['players'])
            
            print("\nHome Starters:")
            home_starters = home_players[home_players['position'] != ""]
            print(home_starters[['firstName', 'familyName', 'position', 'personId']])
            
            print("\nAway Starters:")
            away_starters = away_players[away_players['position'] != ""]
            print(away_starters[['firstName', 'familyName', 'position', 'personId']])
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_boxscore("0022400001")