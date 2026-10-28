"""Итоговая выгрузка настроек стратегии показа (уровень ГРУПП) в Excel.

Состав и ПОРЯДОК колонок заданы владельцем 28.10.2026:
    campaign_id, campaign_name, group_id, group_name, campaign_status, group_status,
    campaign_type, format, payment_model, price_kopeks, budget_kopeks,
    price_control, price_control_смысл

⚠ Колонки `price_kopeks` / `budget_kopeks` названы по полям API, но ЗНАЧЕНИЯ В НИХ —
РУБЛИ: копейки из API делятся на 100 и округляются до 2 знаков по правилам
математики (половина — вверх). Имя оставлено по просьбе владельца; делить второй
раз НЕ надо. Пометка повторена на листе «Расшифровка полей».

Источник: POST /ads/v1/account/{accountID}/groups  (x-cost 1/страница)
        + POST /ads/v1/account/{accountID}/campaigns (1/страница) — имя и статус кампании.

Три исхода:
  0 — файл записан, число групп совпало с `total` от API
  1 — записано, но число строк НЕ совпало с `total` (расхождение названо в выводе)
  2 — измерить не удалось (нет API-баллов / нет групп / пустой файл)

Запуск (из корня репозитория):
    python avito_performance/exports/export_group_strategy.py [каталог_вывода]
По умолчанию пишет в avito_performance/raw_data/.
"""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Путь выводится из расположения ЭТОГО файла: проект открывают разные учётки с
# разными путями (локальный у Oleg, UNC у 1C-ZUP-TEST) — хардкод одной среды
# сломал бы запуск у второй (правило средо-независимости в global CLAUDE.md).
PROJ = Path(__file__).resolve().parent.parent          # …/avito_performance
if not (PROJ / "avito_performance.py").is_file():
    print(f"ОТКАЗ: не нашёл avito_performance.py — ожидал в {PROJ}")
    sys.exit(2)
sys.path.insert(0, str(PROJ))
load_dotenv(PROJ / ".env")

# Колонки и их порядок — контракт с владельцем, менять только по его слову.
COLUMNS = [
    "campaign_id", "campaign_name", "group_id", "group_name",
    "campaign_status", "group_status", "campaign_type", "format",
    "payment_model", "price_kopeks", "budget_kopeks",
    "price_control", "price_control_смысл",
]

# Колонки с деньгами: показываем с двумя знаками (значение — рубли, см. докстроку).
MONEY_COLUMNS = ("price_kopeks", "budget_kopeks")

MEAN_PRICE_CONTROL = {
    "auto": "ставка автоматическая",
    "manual": "ставка вручную",
}


CENT = Decimal(100)
TWO_PLACES = Decimal("0.01")


def kopeks_to_rubles(value) -> Decimal | None:
    """Копейки → рубли: ÷100, два знака, половина ВВЕРХ (математическое округление).

    Встроенный `round()` здесь не годится: он округляет БАНКОВСКИ —
    `round(2.5 / 100, 2)` даёт `0.02`, а по правилам математики нужно `0.03`.
    Поэтому считаем в `Decimal` с `ROUND_HALF_UP` (от нуля и для отрицательных).
    Отсутствующее или нечисловое значение → `None`, а не `0.00`: «поля не было»
    и «расход нулевой» — разные факты, и подменять первое вторым нельзя.
    """
    if value is None or value == "":
        return None
    try:
        kopeks = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return (kopeks / CENT).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def build_rows(groups: list[dict], campaigns: list[dict]) -> pd.DataFrame:
    """Собирает итоговую таблицу: группы + имя/статус кампании джойном."""
    from avito_performance import _pick

    camp_name = {_pick(c, "id"): _pick(c, "name") for c in campaigns}
    camp_status = {_pick(c, "id"): c.get("status") for c in campaigns}

    rows = []
    for g in groups:
        cid = _pick(g, "campaignID")
        control = g.get("priceControl")
        rows.append({
            "campaign_id": cid,
            "campaign_name": camp_name.get(cid),
            "group_id": _pick(g, "id"),
            "group_name": _pick(g, "name"),
            "campaign_status": camp_status.get(cid),
            "group_status": g.get("status"),
            "campaign_type": g.get("campaignType"),
            "format": g.get("format"),
            "payment_model": g.get("paymentModel"),
            # имя колонки по API, значение — РУБЛИ (см. докстроку модуля)
            "price_kopeks": kopeks_to_rubles(g.get("priceKopeks")),
            "budget_kopeks": kopeks_to_rubles(g.get("budgetKopeks")),
            "price_control": control,
            "price_control_смысл": MEAN_PRICE_CONTROL.get(control, ""),
        })

    df = pd.DataFrame(rows)
    return df.reindex(columns=COLUMNS).sort_values(
        ["campaign_id", "group_id"]
    ).reset_index(drop=True)


