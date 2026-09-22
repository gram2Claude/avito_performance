# ТЗ: Avito Performance (Авито Реклама) API — портирование на другой язык

Эталонная реализация: `avito_performance/avito_performance.py` (Python).
Цель — портировать функциональность на целевой язык (PHP / Go / Java / …) с сохранением
структуры выходных данных. Документ самодостаточен: доступ к Python-коду не требуется.

Версия документа: 2026-09-22 (предыдущая — 2026-06-10).

> **Что изменилось в версии 2026-09-22:** денежные метрики статистики перешли в копейки —
> `spendKopecs` / `spendBonusKopecs` вместо исчезнувших рублёвых `spend` / `spendBonus`
> (см. 3.6). Порядок и состав колонок выгрузок не изменился.

---

## 1. Цель проекта

Разработать библиотеку для работы с API Авито Реклама (Avito Performance).
Библиотека загружает справочники (кампании, группы, креативы) и собирает дневную
статистику (показы, клики, расход, видео-метрики) на трёх уровнях, плюс строит
сводную таблицу-агрегат `admin_audit`.

Выход каждой публичной функции — структурированный массив строк (эквивалент
pandas DataFrame в Python-эталоне) с фиксированным набором и порядком колонок.

---

## 2. Общая логика работы библиотеки

API **синхронный, формат JSON** — без submit/poll/download, без CSV/ZIP.

1. **Справочники** (кампании / группы / креативы) — постраничный `POST` с телом
   `{"filter": {}, "limit": 100, "page": N}`; страницы собираются, пока не придёт
   пустой массив или `page*limit >= total`.
2. **Статистика** — перебор сущностей: на каждую кампанию один `POST .../stats`
   с `{"dateFrom": ..., "dateTo": ...}` (для групп/креативов — плюс массив их ID,
   сгруппированный по кампании из соответствующего справочника). API возвращает
   `data[]` сразу за весь период (≤ 100 дней) — **разворачивать по дням локально,
   НЕ делать запрос на каждый день**.
3. **Обогащение** — к строкам добавляются константные и вычисляемые поля
   (разделы 3.7 и 4), затем колонки приводятся к фиксированному набору и порядку.

---

## 3. Ключевые принципы работы с API Авито Реклама

### 3.1. Авторизация

- OAuth 2.0, `grant_type=client_credentials`: `POST https://api.avito.ru/token`.
- ⚠️ **Тело запроса — `application/x-www-form-urlencoded`** (форма, НЕ JSON).
  Отправка JSON — типичная ошибка, токен не выдаётся.
- Ответ: `{access_token, expires_in (86400 сек = 24 ч), token_type: "Bearer"}`.
- Заголовок всех запросов к `/ads/*`: `Authorization: Bearer <token>`.
- Токен обновлять заранее — за 60 сек до истечения (`TOKEN_REFRESH_LEEWAY_SEC = 60`).
- Учётные данные: переменные окружения `CLIENT_ID` / `CLIENT_SECRET`; ID рекламного
  аккаунта — `ACCOUNT_ID`.
- ⚠️ **Токен привязан к одному `accountID`**: запрос к чужому аккаунту → `403`.
  Единого «агентского» токена и метода «список кабинетов» нет. Один кабинет =
  отдельная тройка `CLIENT_ID`/`CLIENT_SECRET`/`ACCOUNT_ID`; клиент инстанцируется
  на конкретный кабинет.

### 3.2. Базовый URL и используемые эндпоинты

`BASE_URL = https://api.avito.ru`, все методы — под префиксом `/ads/v1`.

| Метод | Путь | Назначение | x-cost |
|-------|------|-----------|--------|
| POST | `/ads/v1/account/{accountID}/campaigns` | Справочник кампаний (постранично) | 1/стр |
| POST | `/ads/v1/account/{accountID}/groups` | Справочник групп (постранично) | 1/стр |
| POST | `/ads/v1/account/{accountID}/creatives` | Справочник креативов (постранично) | 1/стр |
| POST | `/ads/v1/account/{accountID}/campaigns/{campaignID}/stats` | Статистика по кампании | 10 |
| POST | `/ads/v1/account/{accountID}/campaigns/{campaignID}/groups/stats` | Статистика по группам кампании | 5 |
| POST | `/ads/v1/account/{accountID}/campaigns/{campaignID}/creatives/stats` | Статистика по креативам кампании | 1 |

