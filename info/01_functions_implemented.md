# Реестр реализованных функций — Avito Performance

Что уже умеет клиент `avito_performance.py`: какой API-метод использует каждая
публичная функция, какие поля возвращает, что важно помнить при сопровождении.

---

## Функция: `get_campaign_dict`

- **Статус:** реализована
- **Дата реализации:** 2026-06-09
- **Тип:** справочник
- **Файл:** `avito_performance.py` → `get_campaign_dict()` (использует `AvitoPerformanceClient._fetch_all_pages`)
- **Spec:** `specs/01_spec_get_campaign_dict.md`
- **Plan:** отдельно не составлялся — реализовано после live-probe эндпоинта по утверждённому направлению
- **Smoke-test:** `smoke_tests/test_get_campaign_dict.py` (+ `smoke_tests/test_auth_and_accounts.py` — bootstrap)

### API-метод

- **Endpoint:** `POST /ads/v1/account/{accountID}/campaigns`
- **Тип:** sync, постраничный (`{"filter":{}, "limit":100, "page":N}`)
- **Формат ответа:** `application/json` — `{"campaigns": [...], "total": int}`
- **x-cost:** 1 балл/страница
- **Ссылка на сводку:** см. `info/00_api_methods.md` → раздел «Список кампаний»

### Параметры функции (Python-сигнатура)

```python
def get_campaign_dict() -> pd.DataFrame:
    # Параметров нет. CLIENT_ID/CLIENT_SECRET/ACCOUNT_ID — из окружения (.env).
```

### Поля выходного DataFrame (21 колонка)

| Колонка | Тип | Источник (поле API) | Описание |
|---------|-----|---------------------|----------|
| `campaign_id` | int64 | `id` | ID кампании |
| `campaign_name` | string | `name` | Название |
| `status` | string | `status` | Статус (`draft`/`active`/`finished`/…) |
| `budget` | int64 | `budget` | Бюджет, ₽ с НДС |
| `payment_model` | string | `paymentModel` | `CPM`/`CPC` |
| `campaign_type` | string | `campaignType` | `textImage`/`HTML`/`video` |
| `start_date` | string | `startDate` → `_day_from_timestamp` | Начало размещения, `YYYY-MM-DD` |
| `end_date` | string | `endDate` → `_day_from_timestamp` | Конец размещения, `YYYY-MM-DD` |
| `advertiser_id` | int64 | `advertiserId` | ID рекламодателя |
| `contract_id` | int64 | `contractId` | ID договора |
| `manager_id` | int64 | `managerID` | ID менеджера (в API — заглавные `ID`) |
| `created_at` | string | `createdAt` → `_normalize_iso_dt` | Создание, ISO 8601 UTC |
| `updated_at` | string | `updatedAt` → `_normalize_iso_dt` | Обновление, ISO 8601 UTC |
| `account_id` | int64 | константа `1` | пример, заменить при интеграции |
| `source_type_id` | int64 | константа `9` | пример |
| `product_id` | int64 | константа `1` | пример |
| `product_name` | string | константа `"prod_test"` | пример |
| `camp_type` | string | константа `"camp_test"` | пример |
| `camp_category` | string | константа `"cat_test"` | пример |
| `id_key_camp` | string | вычисляется: `"1_" + campaign_id` | составной ключ |
| `owner_id` | int64 | константа `1` | пример |

Расходов в справочнике нет → блок `costs_*`/`ak` не применяется.

### Специфика / сложности реализации

- **Пагинация:** через `_fetch_all_pages("/campaigns", "campaigns", {})`; завершение по пустому
  массиву или `page*100 >= total`. На тестовом аккаунте `total=16` (1 страница).
- **`filter:{}` возвращает кампании ВСЕХ статусов** (проверено: `finished:9, active:6, draft:1`).
  Если потребуется только активные — добавить `{"statuses":["active"]}` в `filter_body`.
