from pathlib import Path
import csv

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "generated"

def read_csv(name: str):
    path = DATA_DIR / name
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