### 3.3. Схема получения данных

Все методы **синхронные** — данные возвращаются в ответе сразу, без UUID и polling.
Статистика отдаётся вложенным массивом `data[]` (элемент = день с `timestamp`);
агрегат за период — `totalData` (в выгрузку **не** берём).

### 3.4. Лимиты API — критичны

| Лимит | Значение | Как соблюдать |
|-------|----------|---------------|
| Запросов в минуту на аккаунт | 500 | При 429 — экспоненциальный backoff |
| API-баллы | у каждого метода свой `x-cost`; пул **общий на аккаунт** (все ключи), сброс **раз в неделю, пн 00:00 UTC** | Остаток — в заголовке ответа `Api-Point-Balance`; исчерпан → запросы не обрабатываются |
| Период статистики | ≤ 100 дней между `dateFrom` и `dateTo` | Валидировать на входе |
| Пагинация | `limit` 1–100 (дефолт 20), `page` ≥ 1 | Использовать `limit=100` |

### 3.5. Обработка ошибок и rate-limit

- **HTTP 429** — повторить с экспоненциальным backoff: стартовая пауза 1 сек,
  удвоение, до 5 повторов. Уважать заголовок `Retry-After`, если присутствует.
- **Единая схема ошибки:** `{"code": string, "message": string}`.
- **HTTP-коды:** `400` (невалидное тело / период > 100 дней), `401` (нет/просрочен
  токен), `403` (токен не на этот `accountID`), `404` (сущность не найдена),
  `429` (лимит), `500`, `503`.
- **Ошибки на уровне сущности** (одна кампания вернула ошибку) — логировать
  предупреждение и продолжать цикл, не прерывая общую выгрузку.
- Кампании без активности в периоде возвращают пустой `data[]` — это не ошибка,
  строк в результат они не дают.

### 3.6. Подводные камни форматов данных

- **Деньги в статистике — целые числа в КОПЕЙКАХ, С НДС** (`spendKopecs`, `spendBonusKopecs`);
  приходят как JSON integer. Перед записью в выгрузку **делятся на 100** → рубли с копейками.
  > ⚠️ **Изменение источника (2026-09-22):** прежние рублёвые поля `spend` / `spendBonus`
  > из ответа **исчезли** — вместо них `spendKopecs` / `spendBonusKopecs`. Реализация
  > **не должна** читать старые поля даже как запасной вариант: рубли, принятые за копейки,
  > занизят расход в 100 раз и сделают это молча. Отсутствующее поле → пустое значение
  > (`None`), а не `0`.
  > ⚠️ **Прежнее предупреждение о расхождениях с личным кабинетом снято:** оно объяснялось
  > целочисленным рублёвым входом, которого больше нет — копейки приходят из API.
  > Деньги **вне статистики** (`budget`, `price`, `balance`, `bonusBalance`) на копеечный
  > формат не перепроверялись и в выгрузках не участвуют.
- **`costs_nds` в выгрузке — десятичный тип (float), округление до 2 знаков** сразу
  после чтения из API, до вычисления производных полей.
- **Два формата дат в одном ответе** (список кампаний):
  `createdAt` — чистый ISO 8601 (`2026-06-05T15:54:49Z`); `startDate`/`endDate`/`updatedAt`
  — Go-time `time.String()` (`2026-06-19 20:00:00 +0000 UTC`, иногда с миллисекундами,
  всегда `+0000`). У групп/креативов все даты — ISO `Z`.
  ⚠️ Для ISO-строки с `Z` НЕЛЬЗЯ конвертировать naive-datetime через локальную таймзону —
  время сдвинется на offset машины. `Z`-значения форматировать без сдвига.
- **`timestamp` статистики** приходит с офсетом `+03:00` (МСК): дата строки = первые
  10 символов (`YYYY-MM-DD`, день в МСК).
