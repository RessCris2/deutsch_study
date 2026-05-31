"""Batch-import all JSON files from data/json_output/ into the SQLite database."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db import Base, engine, get_session
from backend.app.main import json_word_to_payload, upsert_entries
from backend.app.models import VocabularyEntry

Base.metadata.create_all(bind=engine)

JSON_DIR = ROOT / "data" / "json_output"

files = sorted(JSON_DIR.rglob("*.json"))
total_imported = 0
total_errors = 0

for path in files:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[SKIP] {path.relative_to(ROOT)}: {exc}")
        continue

    if not isinstance(data, list):
        print(f"[SKIP] {path.relative_to(ROOT)}: not an array")
        continue

    payloads = []
    for i, item in enumerate(data):
        try:
            payloads.append(json_word_to_payload(item))
        except Exception as exc:
            print(f"  [ERR] {path.name} item {i}: {exc}")
            total_errors += 1

    with next(get_session()) as session:
        count = upsert_entries(session, payloads)
        total_imported += count
        print(f"[OK]  {path.relative_to(ROOT)}  → {count} 条")

print(f"\n完成：共导入 {total_imported} 条，{total_errors} 条错误")
