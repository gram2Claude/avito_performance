# Сводка методов API — Avito Performance (Авито Реклама)

> Источник правды: официальная документация Авито.
> - Каталог методов: `https://developers.avito.ru/api-catalog/ads/documentation` (slug `ads` — «Авито Реклама»)
> - Авторизация: `https://developers.avito.ru/api-catalog/auth/documentation` (slug `auth`)
> - Рабочая справка кабинета: `https://ads-help.avito.com/external/api` (ссылка A3 из анкеты)
> - Спеки получены машинно через внутренний эндпоинт портала разработчика
>   `GET https://developers.avito.ru/web/1/openapi/info/{ads|auth}` (OpenAPI 3.0 + markdown-доки).
>
> Сформировано: 2026-06-09. Поля и типы — оригинальные, как в доках, без перевода/переименования.

## Общая характеристика API

| Параметр | Значение |
|---|---|
| Базовый URL (prod) | `https://api.avito.ru/ads/` (версия `v1`) → полный префикс `https://api.avito.ru/ads/v1/` |
| Базовый URL (sandbox) | `https://api.avito.ru/ads-sandbox/v1/` |
| Эндпоинт токена | `https://api.avito.ru/token` |
| Формат | JSON (везде, кроме токена — там `x-www-form-urlencoded` в запросе) |
| Характер методов | **Синхронный** — ответ сразу в теле. Нет async submit/poll/download, нет CSV/TSV/ZIP. |
| Авторизация | OAuth 2.0 **client_credentials**, заголовок `Authorization: Bearer <access_token>` |
| Кодировка | UTF-8 (JSON) |
| Привязка токена | Токен привязан к **одному рекламному аккаунту** (`accountID`). Для дочерних аккаунтов выпускаются отдельные ключи. |
| Rate limit | **500 запросов/минуту** по умолчанию (на аккаунт, пополняется поминутно). Доп. лимит — «API-баллы»: у каждого метода своя стоимость `x-cost`, остаток в заголовке ответа `Api-Point-Balance`. Пул баллов **общий на аккаунт (на все ключи/токены)** и **восстанавливается раз в неделю — в понедельник 00:00 UTC** (= 03:00 МСК). Когда баллы кончились — запросы перестают обрабатываться (не `429`, а исчерпание недельного пула). Источник: справка Авито Рекламы `ads-help.avito.com/external/api`. |
| При `429` | Повтор с экспоненциальным backoff (1 → 2 → 4 → 8 c). |

**Важно про охват:** в StatsData **нет поля reach/охвата** (уникальные пользователи). Доступны только
показы (`views`), клики (`clicks`), расход (`spend`/`spendBonus`), `ctr`, `cpm`, `cpc` и видео-метрики.
→ В этом проекте **охватных функций не будет** — только справочники и статистика.

---

## 1. Аутентификация — выпуск access-токена

### Метод: `POST https://api.avito.ru/token`
- **Назначение:** выпуск временного access-токена.
- **Тип авторизации:** `client_credentials` (персональная авторизация своего кабинета).
- **Где взять ключи:** кабинет Авито Реклама → вкладка **API** (доступно роли **Администратор**).
  Ключи привязаны к конкретному рекламному аккаунту.
- **Формат запроса:** `application/x-www-form-urlencoded`
- **Параметры запроса (оригинальные имена):**
  | Поле | Тип | Обязательное | Описание |
  |------|-----|-------------|----------|
  | `grant_type` | string | да | Строка `client_credentials` |
  | `client_id` | string | да | Client ID из кабинета |
  | `client_secret` | string | да | Client Secret из кабинета |
- **Формат ответа:** `application/json`
- **Поля ответа (оригинальные имена):**
  | Поле | Тип | Описание |
  |------|-----|----------|
  | `access_token` | string | Ключ для авторизации запросов |
  | `expires_in` | number (секунды) | Срок жизни токена. По умолчанию `86400` (**24 часа**) |
  | `token_type` | string | Тип ключа — `Bearer` |
- **TTL токена / частота обновления:** 24 часа. Обновлять заранее, повторным запросом к `/token`.
- **Использование:** во всех запросах к `/ads/...` — заголовок `Authorization: Bearer <access_token>`.

> Примечание: у Авито есть второй flow — `authorization_code` (для доступа к данным **других**
> пользователей через зарегистрированное приложение, с `refresh_token`, TTL refresh — 1 год).
> Для нашего проекта (свой кабинет) он **не используется** — работаем по `client_credentials`.

---

## 2. Методы получения статистики

