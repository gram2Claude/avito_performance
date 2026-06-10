# Spec for get_campaign_dict

<!-- Имя файла: specs/01_spec_get_campaign_dict.md -->

## Summary

Новая публичная функция в `avito_performance.py`, возвращающая **справочник рекламных
кампаний аккаунта** — уникальные кампании с атрибутами, без дат. Источник —
`POST /ads/v1/account/{accountID}/campaigns` (синхронный JSON, постраничный).

Это первая реализуемая функция: она верифицирует базовую инфраструктуру скаффолда
(OAuth `client_credentials`, заголовок Bearer, обёртка `_post`, пагинация `_fetch_all_pages`,
кодировка/CSV). Все последующие функции опираются на ту же базу.

## Functional Requirements

### 1. Сигнатура функции

```python
def get_campaign_dict() -> pd.DataFrame:
    # Параметров нет. accountID и креды берутся клиентом из окружения
    # (ACCOUNT_ID, CLIENT_ID, CLIENT_SECRET) или из конструктора AvitoPerformanceClient.
```

### 2. Алгоритм

**Синхронный паттерн (с пагинацией):**

1. `client = AvitoPerformanceClient()` — токен и accountID берутся из окружения.
2. `entities = client._fetch_all_pages("/campaigns", "campaigns", filter_body={})`
   - тело каждого запроса: `{"filter": {}, "limit": 100, "page": N}` (`POST /ads/v1/account/{accountID}/campaigns`);
   - пустой `filter` → возвращаются кампании всех статусов;
   - идём по страницам, пока массив `campaigns` не опустеет или `page*100 >= total`.
3. Если `entities` пуст → вернуть `pd.DataFrame(columns=CAMPAIGN_DICT_COLUMNS)`.
4. Собрать DataFrame, маппя поля API → snake_case (см. таблицу §3).
5. `dropna(subset=["campaign_id"]).drop_duplicates(subset=["campaign_id"])`.
6. Добавить обогащение (см. «Обязательное обогащение»).
7. `df.reindex(columns=CAMPAIGN_DICT_COLUMNS).reset_index(drop=True)`.

> Примечание: справочник не делает запросов с датами; стоимость метода — 1 API-балл за страницу.

### 3. Возвращаемый DataFrame

> **Обновление 2026-06-10:** из выходного DataFrame удалены поля `status`, `budget`,
> `payment_model`, `start_date`, `end_date`, `created_at`, `updated_at` (требование проекта).
> Актуальный состав — **14 колонок**: `campaign_id, campaign_name, campaign_type, advertiser_id,
> contract_id, manager_id, account_id, source_type_id, product_id, product_name, camp_type,
> camp_category, id_key_camp, owner_id` — см. `info/01_functions_implemented.md`.
> Таблицы ниже отражают первоначальную спецификацию на момент реализации.

Все имена колонок — **snake_case**.

**Поля из API** (элемент массива `campaigns[]`):

| Колонка | Тип | Источник API | Описание |
|---------|-----|--------------|----------|
| `campaign_id` | integer | `id` | ID кампании |
| `campaign_name` | string | `name` | Название кампании |
| `status` | string | `status` | Статус (`draft`/`active`/`paused`/… 11 значений) |
| `budget` | integer | `budget` | Бюджет, ₽ с НДС |
| `payment_model` | string | `paymentModel` | `CPM` / `CPC` |
| `campaign_type` | string | `campaignType` | `textImage` / `HTML` / `video` |
| `start_date` | string | `startDate` | Дата начала размещения |
| `end_date` | string | `endDate` | Дата окончания размещения |
| `advertiser_id` | integer | `advertiserId` | ID рекламодателя |
| `contract_id` | integer | `contractId` | ID договора |
| `manager_id` | integer | `managerID` | ID менеджера (внимание: в API `managerID`, заглавные ID) |
| `created_at` | string | `createdAt` | Дата создания (ISO 8601) |
| `updated_at` | string | `updatedAt` | Дата обновления (ISO 8601) |

> ⚠️ В ответе API регистр ключей неоднороден: `advertiserId`, `contractId` (строчная `d`/`Id`),
> но `managerID` (заглавные `ID`). Маппинг использует точные имена ключей через `_pick`.
> Поля `accountId`, `userId`, `additionalAgreementID`, `performanceAdditionalAgreementID`
> из ответа в DataFrame не выносим (не входят в согласованный набор Fn5).

#### Обязательное обогащение DataFrame (соглашение проекта)