- **Неоднородный регистр ключей API:** `advertiserId`, `contractId`, `accountId`,
  `userId` — но `managerID`, `campaignID`, `advertiserID` (у групп/креативов);
  в списке креативов поле группы — `groupID`, а в ответе `creatives/stats` — `groupId`.
  Обязателен helper «взять первый существующий ключ»: `pick(row, "groupID", "groupId")`.
- **Видео-метрики** (`videoViews25/50/75/100`) приходят только у видео-кампаний;
  у `textImage` отсутствуют → в выгрузке `NULL`.
- **`filter: {}`** в справочниках возвращает сущности **всех** статусов
  (active/finished/draft/…). Поле `haveCreative` у групп в реальном ответе отсутствует.
- **Метрики `ctr`, `cpm`, `cpc`, `q25`, `q50`, `q75`, `vtr` из API НЕ выгружаются** —
  исключены по требованию проекта. Охватных метрик (reach) в API нет вовсе.

### 3.7. Обогащение строк (соглашение проекта)

Константные и вычисляемые поля добавляются на стороне клиента **до** финальной
сборки колонок. Значения констант — примеры, заменяются при интеграции.

- Для всех функций: `account_id = 1`, `source_type_id = 9`.
- Справочник кампаний: `product_id = 1`, `product_name = "prod_test"`,
  `camp_type = "camp_test"`, `camp_category = "cat_test"`, `owner_id = 1`.
- Справочник групп: `camp_type`, `camp_category`, `owner_id` — **join из справочника
  кампаний** по `campaign_id`; `group_type = "other"`, `group_category = "other"` — дефолт.
- Справочник креативов: `id_key_group`, `owner_id` — **join из справочника групп** по `group_id`.
- Для функций с расходами (`ak = 0.5` — агентская комиссия):
  - `costs_nds` ← API `spendKopecs` / 100 (копейки → рубли); десятичный тип, округление
    до 2 знаков. Аналогично `spend_bonus` ← `spendBonusKopecs` / 100;
  - `costs_without_nds = costs_nds / (1 + ставка_НДС)` — **ставка по году даты строки:
    год ≥ 2026 → 22% (делитель 1.22), раньше → 20% (делитель 1.20)**; вычисляется
    per-row (в одном отчёте возможны дни разных лет);
  - `costs_nds_ak = costs_nds * 1.5`; `costs_without_nds_ak = costs_without_nds * 1.5`.
- Составные ключи:
  - `id_key_camp = "1_" + campaign_id` — все функции;
  - `id_key_group = id_key_camp + "_" + group_id` — справочники групп и креативов;
  - `id_key_ad = id_key_group + "_" + creative_id` — только ad-level (креативы = объявления).

---

## 4. Публичные функции

Всего **7 функций**. Колонки и их порядок — фиксированные (контракты ниже).

> ⚠️ **Максимальный период статистики — 100 дней.** Все stat-функции (4.4–4.7) принимают
> `date_from` / `date_to` (`YYYY-MM-DD`); разница между ними не должна превышать **100 дней**
> (`PERIOD_MAX_DAYS = 100`) — ограничение API: при превышении сервер возвращает `400`.
> Валидировать период на входе; за более длинные интервалы — несколько последовательных
> вызовов с разбиением периода на куски ≤ 100 дней.

### 4.1. get_campaign_dict() — справочник кампаний

`POST /ads/v1/account/{accountID}/campaigns`, постранично. 14 колонок:

| Поле | Тип | Источник |
|------|-----|----------|
| `campaign_id` | integer | `id` |
| `campaign_name` | string | `name` |
| `campaign_type` | string | `campaignType` (`textImage`/`HTML`/`video`) |
| `advertiser_id` | integer | `advertiserId` |
| `contract_id` | integer | `contractId` |
| `manager_id` | integer | `managerID` (⚠️ заглавные `ID`) |
| `account_id` | integer | константа `1` |
| `source_type_id` | integer | константа `9` |
| `product_id` | integer | константа `1` |
| `product_name` | string | константа `"prod_test"` |
| `camp_type` | string | константа `"camp_test"` |
| `camp_category` | string | константа `"cat_test"` |
| `id_key_camp` | string | вычисляется: `"1_" + campaign_id` |
| `owner_id` | integer | константа `1` |

