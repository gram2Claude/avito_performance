# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -r avito_performance/requirements.txt
pip install -r avito_performance/requirements-dev.txt   # pytest (для unit-тестов)
```

Credentials go in `avito_performance/.env` (copy from `avito_performance/.env.example`):

```
CLIENT_ID=...
CLIENT_SECRET=...
ACCOUNT_ID=...        # ID рекламного аккаунта из кабинета Авито Реклама
TEST_START_DATE=...   # YYYY-MM-DD — период для smoke-тестов статистики
TEST_END_DATE=...     # (≤ 100 дней между ними)
```

`AvitoPerformanceClient` reads credentials from env vars `CLIENT_ID` / `CLIENT_SECRET`
and the account id from `ACCOUNT_ID`, or they can be passed explicitly to the constructor.

## Account model (зафиксировано)

**Один аккаунт = отдельная тройка `CLIENT_ID` / `CLIENT_SECRET` / `ACCOUNT_ID`.**
Токен `client_credentials` в API Авито Реклама привязан к одному рекламному аккаунту
(запрос к чужому `accountID` → 403). Единого «агентского» токена на несколько кабинетов нет;
метода «список всех кабинетов» тоже нет. Поэтому каждый кабинет обслуживается своей тройкой
кредитов в `.env`, и клиент инстанцируется под конкретный `ACCOUNT_ID`.

Текущий проект работает с **одним** кабинетом: `ACCOUNT_ID=383819919` (shortName «5KA-AI-IGC»),
дочерних аккаунтов нет (`children-with-balances` → `[]`, проверено 2026-06-09). Если в будущем
появятся другие кабинеты — добавляется отдельная тройка кредитов и клиент создаётся per-account
(токен-рефреш остаётся автоматическим). См. `info/00_api_methods.md` → раздел про привязку токена.

## Running

Unit-тесты (pytest, моки — без сети и `.env`):
```bash
python -m pytest avito_performance/tests -q
# один тест:
python -m pytest avito_performance/tests/test_avito_performance.py::test_get_admin_audit -q
```

Smoke-тесты (живой API, нужен `.env`; запуск из корня репо, по одному файлу на функцию):
```bash
python avito_performance/smoke_tests/test_<имя_функции>.py   # напр. test_get_admin_audit.py
```
Даты статистики берутся из `.env` (`TEST_START_DATE`/`TEST_END_DATE`). Результат сохраняется в
`avito_performance/raw_data/<имя_функции>[_{from}_{to}].csv` (cp1251, gitignored); перед записью
тест удаляет старые выгрузки этой же функции — в `raw_data/` лежит только последняя.
После прогона показать первые 5 строк **из сохранённого CSV** (не из памяти) — см. `test/00_README.md`.

Выгрузка настроек стратегии показа в Excel (уровень групп, 13 колонок — состав и порядок
заданы владельцем 2026-10-28):
```bash
python avito_performance/exports/export_group_strategy.py            # в raw_data/
python avito_performance/exports/export_group_strategy.py <каталог>  # в указанный каталог
```
Стоимость — 2 балла (списки групп и кампаний). Исходы: `0` — выгружено и число строк совпало
с `total` от API, `1` — записано с расхождением, `2` — измерить не удалось (нет баллов/групп).
⚠ Колонки `price_kopeks`/`budget_kopeks` названы по полям API, но **содержат рубли**
(÷100, два знака, округление половины вверх — `kopeks_to_rubles`, тесты в
`tests/test_export_group_strategy.py`). Стратегия задаётся на уровне **группы**; отдельного
поля `strategy` в API нет — см. `info/00_api_methods.md`.

Demo notebook:
```bash
jupyter notebook avito_performance/avito_performance_demo.ipynb
```

Quick smoke-test from Python REPL (requires real credentials):
```python
import sys; sys.path.insert(0, "avito_performance")
from avito_performance import get_campaign_dict
df = get_campaign_dict()
print(df.shape)
```

## Architecture

Single-file library: `avito_performance/avito_performance.py`.

**`AvitoPerformanceClient`** — internal HTTP client:
- OAuth 2.0 `client_credentials` auth; token auto-refreshed 60 s before expiry (TTL 24 h).
  Token endpoint `POST https://api.avito.ru/token` uses **`application/x-www-form-urlencoded`** (`data=`, not `json=`).
- Every request to `/ads/*` carries `Authorization: Bearer <token>`.
- `_get()` / `_post()` → JSON; `_request()` handles 429 with exponential backoff (max 5 retries, starts at 1 s).
- `_fetch_all_pages(suffix, entity_key, filter_body)` → paginated list helper for справочники
  (body `{filter, limit, page}`, walks pages until empty / `page*limit >= total`).
- `_campaign_stats()` / `_groups_stats()` / `_creatives_stats()` → обёртки stats-эндпоинтов
  (для групп/креативов — с массивом `groupIDs`/`creativeIDs`).