Справочник (без дат) — добавляются константные и вычисляемые поля:

| Колонка | Тип | Источник | Описание |
|---------|-----|----------|----------|
| `account_id` | integer | константа `1` | пример, заменить при интеграции |
| `source_type_id` | integer | константа `9` | пример |
| `product_id` | integer | константа `1` | пример |
| `product_name` | string | константа `"prod_test"` | пример |
| `camp_type` | string | константа `"camp_test"` | пример |
| `camp_category` | string | константа `"cat_test"` | пример |
| `id_key_camp` | string | вычисляется: `"1_" + str(campaign_id)` | составной ключ |
| `owner_id` | integer | константа `1` | пример |

Итоговый порядок колонок — константа `CAMPAIGN_DICT_COLUMNS` (уже в `avito_performance.py`):
`campaign_id, campaign_name, status, budget, payment_model, campaign_type, start_date, end_date,
advertiser_id, contract_id, manager_id, created_at, updated_at, account_id, source_type_id,
product_id, product_name, camp_type, camp_category, id_key_camp, owner_id`.

> Расходов в справочнике нет → блок `costs_*`/`ak` не применяется.

### 4. Изменения в `avito_performance.py`

- Константа `CAMPAIGN_DICT_COLUMNS` — **уже есть** (скаффолд), править не нужно.
- Реализовать тело публичной функции `get_campaign_dict()` (заменить `raise NotImplementedError`).
- Приватный метод не нужен — достаточно существующего `_fetch_all_pages`.
- Docstring модуля и функции уже актуальны.

## Ограничения API

| Ограничение | Значение | Реализация |
|-------------|----------|------------|
| Размер страницы (`limit`) | 1–100 (дефолт 20) | `PAGE_LIMIT = 100`, пагинация в `_fetch_all_pages` |
| Завершение пагинации | по `total` / пустому массиву | `page*PAGE_LIMIT >= total` или пустой `campaigns` |
| Стоимость метода | 1 API-балл / страница | мониторится по заголовку `Api-Point-Balance` (не enforced) |
| Rate limit | 500 запросов/минуту | общий для аккаунта |
| Период | не применяется (справочник без дат) | — |

**Поведение при 429:** экспоненциальный backoff, базовый интервал `RATE_LIMIT_BASE_SEC = 1` сек,
удвоение, макс `RATE_LIMIT_RETRY_MAX = 5` повторов, учёт заголовка `Retry-After`. Реализовано в `_request`.

## Possible Edge Cases

- **Нет кампаний** у аккаунта → `pd.DataFrame(columns=CAMPAIGN_DICT_COLUMNS)` (пустой, но с колонками).
- **`total = 0`** → первая же страница пустая, цикл завершается сразу.
- **Кампания без `name`/дат** → значение `None`, строка сохраняется (не дропаем по этим полям).
- **Неоднородный регистр ключей** (`managerID` vs `advertiserId`) → точные имена в маппинге.
- **Кампания без `id`** (теоретически) → строка дропается (`dropna(subset=["campaign_id"])`).
- **Дубликаты по `campaign_id`** между страницами → `drop_duplicates(subset=["campaign_id"])`.

## Acceptance Criteria

- [ ] `get_campaign_dict()` возвращает DataFrame с колонками `CAMPAIGN_DICT_COLUMNS` (21 колонка, точный порядок).
- [ ] Одна строка на уникальную кампанию (`campaign_id` уникален, дубликатов нет).
- [ ] `account_id == 1`, `source_type_id == 9`, `id_key_camp == "1_" + str(campaign_id)` для всех строк.
- [ ] При отсутствии данных — пустой DataFrame с правильными колонками (не падает).
- [ ] Существующие функции (стабы) и импорт модуля не ломаются.
- [ ] Smoke-тест на реальном API проходит; результат сохранён в `raw_data/get_campaign_dict.csv` (cp1251).

## Open Questions

- Возвращает ли пустой `filter: {}` кампании **всех** статусов (включая `archived`/`draft`)?
  Предполагаем «да». Проверить реальным запросом; если архивные не нужны — добавить фильтр статусов.
- Формат `startDate`/`endDate`/`createdAt`/`updatedAt` в реальном ответе — `YYYY-MM-DD` или полный ISO
  с временем? В доках примеры показывают и то, и то. Оставляем как строку «как пришло»; при необходимости
  нормализуем `_day_from_timestamp` на этапе реализации.
- Поле `managerID` — может быть `0`/`null`, если менеджер не назначен. Сохраняем как есть.