- **Неоднородный регистр ключей API:** `advertiserId`, `contractId`, `accountId`, `userId`
  (строчные `d`/`Id`), но `managerID` (заглавные `ID`). Маппинг использует точные имена.
- **Два формата дат в одном ответе** (важно!):
  - `createdAt` — чистый ISO 8601 (`2026-06-05T15:54:49Z`);
  - `startDate`/`endDate`/`updatedAt` — Go-time `time.String()` (`2026-06-19 20:00:00 +0000 UTC`,
    иногда с миллисекундами). Всегда `+0000` (UTC).
  - `start_date`/`end_date` нормализуются к дате (первые 10 символов работают для обоих форматов),
    `created_at`/`updated_at` — к ISO 8601 UTC через `_normalize_iso_dt`.
  - ⚠️ **Баг и фикс:** для ISO-строки с `Z` нельзя применять `.astimezone(utc)` к naive-datetime —
    Python трактует naive как локальное время и сдвигает на offset машины (на UTC+3 `15:54Z`
    превращался в `12:54Z`). Исправлено: `Z`-формат форматируется без сдвига.
- **Токен:** `/token` принимает `application/x-www-form-urlencoded` (`data=`, не `json=`).
- **Поля, не вынесенные в DataFrame:** `accountId`, `userId`, `additionalAgreementID`,
  `performanceAdditionalAgreementID` (последних двух в реальном ответе нет — опциональны).
- **CSV:** сохранение/чтение в `cp1251` с `errors="replace"`.

### История изменений

| Дата | Изменение | Причина |
|------|-----------|---------|
| 2026-06-09 | Первичная реализация | — |

---

## Функция: `get_group_dict`

- **Статус:** реализована · **Дата:** 2026-06-09 · **Тип:** справочник
- **Файл:** `avito_performance.py` → `get_group_dict()` (использует `_fetch_all_pages`)
- **Spec/Plan:** отдельно не составлялись (реализовано по `03_ENTITY_FUNCTIONS.md` + live-probe)
- **Smoke-test:** `smoke_tests/test_get_group_dict.py` · **CSV:** `raw_data/get_group_dict.csv`

### API-метод
- **Endpoint:** `POST /ads/v1/account/{accountID}/groups` (sync, постраничный, x-cost 1)
- **Формат:** JSON `{"groups": [...], "total": int}`

### Поля выходного DataFrame (24 колонки)
API: `group_id←id, group_name←name, campaign_id←campaignID, status, payment_model←paymentModel,
budget, price, price_control←priceControl, pace, audience_type←audienceType, format,
frequency_count←frequencyCount, frequency_period←frequencyPeriod, schedule_type←scheduleType,
period_start_at←periodStartAt, period_end_at←periodEndAt, have_creative←haveCreative,
advertiser_id←advertiserID, manager_id←managerID, created_at←createdAt, updated_at←updatedAt`.
Обогащение (справочник без product_*): `account_id=1, source_type_id=9, id_key_camp="1_"+campaign_id`.

### Специфика
- Регистр ключей: у групп почти все с заглавными `ID` (`campaignID`, `advertiserID`, `managerID`, `userID`).
- Даты (`periodStartAt/EndAt`, `createdAt`, `updatedAt`) — **ISO 8601 с `Z`** (в отличие от кампаний, где
  `startDate/endDate` в Go-формате); `_normalize_iso_dt` покрывает оба → ISO 8601 UTC.
- `haveCreative` в реальном ответе **отсутствует** → колонка `have_creative = None`.
- Массивы таргетинга (`targeting*IDs`), `activitySchedule`, `actions`, `budgetFrequency`, `startASAP`,
  `periodTimezone` намеренно не вынесены (вне согласованного набора Fn5).
- На тестовом аккаунте: 16 групп (по одной на кампанию), 1 страница.

### История изменений
| Дата | Изменение | Причина |
|------|-----------|---------|
| 2026-06-09 | Первичная реализация | — |

---

## Функция: `get_creative_dict`

