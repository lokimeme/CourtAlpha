import duckdb
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

class BreakoutEngine:
    """
    Predictive Analytics for Player Development.
    Identifies 'Breakout' candidates by comparing trajectories to physical peers.
    """
    def __init__(self, db_path='data/courtalpha.duckdb'):
        self.db_path = db_path

    def calculate_age(self, birthdate_str):
        if not birthdate_str: return 26
        try:
            birth_year = int(birthdate_str.split('-')[0])
            return 2026 - birth_year
        except: return 26

    def get_breakout_candidates(self):
        con = duckdb.connect(self.db_path, read_only=True)
        
        query = """
        SELECT 
            m.PLAYER_NAME, 
            m.SHRUNK_IMPACT, 
            m.X_EFG_PCT, 
            m.POSSESSIONS,
            t.BIRTHDATE,
            t.HEIGHT,
            t.WEIGHT,
            m.ARCHETYPE_NAME
        FROM player_metrics m
        JOIN player_metadata t ON m.PLAYER_NAME = t.PLAYER_NAME
        """
        df = con.execute(query).df()
        con.close()

        if df.empty: return "No data available."

        df['AGE'] = df['BIRTHDATE'].apply(self.calculate_age)
        
        def height_to_inches(h):
            try:
                f, i = map(int, h.split('-'))
                return f * 12 + i
            except: return 78
            
        df['HEIGHT_IN'] = df['HEIGHT'].apply(height_to_inches)

        candidates = df[df['AGE'] <= 24].copy()
        
        candidates['BREAKOUT_SCORE'] = (
            (candidates['SHRUNK_IMPACT'] * 0.4) + 
            ((25 - candidates['AGE']) * 2.0) + 
            (candidates['X_EFG_PCT'] * 20.0)
        )

        return candidates.sort_values(by='BREAKOUT_SCORE', ascending=False)

    def find_peer_trajectory(self, player_name):
        """
        Finds the 5 most similar historical physical peers to project future growth.
        """
        pass

if __name__ == "__main__":
    engine = BreakoutEngine()
    print("Engine Initialized. Waiting for DB unlock to run predictions.")