Дедупликация по `campaign_id` (выживает первая строка); строки без `id` отбрасываются.

### 4.2. get_group_dict() — справочник групп

`POST /ads/v1/account/{accountID}/groups`, постранично. 17 колонок:

| Поле | Тип | Источник |
|------|-----|----------|
| `group_id` | integer | `id` |
| `group_name` | string | `name` |
| `campaign_id` | integer | `campaignID` |
| `status` | string | `status` |
| `payment_model` | string | `paymentModel` (`CPM`/`CPC`) |
| `format` | string | `format` (`media`/`native`/…) |
| `advertiser_id` | integer | `advertiserID` |
| `manager_id` | integer | `managerID` |
| `account_id` | integer | константа `1` |
| `source_type_id` | integer | константа `9` |
| `camp_type` | string | **join из справочника кампаний** по `campaign_id` |
| `camp_category` | string | **join из справочника кампаний** |
| `group_type` | string | дефолт `"other"` |
| `group_category` | string | дефолт `"other"` |
| `id_key_camp` | string | `"1_" + campaign_id` |
| `id_key_group` | string | `id_key_camp + "_" + group_id` |
| `owner_id` | integer | **join из справочника кампаний** |

### 4.3. get_creative_dict() — справочник креативов (объявлений)

`POST /ads/v1/account/{accountID}/creatives`, постранично. 22 колонки:
`creative_id←id, creative_name←name, group_id←groupID, campaign_id←campaignID, status,
payment_model←paymentModel, campaign_type←campaignType, title, description,
button_text←buttonText, link, origin_url←originUrl, preview_url←previewUrl,
landing_id←landingID, advertiser_id←advertiserID, manager_id←managerID` +
обогащение: `account_id, source_type_id, id_key_camp, id_key_group, id_key_ad, owner_id`.

- `id_key_group`, `owner_id` — **join из справочника групп** по `group_id`;
  `id_key_ad = id_key_group + "_" + creative_id`.
- `buttonText`, `originUrl`, `landingID` в реальном ответе отсутствуют → `NULL`;
  `title`/`description` могут быть пустыми.

### 4.4. get_campaigns_daily_stat(date_from, date_to) — статистика по кампаниям

Перебор кампаний из справочника → на каждую `POST .../campaigns/{id}/stats` с
`{"dateFrom", "dateTo"}`; разворачивается `campaign.data[]`. 19 колонок:
`date` (из `timestamp[:10]`), `campaign_id`, `payment_model`, `campaign_type`,
метрики `impressions←views, clicks, costs_nds←spendKopecs/100, spend_bonus←spendBonusKopecs/100,
video_views_25/50/75/100←videoViews*`, расходные производные
`costs_without_nds, ak, costs_nds_ak, costs_without_nds_ak`, `account_id`,
`source_type_id`, `id_key_camp`.

⚠️ Поле названия (`campaign_name`) в статистике отсутствует — имена джойнить
из справочника по `campaign_id`. Метрика показов называется **`impressions`**
(в API — `views`).

### 4.5. get_groups_daily_stat(date_from, date_to) — статистика по группам

ID групп из справочника группируются по `campaign_id`; на кампанию один
`POST .../groups/stats` с `{"groupIDs": [...], "dateFrom", "dateTo"}`;
разворачивается `groups[].data[]`. 18 колонок: как 4.4, но вместо
`payment_model`/`campaign_type` — `group_id` (название группы не выгружается).

### 4.6. get_creatives_daily_stat(date_from, date_to) — статистика по креативам

ID креативов группируются по `campaign_id`; на кампанию один
`POST .../creatives/stats` с `{"creativeIDs": [...], "dateFrom", "dateTo"}`;
разворачивается `creatives[].data[]`. 20 колонок: `date, campaign_id,
group_id←creatives[].groupId (⚠️ строчная d), creative_id` + метрики и расходные
производные + `account_id, source_type_id, id_key_camp, id_key_ad`, где
`id_key_ad = id_key_camp + "_" + group_id + "_" + creative_id`.

### 4.7. get_admin_audit(date_from, date_to) — сводный аудит (таблица admin_audit)

