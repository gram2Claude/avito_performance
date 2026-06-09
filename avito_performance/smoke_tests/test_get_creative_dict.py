"""Smoke-test: get_creative_dict на реальном API.

Запуск из корня репо:
    python avito_performance/smoke_tests/test_get_creative_dict.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from avito_performance import get_creative_dict  # noqa: E402

df = get_creative_dict()

out_dir = PROJECT_ROOT / "raw_data"
out_dir.mkdir(exist_ok=True)
out_path = out_dir / "get_creative_dict.csv"
df.to_csv(out_path, index=False, encoding="cp1251", errors="replace")

print("shape:", df.shape)
print("columns:", list(df.columns))
print("saved:", out_path)
print("\nhead(5):")
print(df.head(5).to_string())