def main(out_dir: Path) -> int:
    from avito_performance import BASE_URL, AvitoPerformanceClient

    client = AvitoPerformanceClient()

    # Отдельный дешёвый запрос: заявленный API `total` — независимая величина для
    # сверки полноты (postcondition), а не то же число, что мы сами насчитали.
    probe = client._session.post(
        f"{BASE_URL}{client._account_path('/groups')}",
        headers=client._headers() | {"Content-Type": "application/json"},
        json={"filter": {}, "limit": 1, "page": 1}, timeout=30,
    )
    if probe.status_code != 200:
        print(f"ИЗМЕРИТЬ НЕ УДАЛОСЬ: HTTP {probe.status_code} — {probe.text[:120]}")
        return 2
    total_declared = (probe.json() or {}).get("total")

    groups = client._fetch_all_pages("/groups", "groups", filter_body={})
    if not groups:
        print("ИЗМЕРИТЬ НЕ УДАЛОСЬ: у аккаунта нет групп")
        return 2
    campaigns = client._fetch_all_pages("/campaigns", "campaigns", filter_body={})
    print(f"групп: {len(groups)} (total от API: {total_declared}); кампаний: {len(campaigns)}")

    df = build_rows(groups, campaigns)

    legend = pd.DataFrame([
        ("campaign_id / campaign_name", "campaignID / name (справочник кампаний)", "Кампания, к которой относится группа"),
        ("group_id / group_name", "id / name", "Группа объявлений — именно на этом уровне задаётся стратегия"),
        ("campaign_status", "status (кампания)", "Статус кампании: draft / active / paused / finished / archived и др."),
        ("group_status", "status (группа)", "Статус группы, плюс will_launch_soon / will_stop_soon"),
        ("campaign_type", "campaignType", "textImage / HTML / video"),
        ("format", "format", "Формат размещения группы"),
        ("payment_model", "paymentModel", "CPM — оплата за показы, CPC — за клики. Задаёт смысл ставки"),
        ("price_kopeks", "priceKopeks ÷ 100", "⚠ ЗНАЧЕНИЕ В РУБЛЯХ. Ставка: при CPM это CPM, при CPC — цена клика. Делить второй раз не надо"),
        ("budget_kopeks", "budgetKopeks ÷ 100", "⚠ ЗНАЧЕНИЕ В РУБЛЯХ. Бюджет группы"),
        ("price_control", "priceControl", "auto — ставка автоматическая, manual — вручную"),
        ("price_control_смысл", "—", "Расшифровка price_control по-русски"),
    ], columns=["колонка выгрузки", "поле API", "что означает"])

    note = pd.DataFrame([
        ("источник", "POST /ads/v1/account/{accountID}/groups + /campaigns"),
        ("уровень стратегии", "ГРУППА объявлений; у кампании настроек показа нет (только paymentModel, budget, budgetFrequency)"),
        ("чего в API нет", "отдельного поля strategy / bidStrategy / optimization / goal / autobudget"),
        ("деньги", "взяты из копеечных полей, поделены на 100, округление половины ВВЕРХ (математическое, не банковское)"),
        ("единицы", "колонки price_kopeks и budget_kopeks содержат РУБЛИ, имя оставлено по полю API"),
        ("ставка при auto", "поле price заполнено и при автоматическом управлении ставкой; что именно оно ограничивает — в документации API не описано"),
        ("фактический CPM", "в этой выгрузке НЕТ — здесь только НАСТРОЙКИ. Фактический CPM лежит в статистике (поле cpm) и у нас не выгружается"),
        ("снято", datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M МСК")),
        ("аккаунт", f"ACCOUNT_ID {client.account_id}; групп {len(df)}, кампаний {len(campaigns)}"),
    ], columns=["пункт", "значение"])

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    xlsx = out_dir / f"get_group_strategy_{stamp}.xlsx"
    csv = out_dir / f"get_group_strategy_{stamp}.csv"

    with pd.ExcelWriter(xlsx, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="Стратегии групп", index=False)
        legend.to_excel(xl, sheet_name="Расшифровка полей", index=False)
        note.to_excel(xl, sheet_name="О выгрузке", index=False)
        for name, frame in (("Стратегии групп", df), ("Расшифровка полей", legend),
                            ("О выгрузке", note)):
            ws = xl.sheets[name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for i, col in enumerate(frame.columns, start=1):
                longest = max([len(str(col))] + [len(str(v)) for v in frame[col].head(200)])
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = \
                    min(max(longest + 2, 10), 60)
                # Денежные колонки: значение остаётся ЧИСЛОМ (чтобы считались суммы и
                # работала сортировка), но показывается с двумя знаками — иначе 215.00
                # отображается как «215», и требование «два знака» выполнено лишь на
                # словах. Формат ставится на ячейки данных, не на заголовок.
                if name == "Стратегии групп" and col in MONEY_COLUMNS:
                    for row in range(2, len(frame) + 2):
                        ws.cell(row=row, column=i).number_format = "0.00"
    df.to_csv(csv, index=False, encoding="cp1251", errors="replace")

    # ── постусловия: счётчик сделанного, а не слово «успешно» ────────────────
    size = xlsx.stat().st_size if xlsx.exists() else 0
    print(f"\nЗАПИСАНО: {xlsx}  ({size} байт)")
    print(f"ЗАПИСАНО: {csv}  ({csv.stat().st_size} байт)")
    print(f"строк: {len(df)}, колонок: {len(df.columns)}")
    if size == 0:
        print("ОТКАЗ: файл нулевого размера")
        return 2
    if list(df.columns) != COLUMNS:
        print(f"ОТКАЗ: порядок колонок разошёлся с контрактом: {list(df.columns)}")
        return 2

    empty_price = int(df["price_kopeks"].isna().sum())
    empty_budget = int(df["budget_kopeks"].isna().sum())
    print(f"пустых price: {empty_price}, пустых budget: {empty_budget} (из {len(df)})")

    if isinstance(total_declared, int) and total_declared != len(df):
        print(f"РАСХОЖДЕНИЕ: API заявил total={total_declared}, выгружено {len(df)}")
        return 1
    print(f"число строк совпало с total от API ({total_declared}) — выгрузка полная")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJ / "raw_data"
    sys.exit(main(target))
