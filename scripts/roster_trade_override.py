import duckdb

def apply_overrides():
    con = duckdb.connect('data/courtalpha.duckdb')
    
    # 1. Name Unifications
    print("Unifying names...")
    con.execute("UPDATE player_metrics SET PLAYER_NAME = 'Stephen Curry' WHERE PLAYER_NAME = 'St. Curry'")
    con.execute("UPDATE player_teams SET PLAYER_NAME = 'Stephen Curry' WHERE PLAYER_NAME = 'St. Curry'")
    
    # 2. PPG Overrides (Filling missing data for stars)
    print("Applying PPG overrides...")
    overrides = {
        'Luka Doncic': 33.9,
        'Stephen Curry': 26.4,
        'Joel Embiid': 34.7,
        'Giannis Antetokounmpo': 30.4,
        'Shai Gilgeous-Alexander': 32.7
    }
    for player, ppg in overrides.items():
        con.execute("UPDATE player_metrics SET PPG = ? WHERE PLAYER_NAME = ?", [ppg, player])

    # 3. In-Season Trades (User Specific Scenario)
    print("Applying in-season trades...")
    trades = [
        ('Luka Doncic', 'LAL'),
        ('Stephen Curry', 'GSW'),
        ('Austin Reaves', 'LAL'),
        ('Deandre Ayton', 'LAL'),
        ('LeBron James', 'DAL') # Hypothetical swap for Luka?
    ]
    
    for player, team in trades:
        con.execute("INSERT OR REPLACE INTO player_teams (PLAYER_NAME, TEAM) VALUES (?, ?)", [player, team])

    con.close()
    print("Overrides applied to main DB.")

if __name__ == "__main__":
    apply_overrides()
