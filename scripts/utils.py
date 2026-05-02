import os
import logging
import duckdb
from datetime import datetime

def setup_logging():
    
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"courtalpha_{timestamp}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("CourtAlpha")

class DBManager:
    
    def __init__(self, db_path='data/courtalpha.duckdb'):
        self.db_path = db_path
        
    def get_connection(self):
        
        try:
            return duckdb.connect(self.db_path)
        except Exception as e:
            logging.error(f"Database Connection Failed: {e}")
            return None

def format_currency(value):
    
    if value >= 1000000:
        return f"${value/1000000:.1f}M"
    elif value >= 1000:
        return f"${value/1000:.1f}K"
    else:
        return f"${value:.2f}"

def calculate_percentile(value, distribution):
    
    if not distribution:
        return 0
    less_than = len([x for x in distribution if x < value])
    return (less_than / len(distribution)) * 100

def shrink_value(raw_val, sample_size, prior=0, lmbda=300):
    
    return (raw_val * sample_size + prior * lmbda) / (sample_size + lmbda)

def normalize_stat(val, mean, std):
    
    if std == 0: return 0
    return (val - mean) / std

if __name__ == "__main__":
    logger = setup_logging()
    logger.info("Utility Module Initialized.")
    print(format_currency(35859941))
    print(f"Shrunk Impact (Low Sample): {shrink_value(10.0, 50):.2f}")