- **Статус:** реализована · **Дата:** 2026-06-09 · **Тип:** справочник
- **Файл:** `avito_performance.py` → `get_creative_dict()` (использует `_fetch_all_pages`)
- **Spec/Plan:** отдельно не составлялись (реализовано по `03_ENTITY_FUNCTIONS.md` + live-probe)
- **Smoke-test:** `smoke_tests/test_get_creative_dict.py` · **CSV:** `raw_data/get_creative_dict.csv`

### API-метод
- **Endpoint:** `POST /ads/v1/account/{accountID}/creatives` (sync, постраничный, x-cost 1)
- **Формат:** JSON `{"creatives": [...], "total": int}`

### Поля выходного DataFrame (20 колонок)
API: `creative_id←id, creative_name←name, group_id←groupID, campaign_id←campaignID, status,
payment_model←paymentModel, campaign_type←campaignType, title, description, button_text←buttonText,
link, origin_url←originUrl, preview_url←previewUrl, landing_id←landingID, advertiser_id←advertiserID,
manager_id←managerID`. Обогащение (ad-level): `account_id=1, source_type_id=9,
id_key_camp="1_"+campaign_id, id_key_ad=id_key_camp+"_"+creative_id`.

### Специфика
- `buttonText`, `originUrl`, `landingID` в реальном ответе **отсутствуют** → `None`.
- `title`/`description` могут быть пустыми (NaN) у части креативов.
- `legalInfo`, `media` (storageID медиафайлов) не выносим.
- В **списке** креативов поле группы — `groupID`; в ответе **creatives/stats** — `groupId` (см. ниже).
  Маппинг защищён: `_pick(e, "groupID", "groupId")`.
- На тестовом аккаунте: 18 креативов, 1 страница.

### История изменений
| Дата | Изменение | Причина |
|------|-----------|---------|
| 2026-06-09 | Первичная реализация | — |

---

## Функция: `get_campaigns_daily_stat`

- **Статус:** реализована · **Дата:** 2026-06-09 · **Тип:** статистика (по дням)
- **Файл:** `avito_performance.py` → `get_campaigns_daily_stat(date_from, date_to)`
- **Spec/Plan:** отдельно не составлялись (реализовано по `03_ENTITY_FUNCTIONS.md` + live-probe)
- **Smoke-test:** `smoke_tests/test_get_campaigns_daily_stat.py` · **CSV:** `raw_data/get_campaigns_daily_stat_{from}_{to}.csv`

### API-метод
- **Endpoint:** `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/stats` (sync, x-cost 10)
- Перебор: список кампаний из `_fetch_all_pages("/campaigns")` → по 1 вызову на кампанию.
- Берётся `campaign.data[]` (по дням); `groups[]`/`creatives[]` из ответа не используются здесь.

### Поля выходного DataFrame (27 колонок)
Ключи: `date←campaign.data[].timestamp[:10], campaign_id, campaign_name, payment_model, campaign_type`.
Метрики StatsData (без `ctr`/`cpm`/`cpc`/`q25`/`q50`/`q75` — исключены по требованию проекта):
`views, clicks, costs_nds←spend, spend_bonus←spendBonus, video_views_25/50/75/100←videoViews*, vtr`.
Обогащение расходов:
`costs_without_nds=costs_nds/(1.22 при year≥2026, иначе 1.20), ak=0.5, costs_nds_ak=costs_nds*1.5,
costs_without_nds_ak=costs_without_nds*1.5, account_id=1, source_type_id=9, id_key_camp`.

### Специфика
- **`costs_nds ← spend`** (Avito `spend` — целые ₽ **с НДС**, подтверждено доками). Ставка НДС для
  `costs_without_nds` — **по году даты строки: год ≥ 2026 → 22% (÷1.22), раньше → 20% (÷1.20)**;
  считается per-row через `_vat_divisor(df["date"])` (в одном отчёте возможны дни разных лет).
- `timestamp` в `data[]` приходит с офсетом **+03:00** (МСК); дата берётся как первые 10 символов
  (день в МСК). `totalData` (агрегат за период, без дневного `timestamp`) в DataFrame **не выгружается**.
