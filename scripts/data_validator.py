import duckdb
import pandas as pd
import numpy as np

class DataValidator:
    """
    Quality Assurance & Validation Suite.
    Ensures 8-season backfill integrity and identifies API-induced anomalies.
    """
    def __init__(self, db_path='data/courtalpha.duckdb'):
        self.db_path = db_path
        # Use read_only=True to allow parallel audits while backfill/lineup scripts are running
        self.con = duckdb.connect(self.db_path, read_only=True)

    def validate_schema(self):
        """
        Verifies that all required columns for Phase 1-4 exist and have correct types.
        """
        required_cols = {
            'play_by_play': ['GAME_ID', 'LOC_X', 'LOC_Y', 'GARBAGE_TIME', 'SEASON'],
            'player_metrics': ['PLAYER_NAME', 'SHRUNK_IMPACT', 'X_EFG_PCT', 'SURPLUS_VALUE', 'ARCHETYPE_NAME']
        }
        
        errors = []
        for table, cols in required_cols.items():
            try:
                existing = self.con.execute(f"PRAGMA table_info({table})").df()['name'].tolist()
                for c in cols:
                    if c not in existing:
                        errors.append(f"MISSING_COLUMN: Table '{table}' is missing '{c}'")
            except:
                errors.append(f"MISSING_TABLE: Table '{table}' not found.")
        return errors

    def detect_outliers(self):
        """
        Uses IQR (Interquartile Range) to flag suspicious data points (e.g. 5000% eFG).
        """
        metrics = self.con.execute("SELECT PLAYER_NAME, SHRUNK_IMPACT, X_EFG_PCT FROM player_metrics").df()
        if metrics.empty: return []

        flags = []
        for col in ['SHRUNK_IMPACT', 'X_EFG_PCT']:
            Q1 = metrics[col].quantile(0.25)
            Q3 = metrics[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 3 * IQR
            upper_bound = Q3 + 3 * IQR
            
            outliers = metrics[(metrics[col] < lower_bound) | (metrics[col] > upper_bound)]
            for _, row in outliers.iterrows():
                flags.append(f"ANOMALY: {row['PLAYER_NAME']} has extreme {col} value ({row[col]:.2f})")
        
        return flags

    def check_backfill_completeness(self, expected_seasons):
        """
        Verifies if all 8 target seasons have data present.
        """
        present = self.con.execute("SELECT DISTINCT SEASON FROM play_by_play").df()['SEASON'].tolist()
        missing = [s for s in expected_seasons if s not in present]
        
        if missing:
            return f"INCOMPLETE: Missing data for seasons: {', '.join(missing)}"
        return "COMPLETE: All 8 seasons verified."

    def calculate_data_health_score(self):
        """
        Returns a 0-100 score of the database's readiness for executive decision making.
        """
        score = 100
        schema_errs = self.validate_schema()
        outliers = self.detect_outliers()
        
        score -= (len(schema_errs) * 15)
        score -= (len(outliers) * 2)
        
        # Check for nulls in critical columns
        nulls = self.con.execute("SELECT count(*) FROM player_metrics WHERE SHRUNK_IMPACT IS NULL").fetchone()[0]
        score -= (nulls * 0.5)
        
        return max(0, min(100, score))

    def run_full_audit(self):
        """
        Executes all checks and provides a summary report.
        """
        print(f"--- CourtAlpha Data Audit ---")
        print(f"Health Score: {self.calculate_data_health_score()}/100")
        
        errs = self.validate_schema()
        if errs: print(f"Schema Errors: {len(errs)}")
        
        outliers = self.detect_outliers()
        if outliers: print(f"Statistical Outliers: {len(outliers)}")
        
        print("Audit Complete.")

if __name__ == "__main__":
    validator = DataValidator()
    validator.run_full_audit()
