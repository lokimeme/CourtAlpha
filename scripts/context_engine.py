import duckdb
import pandas as pd
import numpy as np

class ContextSuppressionEngine:
    """
    The 'Hidden Gem' Discovery Core.
    Analyzes players whose statistical output is 'suppressed' by poor teammate spacing.
    """
    def __init__(self, db_path='data/courtalpha.duckdb'):
        self.con = duckdb.connect(db_path)
        
    def calculate_team_spacing_scores(self):
        """
        Calculates a 'Spacing Rating' for every team based on the real spatial 
        gravity of its players (3PT frequency and location).
        """
        # Calculate real spacing rating from play-by-play data
        query = """
            WITH player_spacing AS (
                SELECT 
                    PLAYER_NAME,
                    CAST(SUM(CASE WHEN (ABS(LOC_X) >= 220 AND LOC_Y <= 92) OR (SQRT(LOC_X*LOC_X + LOC_Y*LOC_Y) > 235 AND LOC_Y > 92) THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as spacing_val
                FROM play_by_play
                WHERE ACTION_TYPE IN ('Made Shot', 'Missed Shot')
                GROUP BY 1
            )
            SELECT t.TEAM, AVG(s.spacing_val) as avg_spacing
            FROM player_spacing s
            JOIN player_teams t ON s.PLAYER_NAME = t.PLAYER_NAME
            GROUP BY 1
        """
        spacing_df = self.con.execute(query).df()
        if spacing_df.empty: return {}
        
        # Normalize to a 0-100 scale where 100 is league average
        mean_spacing = spacing_df['avg_spacing'].mean()
        spacing_df['norm_spacing'] = (spacing_df['avg_spacing'] / (mean_spacing if mean_spacing > 0 else 1)) * 100
        
        return dict(zip(spacing_df['TEAM'], spacing_df['norm_spacing']))

    def find_suppressed_talents(self, min_fga=100):
        """
        Flags players who have high expected eFG% (shot quality) 
        despite playing in low-spacing environments.
        """
        df = self.con.execute("""
            SELECT m.PLAYER_NAME, m.SHRUNK_IMPACT, m.X_EFG_PCT, m.FGA, t.TEAM
            FROM player_metrics m
            JOIN player_teams t ON m.PLAYER_NAME = t.PLAYER_NAME
            WHERE m.FGA >= ?
        """, [min_fga]).df()
        
        spacing_map = self.calculate_team_spacing_scores()
        
        def calc_suppression(row):
            team_spacing = spacing_map.get(row['TEAM'], 100.0)
            # Higher suppression when team spacing is below 100
            suppression_factor = (100.0 - team_spacing) / 10.0
            return max(0, suppression_factor * row['X_EFG_PCT'])
            
        df['SUPPRESSION_SCORE'] = df.apply(calc_suppression, axis=1)
        
        # Adjusted impact considering environment suppression
        df['ADJUSTED_IMPACT'] = df['SHRUNK_IMPACT'] + (df['SUPPRESSION_SCORE'] * 0.1)
        
        # Hidden Gem: High suppression score but low current impact
        df['IS_HIDDEN_GEM'] = (df['SUPPRESSION_SCORE'] > 0.5) & (df['SHRUNK_IMPACT'] < 0.005)
        
        return df.sort_values(by='SUPPRESSION_SCORE', ascending=False)

    def get_discovery_narrative(self, player_name):
        """
        Provides a front-office narrative for why this player is a hidden gem.
        """
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
