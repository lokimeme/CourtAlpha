import duckdb
import pandas as pd
import numpy as np
import logging
import os

DB_PATH = 'data/courtalpha.duckdb'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MetricIngest")

def ingest_metrics(csv_path=None):
    # NOTE: The random benchmark fallback below is a legacy development scaffold.
    # The production app uses only the proprietary RAPM-Lite Meta-Impact score.
    # This file is retained for future integration with real external CSV sources.
    """
    Final Phase: Internal Meta-Impact Consolidation.
    Focuses 100% on the proprietary RAPM model, removing reliance on external
    simulated benchmarks to ensure 100% data integrity.
    """
    con = duckdb.connect(DB_PATH)
    
    logger.info("Calculating Meta-Impact Score based on proprietary RAPM...")
    try:
        con.execute("ALTER TABLE player_metrics ADD COLUMN META_IMPACT FLOAT")
    except: pass

    # Meta-Impact is now 100% based on our internal shrunk impact (Pts/100 scale)
    con.execute("""
        UPDATE player_metrics
        SET META_IMPACT = (SHRUNK_IMPACT * 100)
    """)
    
    con.close()
    logger.info("Meta-Impact calculation complete.")

if __name__ == "__main__":
    ingest_metrics()
