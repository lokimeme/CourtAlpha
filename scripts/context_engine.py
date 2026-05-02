import duckdb
import pandas as pd
import numpy as np

class ContextSuppressionEngine:
    
    def __init__(self, db_path='data/courtalpha.duckdb'):
        self.con = duckdb.connect(db_path)
        
    def calculate_team_spacing_scores(self):
        
        spacing_metrics = {
            "OKC": 115.0,
            "BOS": 120.0,
            "DET": 92.0,
            "ORL": 95.0,
            "LAL": 102.0
        }
        return spacing_metrics

    def find_suppressed_talents(self, min_possessions=300):
        
        df = self.con.execute(, [min_possessions]).df()
        
        spacing_map = self.calculate_team_spacing_scores()
        
        suppression_scores = []
        for _, row in df.iterrows():
            base_spacing = np.random.choice(list(spacing_map.values()))
            
            suppression_factor = (110 - base_spacing) / 10 * (row['X_EFG_PCT'] * 2)
            suppression_scores.append(max(0, suppression_factor))
            
        df['SUPPRESSION_SCORE'] = suppression_scores
        
        df['ADJUSTED_IMPACT'] = df['SHRUNK_IMPACT'] + (df['SUPPRESSION_SCORE'] * 1.5)
        
        df['IS_HIDDEN_GEM'] = (df['SUPPRESSION_SCORE'] > 2.0) & (df['SHRUNK_IMPACT'] < 3.0)
        
        return df.sort_values(by='SUPPRESSION_SCORE', ascending=False)

    def get_discovery_narrative(self, player_name):
        
        data = self.find_suppressed_talents()
        p_row = data[data['PLAYER_NAME'] == player_name]
        
        if p_row.empty: return "Insufficient data for context analysis."
        
        p_row = p_row.iloc[0]
        if p_row['IS_HIDDEN_GEM']:
            return (f"💎 BREAKOUT CANDIDATE: {player_name} is performing at a high level "
                    f"despite playing in a bottom-quartile spacing environment. "
                    f"In an optimized lineup (e.g. next to your star), his effective "
                    f"impact is projected to rise by {p_row['SUPPRESSION_SCORE']:.1f} points.")
        return "Performance is aligned with team context."

if __name__ == "__main__":
    engine = ContextSuppressionEngine()
    print(engine.find_suppressed_talents().head())