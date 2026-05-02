"""
CourtAlpha Similarity Engine (v2.2)
Phase 2.4: Trajectory & Similarity Scores
-----------------------------------------
This module uses K-Nearest Neighbors (KNN) to find historically comparable 
player-seasons to a target prospect.

Methodology:
- Feature Engineering: Impact, xEFG%, and Trajectory are used as vectors.
- Normalization: Features are Z-scored to ensure equal weighting.
- Euclidean Distance: Used to calculate the 'Similarity Distance' between players.
"""

import duckdb
import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
import logging
from scripts.utils import setup_logging

# --- CONFIGURATION ---
DB_PATH = 'data/courtalpha.duckdb'
logger = setup_logging()

class SimilarityAnalyzer:
    """
    Finds the most historically similar players to a target prospect
    based on their 8-season development curves.
    """
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.con = duckdb.connect(self.db_path)
        
    def fetch_historical_curves(self):
        """
        Pulls comprehensive metrics for all players across all seasons.
        """
        logger.info("Extracting historical curve data for KNN fitting...")
        try:
            df = self.con.execute("""
                SELECT PLAYER_NAME, SHRUNK_IMPACT, X_EFG_PCT, POSSESSIONS, TRAJECTORY_SCORE
                FROM player_metrics
            """).df()
            return df
        except Exception as e:
            logger.error(f"Data extraction failed: {e}")
            return pd.DataFrame()

    def find_historical_comps(self, player_name, k=5):
        """
        Calculates similarity using Euclidean distance in a normalized feature space.
        """
        df = self.fetch_historical_curves()
        if len(df) < k + 1:
            logger.warning("Insufficient player pool for similarity analysis.")
            return pd.DataFrame()
            
        # 1. Feature Selection & Preprocessing
        features = ['SHRUNK_IMPACT', 'X_EFG_PCT', 'TRAJECTORY_SCORE']
        data = df[features].fillna(df[features].mean())
        
        # 2. Vector Normalization
        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(data)
        
        # 3. Target Vector Extraction
        try:
            target_idx = df[df['PLAYER_NAME'] == player_name].index[0]
            target_vector = scaled_data[target_idx].reshape(1, -1)
        except (IndexError, KeyError):
            logger.error(f"Player {player_name} not found in ML pool.")
            return pd.DataFrame()

        # 4. Nearest Neighbors Fitting
        knn = NearestNeighbors(n_neighbors=k+1, algorithm='auto', metric='euclidean')
        knn.fit(scaled_data)
        
        distances, indices = knn.kneighbors(target_vector)
        
        # 5. Result Formatting (Excluding target player)
        comp_indices = indices[0][1:]
        comps = df.iloc[comp_indices].copy()
        comps['SIMILARITY_DISTANCE'] = distances[0][1:]
        
        # Inversion of distance to create a 0-100% Score
        max_d = distances[0].max() if distances[0].max() > 0 else 1
        comps['SIMILARITY_SCORE'] = comps['SIMILARITY_DISTANCE'].apply(lambda x: max(0, int(100 * (1 - x/max_d))))
        
        return comps[['PLAYER_NAME', 'SHRUNK_IMPACT', 'SIMILARITY_SCORE']]

    def predict_all_star_leap(self, player_name):
        """
        Project future All-Star leaps based on growth trajectory.
        """
        comps = self.find_historical_comps(player_name)
        if comps.empty: return "Insufficient data."
        
        avg_comp_impact = comps['SHRUNK_IMPACT'].mean()
        if avg_comp_impact > 5.5:
            return "🟢 ELITE TRAJECTORY: Comparable players reached 1st Team All-NBA levels."
        elif avg_comp_impact > 2.5:
            return "🟡 CORE STARTER: Reliable trajectory toward top-tier efficiency."
        else:
            return "⚪ ROTATION PIECE: Projection suggests specialized role-player value."

    def generate_scouting_report_comps(self, player_name):
        """Generates a text-based summary for PDF reports."""
        comps = self.find_historical_comps(player_name)
        if comps.empty: return "No comparables identified."
        
        names = ", ".join(comps['PLAYER_NAME'].tolist())
        return f"Historical Comps: {names}. Career path: {self.predict_all_star_leap(player_name)}"

if __name__ == "__main__":
    analyzer = SimilarityAnalyzer()
    print(analyzer.find_historical_comps("Victor Wembanyama"))