Все три метода — **синхронные**, `POST`, тело `application/json`, ответ JSON.
Общие правила:
- `dateFrom` / `dateTo` — формат `YYYY-MM-DD`. **Максимальный период — 100 дней.**
- Гранулярность: массив `data[]` — по дням (с полем `timestamp`); объект `totalData` — агрегат за период (без `timestamp`).
- Перед вызовом нужны ID сущностей — их дают справочные list-методы (см. §2-bis).

### Общий набор полей статистики — `StatsData`

Одинаков во всех трёх методах (в `data[]` и `totalData`):

| Поле | Тип | Описание |
|------|-----|----------|
| `timestamp` | string (date-time, ISO 8601) | Метка дня (`2025-01-01T00:00:00Z`). Только в `data[]`, в `totalData` отсутствует. |
| `views` | integer | Количество показов |
| `clicks` | integer | Количество кликов |
| `ctr` | number | CTR (Click-Through Rate) |
| `spend` | integer | Потрачено денег, в рублях |
| `spendBonus` | integer | Потрачено бонусов, в рублях |
| `cpm` | number | Средняя стоимость CPM |
| `cpc` | number | Средняя стоимость CPC |
| `videoViews25` | integer | Просмотров видео на 25% (видео-кампании) |
| `videoViews50` | integer | Просмотров видео на 50% (видео-кампании) |
| `videoViews75` | integer | Просмотров видео на 75% (видео-кампании) |
| `videoViews100` | integer | Просмотров видео на 100% (видео-кампании) |
| `q25` | number | Доля просмотров на 25% (видео-кампании) |
| `q50` | number | Доля просмотров на 50% (видео-кампании) |
| `q75` | number | Доля просмотров на 75% (видео-кампании) |
| `vtr` | number | View-Through Rate, доля просмотров на 100% (видео-кампании) |

---

### Метод: `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/stats`
- **Название в доках:** Получить статистику по кампании
- **Назначение:** агрегированная статистика по кампании за период + сводка по её группам и креативам.
- **Тип:** синхронный, JSON. **Стоимость (x-cost): 10 баллов.**
- **Path-параметры:** `accountID` (integer), `campaignID` (integer).
- **Параметры запроса (тело):**
  | Поле | Тип | Обязательное | Описание |
  |------|-----|-------------|----------|
  | `dateFrom` | string (YYYY-MM-DD) | да | Начало периода |
  | `dateTo` | string (YYYY-MM-DD) | да | Конец периода (≤ 100 дней от `dateFrom`) |
- **Формат ответа:** `application/json`
- **Структура ответа (200):**
  | Поле | Тип | Описание |
  |------|-----|----------|
  | `campaign` | object | Статистика кампании |
  | `campaign.id` | integer | ID кампании |
  | `campaign.name` | string | Название кампании |
  | `campaign.paymentModel` | string enum `CPM`/`CPC` | Модель оплаты |
  | `campaign.campaignType` | string enum `textImage`/`HTML`/`video` | Тип кампании |
  | `campaign.data` | array[StatsData] | По дням |
  | `campaign.totalData` | StatsData | Агрегат за период |
  | `groups` | array[object] | Сводка по группам: `id`, `name`, `data[]`, `totalData` |
  | `creatives` | array[object] | Сводка по креативам: `id`, `groupId`, `name`, `data[]`, `totalData` |

### Метод: `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/groups/stats`
- **Название в доках:** Получить статистику по группам кампании
- **Назначение:** статистика по конкретным группам внутри кампании.
- **Тип:** синхронный, JSON. **Стоимость (x-cost): 5 баллов.**
- **Параметры запроса (тело):**
  | Поле | Тип | Обязательное | Описание |
  |------|-----|-------------|----------|
  | `dateFrom` | string (YYYY-MM-DD) | да | Начало периода |
  | `dateTo` | string (YYYY-MM-DD) | да | Конец периода (≤ 100 дней) |
  | `groupIDs` | array[integer] | да (минимум 1) | ID групп |
- **Структура ответа (200):** `groups` — array[object] с полями `id`, `name`, `data[]` (StatsData по дням), `totalData` (StatsData).

### Метод: `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/creatives/stats`
- **Название в доках:** Получить статистику по креативам кампании
- **Назначение:** статистика по конкретным креативам кампании.
- **Тип:** синхронный, JSON. **Стоимость (x-cost): 1 балл.**
- **Параметры запроса (тело):**
  | Поле | Тип | Обязательное | Описание |
  |------|-----|-------------|----------|
  | `dateFrom` | string (YYYY-MM-DD) | да | Начало периода |
  | `dateTo` | string (YYYY-MM-DD) | да | Конец периода (≤ 100 дней) |
  | `creativeIDs` | array[integer] | да (минимум 1) | ID креативов |