- Видео-метрики (`video_views_*`, `q*`, `vtr`) приходят только у видео-кампаний; у textImage → `None`.
- Кампании без активности в периоде (draft/finished вне периода) → пустой `data[]`, строк не дают
  (ошибки не вызывают). На тестовом аккаунте за 2026-05-01…06-08: **93 строки**.

### История изменений
| Дата | Изменение | Причина |
|------|-----------|---------|
| 2026-06-09 | Первичная реализация | — |

---

## Функция: `get_groups_daily_stat`

- **Статус:** реализована · **Дата:** 2026-06-09 · **Тип:** статистика (по дням)
- **Файл:** `avito_performance.py` → `get_groups_daily_stat(date_from, date_to)`
- **Spec/Plan:** отдельно не составлялись (реализовано по `03_ENTITY_FUNCTIONS.md` + live-probe)
- **Smoke-test:** `smoke_tests/test_get_groups_daily_stat.py` · **CSV:** `raw_data/get_groups_daily_stat_{from}_{to}.csv`

### API-метод
- **Endpoint:** `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/groups/stats` (sync, x-cost 5)
- Перебор: группы из `_fetch_all_pages("/groups")` группируются по `campaignID`; на каждую кампанию —
  один вызов со списком её `groupIDs`. Берётся `groups[].data[]`.

### Поля выходного DataFrame (26 колонок)
Ключи: `date, campaign_id (из контекста перебора), group_id←groups[].id, group_name←groups[].name`.
Метрики StatsData + обогащение расходов — как в `get_campaigns_daily_stat` (без `id_key_ad`).

### Специфика
- `groupIDs` передаются батчем на кампанию (на тестовом аккаунте — по 1 группе). Документированного
  лимита на число ID в запросе нет; при большом числе групп может потребоваться батчинг.
- Прочее (costs_nds, НДС по году: 2026+ 22% / ранее 20%, timestamp +03:00, видео=None) — как в `get_campaigns_daily_stat`.
- На тестовом аккаунте: **93 строки**.

### История изменений
| Дата | Изменение | Причина |
|------|-----------|---------|
| 2026-06-09 | Первичная реализация | — |

---

## Функция: `get_creatives_daily_stat`

- **Статус:** реализована · **Дата:** 2026-06-09 · **Тип:** статистика (по дням, ad-level)
- **Файл:** `avito_performance.py` → `get_creatives_daily_stat(date_from, date_to)`
- **Spec/Plan:** отдельно не составлялись (реализовано по `03_ENTITY_FUNCTIONS.md` + live-probe)
- **Smoke-test:** `smoke_tests/test_get_creatives_daily_stat.py` · **CSV:** `raw_data/get_creatives_daily_stat_{from}_{to}.csv`

### API-метод
- **Endpoint:** `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/creatives/stats` (sync, x-cost 1)
- Перебор: креативы из `_fetch_all_pages("/creatives")` группируются по `campaignID`; на каждую кампанию —
  один вызов со списком её `creativeIDs`. Берётся `creatives[].data[]`.

### Поля выходного DataFrame (28 колонок)
Ключи: `date, campaign_id, group_id←creatives[].groupId, creative_id←creatives[].id, creative_name←creatives[].name`.
Метрики StatsData + обогащение расходов; ad-level → дополнительно `id_key_ad=id_key_camp+"_"+creative_id`.

### Специфика
- ⚠️ В ответе `creatives/stats` поле группы — **`groupId`** (строчная `d`), а в списке креативов — `groupID`.
  Маппинг: `_pick(cr, "groupId", "groupID")`.
- Прочее (costs_nds, НДС по году: 2026+ 22% / ранее 20%, timestamp +03:00, видео=None) — как в остальных stat-функциях.
- На тестовом аккаунте: **143 строки**.

### История изменений
| Дата | Изменение | Причина |
|------|-----------|---------|
| 2026-06-09 | Первичная реализация | — |

---
