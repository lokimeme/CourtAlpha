import duckdb
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import os

DB_PATH = 'data/courtalpha.duckdb'

class SynergyEngine:
    def __init__(self):
        self.con = duckdb.connect(DB_PATH)
        self.archetypes = {
            0: "Elite Rim Protector",
            1: "3&D Wing",
            2: "Movement Shooter",
            3: "High-Usage Slasher",
            4: "Connector / High-IQ Big",
            5: "Point-of-Attack Defender",
            6: "Floor General",
            7: "Versatile Forward"
        }

    def cluster_players(self):
        """
        Phase 2.4: Archetype Clustering
        Uses K-Means to group players based on their micro-actions and style of play.
        """
        print("Running Archetype Clustering Engine...")
        
        # Pulling metrics for clustering
        # In a full version, we'd use X_EFG_PCT, usage, blocks, steals, etc.
        df = self.con.execute("""
            SELECT PLAYER_NAME, SHRUNK_IMPACT, X_EFG_PCT, POSSESSIONS 
            FROM player_metrics
        """).df()

        if len(df) < 10:
            print("Not enough players for clustering. Using fallback logic.")
            return

        # Feature engineering for archetypes (Simulated)
        features = df[['SHRUNK_IMPACT', 'X_EFG_PCT']]
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features)

        # K-Means Clustering
        kmeans = KMeans(n_clusters=8, random_state=42, n_init=10)
        df['ARCHETYPE_ID'] = kmeans.fit_predict(scaled_features)
        df['ARCHETYPE_NAME'] = df['ARCHETYPE_ID'].map(self.archetypes)

        # Update the database
        try:
            self.con.execute("ALTER TABLE player_metrics ADD COLUMN ARCHETYPE_NAME VARCHAR")
        except: pass

        for _, row in df.iterrows():
            self.con.execute("""
                UPDATE player_metrics 
                SET ARCHETYPE_NAME = ? 
                WHERE PLAYER_NAME = ?
            """, (row['ARCHETYPE_NAME'], row['PLAYER_NAME']))
            
        print("Clustering complete.")

    def calculate_synergy(self, star_name, target_name):
        """
        Phase 2.3: Synergy Predictor
        Calculates a 'Fit Score' based on how well the target's archetype 
        complements the star's archetype.
        """
        star_data = self.con.execute("SELECT ARCHETYPE_NAME FROM player_metrics WHERE PLAYER_NAME = ?", [star_name]).fetchone()
        target_data = self.con.execute("SELECT ARCHETYPE_NAME, X_EFG_PCT, SHRUNK_IMPACT FROM player_metrics WHERE PLAYER_NAME = ?", [target_name]).fetchone()

        if not star_data or not target_data:
            return 0.0

        star_arch = star_data[0]
        target_arch = target_data[0]

        # Define Synergy Matrix (Heuristic-based)
        # High score = Good fit
        synergy_map = {
            "High-Usage Slasher": ["3&D Wing", "Movement Shooter", "Elite Rim Protector"],
            "Floor General": ["3&D Wing", "Elite Rim Protector", "Versatile Forward"],
            "Elite Rim Protector": ["Floor General", "Point-of-Attack Defender"],
        }

        base_score = 50
        
        # Archetype Compatibility
        if star_arch in synergy_map and target_arch in synergy_map[star_arch]:
            base_score += 25
        
        # Context-Suppression Logic: Target's impact vs their cost/sample
        if target_data[1] > 0.52: # High shot quality
            base_score += 15
            
        return min(100, base_score)

    def find_hidden_gems(self, star_name, top_n=5):
        """
        The 'Front Office' Query: Find players with high synergy and low contract cost.
        """
        star_data = self.con.execute("SELECT ARCHETYPE_NAME FROM player_metrics WHERE PLAYER_NAME = ?", [star_name]).fetchone()
        if not star_data: return pd.DataFrame()

        all_players = self.con.execute("""
            SELECT PLAYER_NAME, ARCHETYPE_NAME, SURPLUS_VALUE, SHRUNK_IMPACT 
            FROM player_metrics 
            WHERE PLAYER_NAME != ?
        """, [star_name]).df()

        scores = []
        for _, row in all_players.iterrows():
            score = self.calculate_synergy(star_name, row['PLAYER_NAME'])
            scores.append(score)

        all_players['SYNERGY_SCORE'] = scores
        # A 'Hidden Gem' has high synergy but might have lower Shrunk Impact (undervalued)
        return all_players.sort_values(by='SYNERGY_SCORE', ascending=False).head(top_n)

if __name__ == "__main__":
    engine = SynergyEngine()
    engine.cluster_players()