- `_account_path(suffix)` → builds `/ads/v1/account/{ACCOUNT_ID}{suffix}`.

Synchronous JSON API — no async submit/poll/download, no CSV/ZIP.

**Public functions** (all return `pd.DataFrame`):

| Function | Granularity | API endpoint |
|----------|-------------|--------------|
| `get_campaign_dict()` | справочник (кампании) | `POST /ads/v1/account/{accountID}/campaigns` |
| `get_group_dict()` | справочник (группы) | `POST /ads/v1/account/{accountID}/groups` |
| `get_creative_dict()` | справочник (креативы) | `POST /ads/v1/account/{accountID}/creatives` |
| `get_campaigns_daily_stat(date_from, date_to)` | статистика по дням (кампании) | `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/stats` |
| `get_groups_daily_stat(date_from, date_to)` | статистика по дням (группы) | `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/groups/stats` |
| `get_creatives_daily_stat(date_from, date_to)` | статистика по дням (креативы) | `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/creatives/stats` |
| `get_admin_audit(date_from, date_to)` | сводный аудит по дням (admin_audit) | собственного эндпоинта нет — агрегат поверх campaigns stats |

> Статус: все 7 функций реализованы и проверены на живом API (Шаг 4 завершён; реестр — `info/01_functions_implemented.md`).

**`get_admin_audit` (таблица admin_audit):** суммы `impressions`/`clicks`/`costs_nds`/`costs_without_nds`
по `date × account_id × source_type_id × owner_id` (owner_id — join из справочника кампаний) + `chef_flag = 1`.

**Правила запроса данных:**
- **Справочники:** постраничный POST (`filter`/`limit`/`page`), сбор всех страниц в один DataFrame.
- **Статистика:** Avito отдаёт `data[]` сразу за весь период (≤100 дней) одним запросом на сущность —
  разворачиваем по дням локально (не делаем запрос на каждый день). Для групп/креативов нужны ID
  из соответствующего справочника, сгруппированные по `campaign_id`.
- **Охвата (reach) в API нет.** В выходных DataFrame оставлены: показы (`impressions` ← API `views`),
  клики (`clicks`), расход (`costs_nds`/`spend_bonus`) и видео-метрики (`video_views_25/50/75/100`).
- **Полей названий в статистике нет** (`campaign_name`/`group_name`/`creative_name` удалены по
  требованию проекта) — имена джойнить из справочников по `campaign_id`/`group_id`/`creative_id`.
  Метрики `ctr`, `cpm`, `cpc`, `q25`, `q50`, `q75`, `vtr` из API **не выгружаются** (исключены по требованию проекта).
  Охватных функций нет.

**Цепочка вызовов справочников (join-поля):** `get_creative_dict` → вызывает `get_group_dict`
(берёт `id_key_group`/`owner_id`) → тот вызывает `get_campaign_dict` (берёт
`camp_type`/`camp_category`/`owner_id`). `get_admin_audit` вызывает `get_campaigns_daily_stat`
+ `get_campaign_dict`. Каждый уровень добавляет постраничную выгрузку вышестоящего справочника.

**Helper functions** (private, module-level):
- `_pick()` — первый существующий ключ из dict — обязателен из-за неоднородного регистра
  ключей API (`managerID`/`advertiserId`; `groupID` в списке vs `groupId` в creatives/stats)
- `_metric_cols()` / `_STAT_METRIC_KEYS` — маппинг метрик StatsData → колонки
  (`impressions←views`, `costs_nds←spendKopecs`, `spend_bonus←spendBonusKopecs`);
  общий для всех трёх stat-функций. Денежные колонки (`_KOPECS_COLUMNS`) конвертируются
  здесь же, поэтому возвращённые значения = то, что попадёт в DataFrame
- `_kopecs_to_rubles()` — копейки → рубли (÷100, round 2); `None` при отсутствующем/нечисловом
  значении, чтобы «поля не было» не превращалось в «расход ноль»
- `_apply_stat_enrichment()` — общее обогащение статистики (costs_nds → float.round(2),
  НДС, ak, константы, `id_key_camp`)
- `_vat_divisor()` — делитель НДС по году даты строки (2026+ → 1.22, ранее → 1.20)
- `_day_from_timestamp()` — `YYYY-MM-DD` из ISO-таймстампа статистики (приходит с `+03:00`)
- `_normalize_iso_dt()` — нормализация дат ISO-Z (без сдвига таймзоны!) и Go-time;
  сейчас полей дат в выгрузках нет, хелпер сохранён с unit-тестами
- `_parse_num()` — число → float; `_date_range()` / `_chunks()` — даты и батчи (зарезервированы)

## API Constraints

