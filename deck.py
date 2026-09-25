"""Load the automa deck for the app (self-contained, no project imports).

The data files in app/data/ are copies of the project's config.json,
specs/cards.csv and output/test_stats.json - refresh them with
`python sync_app.py` in the project folder.
"""

import csv
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def load_config():
    return json.loads((DATA_DIR / "config.json").read_text())


def load_deck(cfg):
    """One dict per card from data/cards.csv (same format as specs/cards.csv)."""
    rounds = range(1, cfg["rounds"] + 1)
    deck = []
    with (DATA_DIR / "cards.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            deck.append({
                "number": int(row["number"]), "id": row["id"],
                "action": int(row["action"]), "name": row["name"],
                "quadrant": row["quadrant"], "spaces": int(row["spaces"]),
                "worker": row["worker_cube"] == "yes",
                "first_player": row["card_action"] == "yes",
                "areas": [int(row[f"r{r}_max_cost"]) if row[f"r{r}_max_cost"] else None
                          for r in rounds],
                "sheep": [int(row[f"r{r}_sheep"] or 0) for r in rounds],
                "tools": [row[f"r{r}_tools"] == "yes" for r in rounds],
            })
    return deck
