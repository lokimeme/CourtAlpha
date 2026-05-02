import pandas as pd
import numpy as np

class FrontOfficeSimulator:
    
    def __init__(self, initial_roster, initial_cap=155000000):
        self.roster = initial_roster
        self.current_cap = initial_cap
        self.seasons = ["2025-26", "2026-27", "2027-28", "2028-29", "2029-30"]

    def project_aging_curve(self, current_impact, age, years_out):
        
        new_age = age + years_out
        if new_age < 25:
            return current_impact * (1.10 ** years_out)
        elif new_age < 30:
            return current_impact * (1.02 ** years_out)
        else:
            return current_impact * (0.92 ** years_out)

    def simulate_season(self, year_index):
        
        results = []
        for _, player in self.roster.iterrows():
            age = 24 if "Wembanyama" in player['PLAYER_NAME'] else 28
            
            projected_impact = self.project_aging_curve(
                player['SHRUNK_IMPACT'], 
                age, 
                year_index
            )
            
            is_expired = np.random.random() < (0.2 * year_index)
            status = "Under Contract" if not is_expired else "Free Agent"
            
            results.append({
                "Player": player['PLAYER_NAME'],
                "Projected_Impact": projected_impact,
                "Status": status
            })
            
        return pd.DataFrame(results)

    def run_5_year_strategy(self):
        
        outlooks = []
        for i in range(5):
            season_df = self.simulate_season(i)
            avg_impact = season_df['Projected_Impact'].mean()
            active_count = len(season_df[season_df['Status'] == "Under Contract"])
            
            projected_wins = 41 + (avg_impact * 2)
            
            outlooks.append({
                "Season": self.seasons[i],
                "Projected_Wins": round(projected_wins),
                "Retained_Players": active_count,
                "Team_Trajectory": "Ascending" if avg_impact > 5 else "Contending"
            })
            
        return pd.DataFrame(outlooks)

    def generate_rebuild_advice(self):
        
        outlook = self.run_5_year_strategy()
        final_wins = outlook.iloc[-1]['Projected_Wins']
        
        if final_wins < 35:
            return "🚩 ALERT: Long-term projection shows significant decline. Recommend liquidating veterans for draft assets."
        elif final_wins > 55:
            return "🟢 CHAMPIONSHIP WINDOW: Roster impact is peaking. Recommend 'All-In' moves for rotation depth."
        else:
            return "🟡 TREADMILL RISK: Team is projected for mediocrity. Look for high-trajectory 'Hidden Gems' to break the ceiling."

if __name__ == "__main__":
    mock_r = pd.DataFrame([
        {'PLAYER_NAME': 'Star A', 'SHRUNK_IMPACT': 8.5},
        {'PLAYER_NAME': 'Gem B', 'SHRUNK_IMPACT': 4.2},
        {'PLAYER_NAME': 'Role C', 'SHRUNK_IMPACT': 1.1}
    ])
    sim = FrontOfficeSimulator(mock_r)
    print(sim.run_5_year_strategy())
    print(sim.generate_rebuild_advice())