- **Структура ответа (200):** `creatives` — array[object] с полями `id`, `groupId`, `name`, `data[]` (StatsData по дням), `totalData` (StatsData).

---

## 2-bis. Справочные (read-only) методы — необходимы для статистики

Статистические методы требуют на входе `campaignID`, `groupIDs`, `creativeIDs`.
Получить эти ID можно только из list-методов ниже — поэтому они включены в сводку
(это **read-only справочники**, а не управление кампаниями).

**Единый формат list-запроса** (для campaigns/groups/creatives):
```json
{ "filter": { /* фильтры сущности, можно {} */ }, "limit": 20, "page": 1 }
```
`limit` — 1..100 (по умолчанию 20), `page` — ≥1. В ответе всегда есть `total` (всего записей по фильтру).
Перебор страниц — пока массив не опустеет или `page * limit ≥ total`.

### Метод: `POST /ads/v1/account/{accountID}/campaigns` — список кампаний (x-cost: 1)
Фильтры: `ids`, `paymentModels`, `campaignTypes`, `statuses`, `managers`, `advertisers`,
`contractIDs`, `additionalAgreementIDs`, `createdAt{from,to}`, `timeFrame{from,to}`.
Ответ — `campaigns[]` + `total`. Поля элемента:
| Поле | Тип | Описание |
|------|-----|----------|
| `id` | integer | ID кампании |
| `name` | string | Название |
| `status` | string enum | `draft`/`in_moderation`/`moderation_failed`/`partial_moderation`/`active`/`pausing`/`paused`/`unpausing`/`stopped`/`finished`/`archived` |
| `budget` | integer | Бюджет, ₽ с НДС |
| `paymentModel` | string enum | `CPM`/`CPC` |
| `campaignType` | string enum | `textImage`/`HTML`/`video` |
| `startDate` / `endDate` | string | Период размещения |
| `accountId` | integer | ID аккаунта |
| `advertiserId` | integer | ID рекламодателя |
| `contractId` | integer | ID договора |
| `additionalAgreementID` | integer | ID доп. соглашения |
| `performanceAdditionalAgreementID` | integer | ID доп. соглашения к исполнительскому договору |
| `managerID` | integer | ID менеджера (userID) |
| `userId` | integer | ID создателя кампании |
| `createdAt` / `updatedAt` | string (date-time) | Создание / обновление |

### Метод: `POST /ads/v1/account/{accountID}/groups` — список групп (x-cost: 1)
Фильтры: `ids`, `campaignIDs`, `statuses`, `paces`, `managers`, `advertisers`, `paymentModels`, `timeFrame{from,to}`.
Ответ — `groups[]` + `total`. Ключевые поля: `id`, `name`, `campaignID`, `accountID`, `advertiserID`,
`status` (enum со `will_launch_soon`/`will_stop_soon` дополнительно к статусам кампании), `campaignType`,
`paymentModel`, `budget`, `budgetFrequency` (`weekly`/`entirePeriod`), `price`, `priceControl` (`manual`/`auto`),
`pace` (`asap`/`even`), `audienceType` (`basic`/`ready`/`autotargeting`), `format`, `frequencyCount`,
`frequencyPeriod` (`no_limit`/`day`/`week`/`month`), `scheduleType` (`always`/`weekdays9To20`/`custom`),
`activitySchedule` (по дням недели, часы 0–23), `targeting*IDs` (возраст/пол/доход/интересы/локации/…),
`periodStartAt`/`periodEndAt`/`periodTimezone`, `haveCreative`, `actions`, `createdAt`/`updatedAt`, `userID`, `managerID`.

### Метод: `POST /ads/v1/account/{accountID}/creatives` — список креативов (x-cost: 1)
Фильтры: `ids`, `groupIDs`, `campaignIDs`, `paymentModels`, `campaignTypes`, `statuses`, `managers`, `advertisers`, `timeFrame{from,to}`.
Ответ — `creatives[]` + `total`. Ключевые поля: `id`, `name`, `groupID`, `campaignID`, `accountID`, `advertiserID`,
`campaignType`, `paymentModel`, `status` (enum c `ready_for_moderation`/`erir_registration`), `title`, `description`,
`buttonText`, `link`, `originUrl`, `previewUrl`, `landingID`, `legalInfo{ageRestriction,description,kktu,notes}`, `managerID`, `userID`.

