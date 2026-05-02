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
        
        print("Running Archetype Clustering Engine...")
        
        df = self.con.execute().df()

        if len(df) < 10:
            print("Not enough players for clustering. Using fallback logic.")
            return

        features = df[['SHRUNK_IMPACT', 'X_EFG_PCT']]
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features)

        kmeans = KMeans(n_clusters=8, random_state=42, n_init=10)
        df['ARCHETYPE_ID'] = kmeans.fit_predict(scaled_features)
        df['ARCHETYPE_NAME'] = df['ARCHETYPE_ID'].map(self.archetypes)

        try:
            self.con.execute("ALTER TABLE player_metrics ADD COLUMN ARCHETYPE_NAME VARCHAR")
        except: pass

        for _, row in df.iterrows():
            self.con.execute(, (row['ARCHETYPE_NAME'], row['PLAYER_NAME']))
            
        print("Clustering complete.")

    def calculate_synergy(self, star_name, target_name):
        
        star_data = self.con.execute("SELECT ARCHETYPE_NAME FROM player_metrics WHERE PLAYER_NAME = ?", [star_name]).fetchone()
        target_data = self.con.execute("SELECT ARCHETYPE_NAME, X_EFG_PCT, SHRUNK_IMPACT FROM player_metrics WHERE PLAYER_NAME = ?", [target_name]).fetchone()

        if not star_data or not target_data:
            return 0.0

        star_arch = star_data[0]
        target_arch = target_data[0]

        synergy_map = {
            "High-Usage Slasher": ["3&D Wing", "Movement Shooter", "Elite Rim Protector"],
            "Floor General": ["3&D Wing", "Elite Rim Protector", "Versatile Forward"],
            "Elite Rim Protector": ["Floor General", "Point-of-Attack Defender"],
        }

        base_score = 50
        
        if star_arch in synergy_map and target_arch in synergy_map[star_arch]:
            base_score += 25
        
        if target_data[1] > 0.52:
            base_score += 15
            
        return min(100, base_score)

    def find_hidden_gems(self, star_name, top_n=5):
        
        star_data = self.con.execute("SELECT ARCHETYPE_NAME FROM player_metrics WHERE PLAYER_NAME = ?", [star_name]).fetchone()
        if not star_data: return pd.DataFrame()

        all_players = self.con.execute(, [star_name]).df()

        scores = []
        for _, row in all_players.iterrows():
            score = self.calculate_synergy(star_name, row['PLAYER_NAME'])
            scores.append(score)

        all_players['SYNERGY_SCORE'] = scores
        return all_players.sort_values(by='SYNERGY_SCORE', ascending=False).head(top_n)

if __name__ == "__main__":
    engine = SynergyEngine()
    engine.cluster_players()