Собственного эндпоинта нет — **агрегат поверх 4.4**: к строкам статистики кампаний
джойнится `owner_id` из справочника кампаний, затем метрики **суммируются** по ключу
`date × account_id × source_type_id × owner_id`. 9 колонок:

| Поле | Тип | Источник |
|------|-----|----------|
| `date` | string | ключ группировки |
| `account_id` | integer | константа `1` (ключ группировки) |
| `source_type_id` | integer | константа `9` (ключ группировки) |
| `owner_id` | integer | join из справочника кампаний (ключ группировки) |
| `impressions` | integer | сумма |
| `clicks` | integer | сумма |
| `costs_nds` | float | сумма, округление до 2 знаков |
| `costs_without_nds` | float | сумма |
| `chef_flag` | integer | константа `1` (дефолт) |

---

## 5. Алгоритм сбора статистики (общий шаблон)

```
1. POST /ads/v1/account/{accountID}/campaigns (постранично) → список кампаний.
2. Для групп/креативов: POST .../groups | .../creatives (постранично) →
   ID сущностей, сгруппированные по campaign_id.
3. Для каждой кампании:
     a. POST .../campaigns/{id}/stats (или groups/stats | creatives/stats
        с массивом ID) с {"dateFrom": ..., "dateTo": ...}.
     b. Развернуть data[] → по строке на (сущность × день);
        date = timestamp[:10]; пустой data[] → пропустить.
     c. При ошибке — лог + продолжить со следующей кампанией.
4. Обогащение: costs_nds → float.round(2); costs_without_nds по ставке НДС
   года строки; ak/costs_*_ak; константы; составные ключи.
5. Привести к фиксированному набору и порядку колонок.
```

---

## 6. Примеры запросов и ответов API (реальные)

### 6.1. Авторизация

```
POST https://api.avito.ru/token
Content-Type: application/x-www-form-urlencoded

client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>&grant_type=client_credentials

Ответ:
{ "access_token": "eyJhbGc...", "expires_in": 86400, "token_type": "Bearer" }
```

### 6.2. Справочник кампаний

```
POST https://api.avito.ru/ads/v1/account/{accountID}/campaigns
Authorization: Bearer <token>
Content-Type: application/json

{ "filter": {}, "limit": 100, "page": 1 }

Ответ (фрагмент):
{
  "campaigns": [
    {
      "id": 297840407,
      "name": "5ka_rf-KomboZvezdy_06_2026_med",
      "status": "active",
      "budget": 1390800,
      "paymentModel": "CPM",
      "campaignType": "textImage",
      "startDate": "2026-06-05 15:47:00.692 +0000 UTC",
      "endDate": "2026-06-19 20:00:00 +0000 UTC",
      "advertiserId": 574505283,
      "contractId": 786670188,
      "managerID": 313033278,
      "createdAt": "2026-06-05T15:54:49Z",
      "updatedAt": "2026-06-19 20:00:00 +0000 UTC"
    }
  ],
  "total": 17
}
```

### 6.3. Статистика по кампании

```
POST https://api.avito.ru/ads/v1/account/{accountID}/campaigns/272290369/stats
Authorization: Bearer <token>
Content-Type: application/json

{ "dateFrom": "2026-06-02", "dateTo": "2026-06-02" }

Ответ (фрагмент; spendKopecs — JSON integer, КОПЕЙКИ с НДС → делить на 100):
{
  "campaign": {
    "id": 272290369,
    "paymentModel": "CPC",
    "campaignType": "textImage",
    "data": [
      { "timestamp": "2026-06-02T00:00:00+03:00", "views": 26202, "clicks": 36,
        "spendKopecs": 15100, "spendBonusKopecs": 0,
        "ctr": 0.00137, "cpc": 420.75, "cpm": 578.08 }
    ],
    "totalData": { "views": 26202, "clicks": 36, "spendKopecs": 15100 }
  }
}
```

`ctr`/`cpc`/`cpm` и `totalData` в выгрузку не берутся.

### 6.4. Статистика по группам / креативам