### Метод: `GET /ads/v1/account/{accountID}` — реквизиты аккаунта (x-cost: 1)
Возвращает объект `account`: `inn`, `kpp`, `ogrn`, `shortName`, `longName`, `legalAddress`,
`actualAddress`, `contact{name,phone}`, `manager{name,email}` (nullable).
Используется для проверки токена (200 = ок; 401 = токен невалиден; 403 = токен для другого `accountID`).

### Метод: `GET /ads/v1/account/{accountID}/balance` — баланс аккаунта (x-cost: 1)
Поля ответа: `balance` (integer, ₽), `bonusBalance` (integer, ₽).

> **Про `accountID`:** токен жёстко привязан к аккаунту, в котором выпущены ключи.
> Отдельного метода «узнать свой accountID» в API нет — ID берётся из кабинета (URL/настройки)
> и задаётся как параметр конфигурации проекта.

---

## 3. Сводная таблица методов

| # | Endpoint | Назначение | Формат | Sync/Async | x-cost | Ключевые поля ответа |
|---|----------|------------|--------|-----------|-------:|---------------------|
| — | `POST /token` | Выпуск access-токена | form→JSON | sync | — | `access_token`, `expires_in`, `token_type` |
| 1 | `POST /ads/v1/account/{accountID}/campaigns` | Список кампаний (справочник) | JSON | sync | 1 | `campaigns[]`, `total` |
| 2 | `POST /ads/v1/account/{accountID}/groups` | Список групп (справочник) | JSON | sync | 1 | `groups[]`, `total` |
| 3 | `POST /ads/v1/account/{accountID}/creatives` | Список креативов (справочник) | JSON | sync | 1 | `creatives[]`, `total` |
| 4 | `GET /ads/v1/account/{accountID}` | Реквизиты аккаунта | JSON | sync | 1 | `account{…}` |
| 5 | `GET /ads/v1/account/{accountID}/balance` | Баланс аккаунта | JSON | sync | 1 | `balance`, `bonusBalance` |
| 6 | `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/stats` | Статистика кампании (+ группы/креативы) | JSON | sync | 10 | `campaign{data[],totalData}`, `groups[]`, `creatives[]` |
| 7 | `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/groups/stats` | Статистика по группам | JSON | sync | 5 | `groups[]` (`data[]`, `totalData`) |
| 8 | `POST /ads/v1/account/{accountID}/campaigns/{campaignID}/creatives/stats` | Статистика по креативам | JSON | sync | 1 | `creatives[]` (`data[]`, `totalData`) |

---

## 4. Общие соглашения и ошибки

- **Деньги:** все суммы — целые числа в рублях с НДС (`spend`, `spendBonus`, `budget`, `price`, `balance`, `bonusBalance`).
  Подтверждено живым ответом 2026-06-10: `spend` приходит как JSON integer (целые ₽, без копеек).
  ⚠️ Из-за целочисленного формата на входе возможны **незначительные расхождения со статистикой
  личного кабинета Авито** — там расходы показываются с двумя знаками после запятой.
  Это особенность источника, а не ошибка выгрузки; обязательно отражать в ТЗ.
- **Даты:** `YYYY-MM-DD`; `timestamp` в статистике — ISO 8601 c дневной гранулярностью.
- **Единая схема ошибки:** `{ "code": string, "message": string }`.
- **HTTP-коды:** `400` (невалидное тело / период >100 дней), `401` (нет/просрочен токен), `403` (токен не на этот `accountID`), `404` (сущность не найдена), `429` (лимит), `500`, `503`.

---

## 5. Что НЕ включено (явно)

В сводку сознательно не включены методы, не относящиеся к статистике/справочникам ТМ-аналитики:

- Управление группами: `POST …/group/{groupID}/change-budget`, `…/change-price` (изменение ставки/бюджета).
- Рекламодатели/договоры (ОРД): `create-advertiser`, `advertisers` (list), `create-contract`, `contracts` (list).
- Дочерние аккаунты и переводы: `children`, `children-with-balances`, `create-nonpayer-child-account`, `funds-transfer`, `bonus-transfer`.
- Управление пользователями: `users` (list), `add-user`, `set-user-role`, `delete-user`.
- Sandbox-создание аккаунта: `POST /ads/v1/account/{accountID}` (только песочница).
- Создание/редактирование кампаний, групп, креативов — **через API недоступно** (делается в веб-интерфейсе кабинета).
