"""Тестовая выгрузка СТРАТЕГИЙ показа (настройки групп объявлений) в Excel.

Источник: POST /ads/v1/account/{accountID}/groups (x-cost 1/страница)
        + POST .../campaigns (1/страница) — для названия кампании.

Три исхода:
  0 — файл записан, число строк совпало с total от API
  1 — записано, но число строк НЕ совпало с total (расхождение названо)
  2 — измерить не удалось (нет баллов / нет групп / ошибка записи)

Запуск: python export_group_strategy.py [каталог_вывода]
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Путь выводится из расположения ЭТОГО файла: проект открывают разные учётки
# с разными путями (локальный у Oleg, UNC у 1C-ZUP-TEST) — хардкод одной среды
# сломал бы скрипт у второй (правило средо-независимости в global CLAUDE.md).
PROJ = Path(__file__).resolve().parent.parent          # …/avito_performance
if not (PROJ / "avito_performance.py").is_file():
    print(f"ОТКАЗ: не нашёл avito_performance.py рядом — ожидал в {PROJ}")
    sys.exit(2)
sys.path.insert(0, str(PROJ))
load_dotenv(PROJ / ".env")

from avito_performance import BASE_URL, AvitoPerformanceClient, _pick  # noqa: E402

OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJ / "raw_data"
WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEK_RU = {"monday": "пн", "tuesday": "вт", "wednesday": "ср", "thursday": "чт",
           "friday": "пт", "saturday": "сб", "sunday": "вс"}

# Расшифровки — только то, что подтверждено сводкой API и живым замером.
MEAN_PRICE_CONTROL = {"auto": "ставка автоматическая", "manual": "ставка вручную"}
MEAN_PACE = {"even": "равномерно весь период", "asap": "как можно быстрее"}
MEAN_AUDIENCE = {"basic": "базовая (свои настройки)", "ready": "готовый сегмент",
                 "autotargeting": "автотаргетинг"}
MEAN_BUDGET_FREQ = {"entirePeriod": "бюджет на весь период", "weekly": "бюджет в неделю"}
MEAN_SCHEDULE = {"always": "круглосуточно", "weekdays9To20": "будни 9-20", "custom": "своё расписание"}


def _hours_compact(hours: list | None) -> str:
    """[9,10,11,13] -> '9-11,13'. Пусто -> ''."""
    if not hours:
        return ""
    hs = sorted(int(h) for h in hours)
    spans, start, prev = [], hs[0], hs[0]
    for h in hs[1:]:
        if h == prev + 1:
            prev = h
            continue
        spans.append((start, prev))
        start = prev = h
    spans.append((start, prev))
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in spans)


def schedule_text(sched: dict | None) -> str:
    """activitySchedule -> читаемая строка; 'круглосуточно все дни' при полном покрытии."""
    if not sched:
        return ""
    per_day = {d: _hours_compact(sched.get(d)) for d in WEEK}
    if all(v == "0-23" for v in per_day.values()):
        return "круглосуточно все дни"
    parts = [f"{WEEK_RU[d]} {v}" for d, v in per_day.items() if v]
    return "; ".join(parts) if parts else "нет активных часов"


def freq_text(group: dict) -> str:
    rules = group.get("frequencyRules") or []
    if rules:
        return "; ".join(f"{r.get('count')}/{r.get('period')}" for r in rules)
    cnt, per = group.get("frequencyCount"), group.get("frequencyPeriod")
    if per == "no_limit" or not cnt:
        return "без ограничения"
    return f"{cnt}/{per}"


def ids_text(group: dict, key: str) -> str:
    v = group.get(key) or []
    return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)


def money(rub, kop):
    """Рубли для чтения; копеечное поле как контроль (×100)."""
    if rub is None and kop is None:
        return None, None, ""
    note = ""
    if rub is not None and kop is not None:
        note = "совпадает" if round(float(kop)) == round(float(rub) * 100) else "РАСХОЖДЕНИЕ"
    return rub, kop, note


client = AvitoPerformanceClient()

# ── забор данных ──────────────────────────────────────────────────────────────
r = client._session.post(
    f"{BASE_URL}{client._account_path('/groups')}",
    headers=client._headers() | {"Content-Type": "application/json"},
    json={"filter": {}, "limit": 1, "page": 1}, timeout=30,
)
if r.status_code != 200:
    print(f"ИЗМЕРИТЬ НЕ УДАЛОСЬ: HTTP {r.status_code} — {r.text[:120]}")
    sys.exit(2)
total_declared = (r.json() or {}).get("total")

groups = client._fetch_all_pages("/groups", "groups", filter_body={})
if not groups:
    print("ИЗМЕРИТЬ НЕ УДАЛОСЬ: групп нет")
    sys.exit(2)
print(f"групп получено: {len(groups)} (total от API: {total_declared})")

campaigns = client._fetch_all_pages("/campaigns", "campaigns", filter_body={})
camp_name = {_pick(c, "id"): _pick(c, "name") for c in campaigns}
camp_status = {_pick(c, "id"): _pick(c, "status") for c in campaigns}
print(f"кампаний получено: {len(campaigns)}")

# ── сборка таблицы ────────────────────────────────────────────────────────────
rows = []
for g in groups:
    price_r, price_k, price_note = money(g.get("price"), g.get("priceKopeks"))
    budg_r, budg_k, budg_note = money(g.get("budget"), g.get("budgetKopeks"))
    cid = _pick(g, "campaignID")
    rows.append({
        "group_id": _pick(g, "id"),
        "group_name": _pick(g, "name"),
        "campaign_id": cid,
        "campaign_name": camp_name.get(cid),
        "campaign_status": camp_status.get(cid),
        "group_status": g.get("status"),
        "campaign_type": g.get("campaignType"),
        "format": g.get("format"),
        # ——— собственно стратегия ———
        "payment_model": g.get("paymentModel"),
        "price_control": g.get("priceControl"),
        "price_control_смысл": MEAN_PRICE_CONTROL.get(g.get("priceControl"), ""),
        "pace": g.get("pace"),
        "pace_смысл": MEAN_PACE.get(g.get("pace"), ""),
        "price_руб": price_r,
        "price_kopeks": price_k,
        "price_сверка": price_note,
        "budget_руб": budg_r,
        "budget_kopeks": budg_k,
        "budget_сверка": budg_note,
        "budget_frequency": g.get("budgetFrequency"),
        "budget_frequency_смысл": MEAN_BUDGET_FREQ.get(g.get("budgetFrequency"), ""),
        "частота_показов": freq_text(g),
        "frequency_count": g.get("frequencyCount"),
        "frequency_period": g.get("frequencyPeriod"),
        "schedule_type": g.get("scheduleType"),
        "schedule_type_смысл": MEAN_SCHEDULE.get(g.get("scheduleType"), ""),
        "расписание_часы": schedule_text(g.get("activitySchedule")),
        "start_asap": g.get("startASAP"),
        "audience_type": g.get("audienceType"),
        "audience_type_смысл": MEAN_AUDIENCE.get(g.get("audienceType"), ""),
        "targeting_age_ids": ids_text(g, "targetingAgeIDs"),
        "targeting_income_ids": ids_text(g, "targetingIncomeIDs"),
        "targeting_interest_ids": ids_text(g, "targetingInterestIDs"),
        "targeting_location_ids": ids_text(g, "targetingLocationIDs"),
        # ——— период и служебное ———
        "period_start_at": g.get("periodStartAt"),
        "period_end_at": g.get("periodEndAt"),
        "period_timezone": g.get("periodTimezone"),
        "top_status_reason": g.get("topStatusReason"),
        "status_reasons": ", ".join(str(x) for x in (g.get("statusReasons") or [])),
        "advertiser_id": _pick(g, "advertiserID"),
        "manager_id": _pick(g, "managerID"),
        "created_at": g.get("createdAt"),
        "updated_at": g.get("updatedAt"),
    })

df = pd.DataFrame(rows).sort_values(["campaign_id", "group_id"]).reset_index(drop=True)

# ── сводка по комбинациям стратегий ───────────────────────────────────────────
summary = (
    df.groupby(["payment_model", "price_control", "pace", "budget_frequency",
                "audience_type", "schedule_type", "частота_показов"], dropna=False)
      .size().reset_index(name="групп")
      .sort_values("групп", ascending=False).reset_index(drop=True)
)

# ── лист с расшифровкой полей ─────────────────────────────────────────────────
legend = pd.DataFrame([
    ("payment_model", "paymentModel", "Модель оплаты: CPM (за показы) / CPC (за клики)"),
    ("price_control", "priceControl", "Управление ставкой: auto — автоматическое, manual — вручную"),
    ("pace", "pace", "Темп расхода бюджета: even — равномерно, asap — как можно быстрее"),
    ("price_руб / price_kopeks", "price / priceKopeks", "Ставка. Рублёвое и копеечное поля приходят ОБА; колонка price_сверка проверяет kopeks = руб×100"),
    ("budget_руб / budget_kopeks", "budget / budgetKopeks", "Бюджет. Так же оба формата + сверка"),
    ("budget_frequency", "budgetFrequency", "Период бюджета: entirePeriod — на весь период, weekly — недельный"),
    ("частота_показов", "frequencyRules / frequencyCount+frequencyPeriod", "Ограничение частоты показов на пользователя; 'без ограничения' = no_limit"),
    ("schedule_type + расписание_часы", "scheduleType + activitySchedule", "Расписание показов: always / weekdays9To20 / custom + фактические часы по дням"),
    ("start_asap", "startASAP", "Запускать сразу, не дожидаясь даты старта"),
    ("audience_type", "audienceType", "Подбор аудитории: basic — свои настройки, ready — готовый сегмент, autotargeting — автотаргетинг"),
    ("targeting_*_ids", "targetingAgeIDs / targetingIncomeIDs / targetingInterestIDs / targetingLocationIDs", "Идентификаторы таргетингов; пусто = ограничение не задано"),
    ("top_status_reason / status_reasons", "topStatusReason / statusReasons", "Причины текущего статуса группы"),
], columns=["колонка выгрузки", "поле API", "что означает"])

note = pd.DataFrame([
    ("источник", "POST /ads/v1/account/{accountID}/groups — стратегия задаётся на уровне ГРУППЫ"),
    ("чего в API нет", "отдельного поля strategy / bidStrategy / optimization / goal / autobudget — стратегия это НАБОР полей выше"),
    ("уровень кампании", "у кампании настроек показа нет: только paymentModel, budget/budgetKopeks, budgetFrequency"),
    ("деньги", "в справочниках рублёвые и копеечные поля приходят ОБА (аддитивно); в СТАТИСТИКЕ рублёвый spend исчез, остался spendKopecs"),
    ("выгрузка снята", datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M МСК")),
    ("аккаунт", f"ACCOUNT_ID {client.account_id}; групп {len(df)}, кампаний {len(campaigns)}"),
], columns=["пункт", "значение"])

# ── запись ────────────────────────────────────────────────────────────────────
OUT_DIR.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().strftime("%Y-%m-%d")
xlsx = OUT_DIR / f"get_group_strategy_{stamp}.xlsx"
csv = OUT_DIR / f"get_group_strategy_{stamp}.csv"

with pd.ExcelWriter(xlsx, engine="openpyxl") as xl:
    df.to_excel(xl, sheet_name="Стратегии групп", index=False)
    summary.to_excel(xl, sheet_name="Сводка комбинаций", index=False)
    legend.to_excel(xl, sheet_name="Расшифровка полей", index=False)
    note.to_excel(xl, sheet_name="О выгрузке", index=False)

    for name, frame in (("Стратегии групп", df), ("Сводка комбинаций", summary),
                        ("Расшифровка полей", legend), ("О выгрузке", note)):
        ws = xl.sheets[name]
        ws.freeze_panes = "A2"
        for i, col in enumerate(frame.columns, start=1):
            longest = max([len(str(col))] + [len(str(v)) for v in frame[col].head(200)])
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(max(longest + 2, 10), 60)
        ws.auto_filter.ref = ws.dimensions

df.to_csv(csv, index=False, encoding="cp1251", errors="replace")

# ── постусловия (счётчик сделанного, а не «успешно») ─────────────────────────
size = xlsx.stat().st_size if xlsx.exists() else 0
print(f"\nЗАПИСАНО: {xlsx}  ({size} байт)")
print(f"ЗАПИСАНО: {csv}  ({csv.stat().st_size} байт)")
print(f"строк: {len(df)}, колонок: {len(df.columns)}; комбинаций стратегий: {len(summary)}")
if size == 0:
    print("ОТКАЗ: файл нулевого размера")
    sys.exit(2)

bad = df[df["price_сверка"].eq("РАСХОЖДЕНИЕ") | df["budget_сверка"].eq("РАСХОЖДЕНИЕ")]
print(f"сверка рубли↔копейки: расхождений {len(bad)} из {len(df)}")

if isinstance(total_declared, int) and total_declared != len(df):
    print(f"РАСХОЖДЕНИЕ: API заявил total={total_declared}, выгружено {len(df)}")
    sys.exit(1)
print(f"число строк совпало с total от API ({total_declared}) — выгрузка полная")
sys.exit(0)
