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
        Phase 2.4: Advanced Archetype Clustering
        Uses the 12 granular micro-actions to group players by their tactical DNA.
        """
        print("Running Skill-Based Archetype Clustering Engine...")
        
        skill_df = self.con.execute("""
            SELECT 
                PLAYER_NAME,
                COUNT(*) FILTER (WHERE MICRO_ACTION = 'Logo Range')::FLOAT / COUNT(*) as LOGO_FREQ,
                COUNT(*) FILTER (WHERE MICRO_ACTION = 'Floater / Touch')::FLOAT / COUNT(*) as FLOATER_FREQ,
                COUNT(*) FILTER (WHERE MICRO_ACTION = 'Lob Finish')::FLOAT / COUNT(*) as LOB_FREQ,
                COUNT(*) FILTER (WHERE MICRO_ACTION = 'Off-Ball Cut')::FLOAT / COUNT(*) as CUT_FREQ,
                COUNT(*) FILTER (WHERE MICRO_ACTION = 'Post-Up / Hook')::FLOAT / COUNT(*) as POST_FREQ,
                COUNT(*) FILTER (WHERE MICRO_ACTION = 'Assisted 3PT')::FLOAT / COUNT(*) as SPOTUP_FREQ,
                COUNT(*) FILTER (WHERE MICRO_ACTION = 'Self-Created (Space)')::FLOAT / COUNT(*) as ISOLATION_FREQ,
                COUNT(*) FILTER (WHERE MICRO_ACTION = 'Interior Wall (Contest)')::FLOAT / COUNT(*) as RIM_PROT_FREQ
            FROM play_by_play
            WHERE PLAYER_NAME IS NOT NULL
              AND ACTION_TYPE IN ('Made Shot', 'Missed Shot')
            GROUP BY PLAYER_NAME
            HAVING COUNT(*) > 50
        """).df()

        if len(skill_df) < 10:
            print("Not enough skill data for clustering.")
            return

        metrics = self.con.execute("""
            SELECT PLAYER_NAME, SHRUNK_IMPACT, X_EFG_PCT 
            FROM player_metrics
        """).df()
        
        df = skill_df.merge(metrics, on='PLAYER_NAME', how='inner')

        feature_cols = [c for c in df.columns if 'FREQ' in c] + ['SHRUNK_IMPACT', 'X_EFG_PCT']
        features = df[feature_cols].fillna(0)
        
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features)

        kmeans = KMeans(n_clusters=8, random_state=42, n_init=10)
        df['ARCHETYPE_ID'] = kmeans.fit_predict(scaled_features)
        df['ARCHETYPE_NAME'] = df['ARCHETYPE_ID'].map(self.archetypes)

        try:
            self.con.execute("ALTER TABLE player_metrics ADD COLUMN ARCHETYPE_NAME VARCHAR")
        except: pass

        print(f"Updating {len(df)} players with DNA-based archetypes...")
        for _, row in df.iterrows():
            self.con.execute("""
                UPDATE player_metrics 
                SET ARCHETYPE_NAME = ? 
                WHERE PLAYER_NAME = ?
            """, (row['ARCHETYPE_NAME'], row['PLAYER_NAME']))
            
        print("Skill-based clustering complete.")

    def calculate_synergy(self, star_name, target_name):
        """
        Phase 2.3: Advanced Synergy Predictor (v2.0)
        Calculates compatibility based on Stat-to-Stat interactions.
        """
        query = """
            SELECT 
                PLAYER_NAME, ARCHETYPE_NAME, SHRUNK_IMPACT, X_EFG_PCT,
                POSSESSIONS, COALESCE(ADJUSTED_IMPACT, 0) as RAPM
            FROM player_metrics 
            WHERE PLAYER_NAME IN (?, ?)
        """
        results = self.con.execute(query, [star_name, target_name]).df()
        
        if len(results) < 2:
            return 0.0

        p1 = results[results['PLAYER_NAME'] == star_name].iloc[0]
        p2 = results[results['PLAYER_NAME'] == target_name].iloc[0]

        synergy_score = 50.0

        p1_low_spacing = p1['ARCHETYPE_NAME'] in ["Elite Rim Protector", "High-Usage Slasher"]
        p2_high_spacing = p2['ARCHETYPE_NAME'] in ["3&D Wing", "Movement Shooter"]
        
        if p1_low_spacing and p2_high_spacing:
            synergy_score += 20.0
        elif p1_low_spacing and p2['ARCHETYPE_NAME'] == "Elite Rim Protector":
            synergy_score -= 15.0

        if p1['ARCHETYPE_NAME'] == "High-Usage Slasher" and p2['ARCHETYPE_NAME'] == "High-Usage Slasher":
            synergy_score -= 10.0
        
        if p1['ARCHETYPE_NAME'] == "High-Usage Slasher" and p2['ARCHETYPE_NAME'] in ["Floor General", "Connector / High-IQ Big"]:
            synergy_score += 15.0

        def_pair = {p1['ARCHETYPE_NAME'], p2['ARCHETYPE_NAME']}
        if "Elite Rim Protector" in def_pair and "Point-of-Attack Defender" in def_pair:
            synergy_score += 25.0

        if p2['RAPM'] > 1.5 and p2['SHRUNK_IMPACT'] < 1.0:
            synergy_score += 10.0

        return max(0, min(100, synergy_score))

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
        return all_players.sort_values(by='SYNERGY_SCORE', ascending=False).head(top_n)

if __name__ == "__main__":
    engine = SynergyEngine()
    engine.cluster_players()