```
POST .../campaigns/{campaignID}/groups/stats
{ "groupIDs": [548487753547], "dateFrom": "2026-06-02", "dateTo": "2026-06-02" }
→ { "groups": [ { "id": 548487753547, "data": [ {...} ] } ] }

POST .../campaigns/{campaignID}/creatives/stats
{ "creativeIDs": [601237520391766], "dateFrom": "2026-06-02", "dateTo": "2026-06-02" }
→ { "creatives": [ { "id": 601237520391766, "groupId": 548487753547, "data": [ {...} ] } ] }
```

⚠️ В `creatives/stats` поле группы — `groupId` (строчная `d`), в списке креативов — `groupID`.

---

## 7. Примеры таблиц на выходе (реальные строки)

### 7.1. get_campaign_dict — справочник кампаний

| campaign_id | campaign_name | campaign_type | advertiser_id | contract_id | manager_id |
|---|---|---|---|---|---|
| 509702671 | 5ka_rf-barni_05_2026_nat | textImage | 574505283 | 786670188 | 313033278 |
| 297840407 | 5ka_rf-KomboZvezdy_06_2026_med | textImage | 574505283 | 786670188 | 313033278 |

Константные/вычисляемые поля (для тех же 2 строк в том же порядке):

| account_id | source_type_id | product_id | product_name | camp_type | camp_category | id_key_camp | owner_id |
|---|---|---|---|---|---|---|---|
| 1 | 9 | 1 | prod_test | camp_test | cat_test | 1_509702671 | 1 |
| 1 | 9 | 1 | prod_test | camp_test | cat_test | 1_297840407 | 1 |

### 7.2. get_group_dict — справочник групп

| group_id | group_name | campaign_id | status | payment_model | format | advertiser_id | manager_id |
|---|---|---|---|---|---|---|---|
| 148335493810 | Группа – 1 | 297840407 | active | CPM | media | 574505283 | 313033278 |
| 638420779651 | Группа – 1 | 563334516 | active | CPC | native | 574505283 | 410865360 |

Обогащение (для тех же 2 строк; camp_type/camp_category/owner_id — join из кампаний):

| account_id | source_type_id | camp_type | camp_category | group_type | group_category | id_key_camp | id_key_group | owner_id |
|---|---|---|---|---|---|---|---|---|
| 1 | 9 | camp_test | cat_test | other | other | 1_297840407 | 1_297840407_148335493810 | 1 |
| 1 | 9 | camp_test | cat_test | other | other | 1_563334516 | 1_563334516_638420779651 | 1 |

### 7.3. get_creative_dict — справочник креативов

| creative_id | creative_name | group_id | campaign_id | status | payment_model | campaign_type |
|---|---|---|---|---|---|---|
| 213211925758022 | Ножи | 203449948197 | 322501250 | draft | CPC | textImage |
| 786710393921224 | twix | 148335493810 | 297840407 | active | CPM | textImage |

Ключи (для тех же 2 строк; id_key_group/owner_id — join из справочника групп):

| id_key_camp | id_key_group | id_key_ad | owner_id |
|---|---|---|---|
| 1_322501250 | 1_322501250_203449948197 | 1_322501250_203449948197_213211925758022 | 1 |
| 1_297840407 | 1_297840407_148335493810 | 1_297840407_148335493810_786710393921224 | 1 |

(`title`/`description`/`link`/`preview_url` и пр. опущены здесь для компактности — в выгрузке присутствуют.)

### 7.4. get_campaigns_daily_stat — статистика по кампаниям

| date | campaign_id | payment_model | campaign_type | impressions | clicks | costs_nds | costs_without_nds | ak | costs_nds_ak | costs_without_nds_ak | id_key_camp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06-02 | 563334516 | CPC | textImage | 1048189 | 1954 | 13511.0 | 11074.59 | 0.5 | 20266.5 | 16611.89 | 1_563334516 |
| 2026-06-02 | 534075762 | CPM | textImage | 109316 | 196 | 23393.0 | 19174.59 | 0.5 | 35089.5 | 28761.89 | 1_534075762 |

(`spend_bonus`, `video_views_25/50/75/100`, `account_id=1`, `source_type_id=9` опущены для компактности.)

### 7.5. get_groups_daily_stat / get_creatives_daily_stat

