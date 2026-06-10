"""Smoke-test: get_campaigns_daily_stat на реальном API.

Запуск из корня репо:
    python avito_performance/smoke_tests/test_get_campaigns_daily_stat.py

Даты берутся из .env (TEST_START_DATE / TEST_END_DATE).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from avito_performance import get_campaigns_daily_stat  # noqa: E402

DATE_FROM = os.environ.get("TEST_START_DATE", "").strip().strip("'\"")
DATE_TO = os.environ.get("TEST_END_DATE", "").strip().strip("'\"")
assert DATE_FROM and DATE_TO, "TEST_START_DATE / TEST_END_DATE не заданы в .env"
print(f"Период: {DATE_FROM} → {DATE_TO}")

df = get_campaigns_daily_stat(DATE_FROM, DATE_TO)

out_dir = PROJECT_ROOT / "raw_data"
out_dir.mkdir(exist_ok=True)
# в raw_data/ держим только последнюю выгрузку: имя содержит период,
# поэтому файлы за прежние даты сами не перезаписываются — удаляем
for old in out_dir.glob("get_campaigns_daily_stat_*.csv"):
    old.unlink()
out_path = out_dir / f"get_campaigns_daily_stat_{DATE_FROM}_{DATE_TO}.csv"
df.to_csv(out_path, index=False, encoding="cp1251", errors="replace")

print("shape:", df.shape)
print("columns:", list(df.columns))
print("saved:", out_path)
print("\nhead(5):")
print(df.head(5).to_string())