From `info/00_api_methods.md`:
- Rate limit **500 запросов/минуту** на аккаунт; при 429 — экспоненциальный backoff.
- API-баллы: у каждого метода своя стоимость `x-cost` (campaign stats = 10), остаток в заголовке `Api-Point-Balance`.
- Статистика: период **≤ 100 дней** между `dateFrom` и `dateTo`.
- Пагинация: `limit` 1–100 (дефолт 20), `page` ≥ 1.
- Токен привязан к одному `accountID`; для дочерних аккаунтов — отдельные ключи.

## Обогащение DataFrame (соглашение проекта)

Каждая публичная функция обогащает результат фиксированным набором константных
и вычисляемых полей **перед** `df.reindex(columns=...)`:

**Константы (для всех функций):**
- `account_id = 1`, `source_type_id = 9` — примеры, заменяемые при интеграции

**Для справочников:** дополнительно (для campaign-уровня) `product_id = 1`, `product_name = "prod_test"`,
`camp_type = "camp_test"`, `camp_category = "cat_test"`, `owner_id = 1`

**Для справочника групп** (group-уровень): `camp_type`, `camp_category`, `owner_id` — **join из
справочника кампаний** по `campaign_id` (не константы); `group_type = "other"`,
`group_category = "other"` — дефолт

**Для справочника креативов** (ad-уровень): `id_key_group`, `owner_id` — **join из справочника
групп** по `group_id`

**Для функций с расходами** (агентская комиссия `ak = 0.5`):
- `costs_nds` — **десятичный тип (float), округление до 2 знаков** сразу после чтения из API,
  до вычисления производных (в admin_audit — повторное округление после суммирования)
- `costs_without_nds = costs_nds / (1 + ставка_НДС)` — **ставка зависит от года даты строки:
  год ≥ 2026 → 22% (делитель 1.22), раньше → 20% (делитель 1.20)**. Считается per-row по `date`
  (в одном отчёте могут быть дни разных лет). Реализация — `_vat_divisor()` в `avito_performance.py`.
- `costs_nds_ak = costs_nds * 1.5`
- `costs_without_nds_ak = costs_without_nds * 1.5`

**Составные ключи:**
- `id_key_camp = "1_" + campaign_id` — для всех функций
- `id_key_group = id_key_camp + "_" + group_id` — для справочников групп и креативов
  (у креативов — join из справочника групп по `group_id`)
- `id_key_ad = id_key_group + "_" + creative_id` — **только для ad-level** функций (креативы = объявления);
  в статистике `id_key_group` вычисляется как `id_key_camp + "_" + group_id`

> **Важно про `costs_nds`:** денежные метрики статистики приходят **в копейках** —
> `spendKopecs` / `spendBonusKopecs`, суммы **с НДС**. Клиент делит их на 100 и округляет
> до 2 знаков (`_kopecs_to_rubles`), поэтому `costs_nds ← spendKopecs / 100` — настоящие
> рубли с копейками. Ставка НДС для `costs_without_nds` — **по году даты строки: 2026+ → 22%,
> ранее → 20%** (см. `_vat_divisor`).
>
> ⚠️ **Изменение источника (2026-09-22):** прежние рублёвые поля `spend` / `spendBonus` из ответа
> **исчезли**. Клиент их намеренно **не читает даже как fallback**: рубли, принятые за копейки,
> занизили бы расход в 100 раз молча — пустая колонка заметна, тихо неверная нет. Отсутствующее
> поле даёт `None`, а не `0.0`.
> **Отсюда снято прежнее предупреждение** «целочисленный вход → расхождения с ЛК Авито»: копейки
> теперь приходят из API, и этой причины расхождений больше не существует.
> **Статус проверки:** состав ключей задан владельцем; **живой пробой не подтверждён** — на
> 2026-09-22 у аккаунта исчерпан недельный пул API-баллов (любой метод → `429` «не достаточно
> API балов», при целом частотном лимите `x-ratelimit-remaining: 500`). Пул сбрасывается
> в понедельник 00:00 UTC; проверить smoke-тестом после сброса.

Значения констант — заменяемые при реальной интеграции (вписываются клиентом).

## Windows Encoding

`avito_performance.py` reconfigures `sys.stdout/stderr` to UTF-8 on import — required on Windows
where the default console encoding may be cp1251. CSV пишется/читается в `cp1251` с `errors="replace"`.

## Spec Reference

`info/00_api_methods.md` — полная сводка методов Avito Performance API (auth + статистика + справочники),
единая точка правды по API. `info/01_functions_implemented.md` — реестр реализованных функций (Шаг 4).
Процесс разработки описан в `test/00_README.md`.

ТЗ для внешнего разработчика (Шаг 5, сгенерировано 2026-06-10): `specs/TZ_avito_performance.md`
(источник) → `TZ_avito_performance.pdf` (корень репо); генератор — `specs/generate_tz_pdf.py`
(требует `fpdf2`). При изменении контрактов функций обновлять ТЗ и перегенерировать PDF.
