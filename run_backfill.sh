#!/bin/bash
cd /home/lohith/CourtAlpha
source venv/bin/activate
python scripts/backfill.py >> backfill_output.log 2>&1
