"""Bootstrap smoke-test: проверка кредов и обнаружение доступных кабинетов.

Запуск из корня репо:
    python avito_performance/smoke_tests/test_auth_and_accounts.py

Шаги:
  1. Выпуск access-токена по client_credentials (валидация CLIENT_ID/CLIENT_SECRET).
  2. Попытка определить accountID (через классический /core/v1/accounts/self).
  3. Запрос рекламного аккаунта и его дочерних кабинетов.

Секреты не печатаются (токен маскируется).
"""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

BASE = "https://api.avito.ru"

CLIENT_ID = os.environ.get("CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "").strip()
ACCOUNT_ID = os.environ.get("ACCOUNT_ID", "").strip()

assert CLIENT_ID, "CLIENT_ID не заполнен в avito_performance/.env"
assert CLIENT_SECRET, "CLIENT_SECRET не заполнен в avito_performance/.env"


def _mask(s: str) -> str:
    return f"{s[:4]}…{s[-2:]}" if s and len(s) > 6 else "***"


def _show(label: str, resp: requests.Response) -> None:
    print(f"\n{label} → HTTP {resp.status_code}")
    try:
        print("  " + json.dumps(resp.json(), ensure_ascii=False)[:800])
    except Exception:
        print("  " + resp.text[:400])


# ── 1. Токен ──────────────────────────────────────────────────────────────────
print("=" * 70)
print("1) Выпуск токена (client_credentials)")
r = requests.post(
    f"{BASE}/token",
    data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    },
    timeout=30,
)
print(f"   POST /token → HTTP {r.status_code}")
r.raise_for_status()
tok = r.json()
print(f"   token_type={tok.get('token_type')} expires_in={tok.get('expires_in')} "
      f"access_token={_mask(tok.get('access_token', ''))}")
print("   ✅ Креды валидны, токен получен.")

headers = {"Authorization": f"Bearer {tok['access_token']}", "Accept": "application/json"}

# ── 2. Определение accountID ──────────────────────────────────────────────────
print("\n" + "=" * 70)
print("2) Определение accountID")
self_id = None
try:
    r2 = requests.get(f"{BASE}/core/v1/accounts/self", headers=headers, timeout=30)
    _show("GET /core/v1/accounts/self", r2)
    if r2.ok:
        self_id = r2.json().get("id")
except requests.RequestException as exc:
    print("   /core/v1/accounts/self недоступен:", exc)

candidate = ACCOUNT_ID or (str(self_id) if self_id else "")
print(f"\n   Кандидат accountID: {candidate or '— не определён —'}")

# ── 3. Рекламный аккаунт и дочерние кабинеты ─────────────────────────────────
print("\n" + "=" * 70)
print("3) Рекламный аккаунт и дочерние кабинеты")
if not candidate:
    print("   ⚠️ accountID не определён. Впиши ACCOUNT_ID в .env (из URL кабинета "
          "Авито Реклама) и перезапусти — это позволит проверить доступ и дочерние кабинеты.")
else:
    _show(f"GET /ads/v1/account/{candidate}", requests.get(
        f"{BASE}/ads/v1/account/{candidate}", headers=headers, timeout=30))
    _show(f"GET /ads/v1/account/{candidate}/children-with-balances", requests.get(
        f"{BASE}/ads/v1/account/{candidate}/children-with-balances", headers=headers, timeout=30))

print("\n" + "=" * 70)
print("Готово.")