| date | campaign_id | group_id | creative_id | impressions | clicks | costs_nds | id_key_camp | id_key_ad |
|---|---|---|---|---|---|---|---|---|
| 2026-05-30 | 272290369 | 548487753547 | — (группы) | 1484299 | 1777 | 31991.0 | 1_272290369 | — |
| 2026-05-30 | 272290369 | 548487753547 | 601237520391766 (креативы) | 1484299 | 1777 | 31991.0 | 1_272290369 | 1_272290369_548487753547_601237520391766 |

### 7.6. get_admin_audit — сводный аудит

| date | account_id | source_type_id | owner_id | impressions | clicks | costs_nds | costs_without_nds | chef_flag |
|---|---|---|---|---|---|---|---|---|
| 2026-05-31 | 1 | 9 | 1 | 1301169 | 1779 | 22938.0 | 18801.64 | 1 |
| 2026-06-01 | 1 | 9 | 1 | 2271039 | 2841 | 149688.0 | 122695.08 | 1 |
| 2026-06-02 | 1 | 9 | 1 | 3175332 | 5069 | 206898.0 | 169588.52 | 1 |

---

## 8. Рекомендации по реализации

- **HTTP-клиент** с retry-middleware для 429 (backoff 1 → 2 → 4 → 8 → 16 сек, макс. 5 повторов,
  уважать `Retry-After`); таймаут запроса 30 сек.
- **Кэширование токена**: хранить `token` + `expiresAt`; метод `ensureToken()` перед каждым
  запросом, обновление за 60 сек до истечения.
- **`pick()`-helper**: первый существующий ключ из списка вариантов
  (`pick(row, "groupID", "groupId")`) — обязателен из-за неоднородного регистра ключей API.
- **Нормализация дат**: ISO-`Z` — без сдвига таймзоны; Go-time (`2026-06-19 20:00:00 +0000 UTC`)
  — парсить отдельно; день статистики = `timestamp[:10]`.
- **Деньги**: integer на входе → десятичный тип, округление до 2 знаков (`costs_nds`);
  ставка НДС по году даты строки (≥ 2026 → 1.22, иначе 1.20).
- **Порядок вызова справочников**: кампании → группы (join полей кампаний) →
  креативы (join полей групп). admin_audit использует статистику кампаний + справочник кампаний.
- **Логирование**: пропуск сущности при ошибке — `warning`, не остановка процесса.
- **Тайминги** (константы):

| Константа | Значение |
|-----------|---------|
| `PAGE_LIMIT` | 100 |
| `PERIOD_MAX_DAYS` | 100 |
| `HTTP_TIMEOUT_SEC` | 30 |
| `TOKEN_TTL_SEC` | 86400 |
| `TOKEN_REFRESH_LEEWAY_SEC` | 60 |
| `RATE_LIMIT_BASE_SEC` | 1 |
| `RATE_LIMIT_RETRY_MAX` | 5 |

- **Тесты**: моки HTTP-клиента на все 7 публичных функций + retry на 429 + пустые ответы
  (пустой DataFrame с правильными колонками) + смешанные форматы дат + дедупликация ID.

---

## 9. Критерии приёмки

- [ ] Все 7 публичных функций возвращают данные с теми же колонками и в том же порядке,
      что в Python-эталоне `avito_performance.py` (разделы 4.1–4.7).
- [ ] Токен запрашивается формой (`x-www-form-urlencoded`) и автоматически
      переподписывается при многочасовом цикле.
- [ ] Корректная работа на реальных учётных данных: ≥ 15 кампаний, период > 7 дней,
      без ошибок 429 (backoff отрабатывает).
- [ ] `costs_nds` — десятичный тип с округлением до 2 знаков; `costs_without_nds`
      считается по ставке НДС года строки (1.22 / 1.20).
- [ ] Строки разворачиваются по дням локально из `data[]` (1 запрос на сущность за период,
      НЕ по запросу на день).
- [ ] Составные ключи: `id_key_camp` / `id_key_group` / `id_key_ad` — по формулам раздела 3.7.
- [ ] При сбое любой кампании процесс продолжает работать, ошибка попадает в лог.
- [ ] README с примерами вызова + `.env.example` (`CLIENT_ID`, `CLIENT_SECRET`, `ACCOUNT_ID`).
