# Сущности и функции — Avito Performance

Заполняется после основной анкеты (`02_NEW_PROJECT_QUESTIONNAIRE.md`).
Один файл на проект. Скопируй блок функции нужное количество раз.

**Как заполнять:** в каждом пункте под строкой `Пример:` есть строка `Ответ:`.
Замени `<впиши сюда>` своим значением. Строку `Пример:` не трогай —
она остаётся как подсказка. В пункте `Fn2. Тип` поставь `[x]` напротив одного
варианта (только один тип на функцию).

**Важно про Fn5 (колонки):** перечисляй только поля, которые приходят **из API**
(например: `date, campaign_id, ad_id, ad_name, views, clicks, costs_nds`).
Стандартные константные и вычисляемые поля (`account_id`, `source_type_id`,
`id_key_camp`, `id_key_ad`, `costs_without_nds`, `ak`, `costs_nds_ak`,
`costs_without_nds_ak`, плюс справочные `product_id`, `product_name`,
`camp_type`, `camp_category`, `owner_id`) Claude **добавляет автоматически**
по соглашению проекта — их в Fn5 указывать не нужно. См. шаблон
`test/spec_templates/07_template_spec.md` → раздел «Обязательное обогащение DataFrame».

> **Примечание по API (см. `info/00_api_methods.md`):**
> Avito Реклама — синхронный JSON API. Охватных метрик (reach) нет → функций типа «Охват» нет.
> Статистические методы требуют ID сущностей, поэтому сначала идут справочники
> (`campaigns`/`groups`/`creatives`), затем статистика по дням на трёх уровнях.
> Порядок реализации в Шаге 4: справочники → статистика.

---

## Функции

### Функция 1

```
Fn1. Имя функции (snake_case):
     Пример:  get_campaign_dict, get_campaign_daily_stat
     Ответ:   get_campaign_dict
     → Плейсхолдер: {FUNCTION_1_NAME}

Fn2. Тип (поставь [x] напротив одного варианта):
     [x] Справочник  — уникальные сущности с атрибутами, без дат
     [ ] Статистика  — метрики по дням, date_from / date_to
     [ ] Охват       — кумулятивная метрика, global_start_date + date_from / date_to

Fn4. Описание одной строкой:
     Пример:  Дневная статистика по рекламным кампаниям
     Ответ:   Справочник рекламных кампаний аккаунта (POST /ads/v1/account/{accountID}/campaigns)
     → Плейсхолдер: {FN_1_ONELINER}

Fn5. Колонки выходного DataFrame (перечисли имена через запятую):
     Пример:  date, campaign_id, campaign_name, views, clicks, costs_nds
     Ответ:   campaign_id, campaign_name, status, budget, payment_model, campaign_type, start_date, end_date, advertiser_id, contract_id, manager_id, created_at, updated_at
     Правило: все имена колонок — snake_case.
     Типы данных определяются автоматически из ответа API.
     → Плейсхолдер: {DF_1_COLUMNS}
     Маппинг на API: campaign_id←id, campaign_name←name, payment_model←paymentModel,
       campaign_type←campaignType, start_date←startDate, end_date←endDate,
       advertiser_id←advertiserId, contract_id←contractId, manager_id←managerID,
       created_at←createdAt, updated_at←updatedAt. (accountId — константа, добавляется автоматически.)
```

---

### Функция 2

```
Fn1. Имя функции (snake_case):
     Пример:  get_campaign_dict, get_campaign_daily_stat
     Ответ:   get_group_dict
     → Плейсхолдер: {FUNCTION_2_NAME}

Fn2. Тип (поставь [x] напротив одного варианта):
     [x] Справочник  — уникальные сущности с атрибутами, без дат
     [ ] Статистика  — метрики по дням, date_from / date_to
     [ ] Охват       — кумулятивная метрика, global_start_date + date_from / date_to

Fn4. Описание одной строкой:
     Пример:  Дневная статистика по рекламным кампаниям
     Ответ:   Справочник групп объявлений аккаунта (POST /ads/v1/account/{accountID}/groups)
     → Плейсхолдер: {FN_2_ONELINER}

Fn5. Колонки выходного DataFrame (перечисли имена через запятую):
     Пример:  date, campaign_id, campaign_name, views, clicks, costs_nds
     Ответ:   group_id, group_name, campaign_id, status, payment_model, budget, price, price_control, pace, audience_type, format, frequency_count, frequency_period, schedule_type, period_start_at, period_end_at, have_creative, advertiser_id, manager_id, created_at, updated_at
     Правило: все имена колонок — snake_case.
     Типы данных определяются автоматически из ответа API.
     → Плейсхолдер: {DF_2_COLUMNS}
     Маппинг на API: group_id←id, group_name←name, campaign_id←campaignID,
       payment_model←paymentModel, price_control←priceControl,
       audience_type←audienceType, frequency_count←frequencyCount,
       frequency_period←frequencyPeriod, schedule_type←scheduleType,
       period_start_at←periodStartAt, period_end_at←periodEndAt,
       have_creative←haveCreative, advertiser_id←advertiserID, manager_id←managerID,
       created_at←createdAt, updated_at←updatedAt.
       (Массивы таргетинга targeting*IDs и activitySchedule в плоский DataFrame не выносим.)
```

---

### Функция 3

```
Fn1. Имя функции (snake_case):
     Пример:  get_campaign_dict, get_campaign_daily_stat
     Ответ:   get_creative_dict
     → Плейсхолдер: {FUNCTION_3_NAME}

Fn2. Тип (поставь [x] напротив одного варианта):
     [x] Справочник  — уникальные сущности с атрибутами, без дат
     [ ] Статистика  — метрики по дням, date_from / date_to
     [ ] Охват       — кумулятивная метрика, global_start_date + date_from / date_to

Fn4. Описание одной строкой:
     Пример:  Дневная статистика по рекламным кампаниям
     Ответ:   Справочник креативов аккаунта (POST /ads/v1/account/{accountID}/creatives)
     → Плейсхолдер: {FN_3_ONELINER}

Fn5. Колонки выходного DataFrame (перечисли имена через запятую):
     Пример:  date, campaign_id, campaign_name, views, clicks, costs_nds
     Ответ:   creative_id, creative_name, group_id, campaign_id, status, payment_model, campaign_type, title, description, button_text, link, origin_url, preview_url, landing_id, advertiser_id, manager_id
     Правило: все имена колонок — snake_case.
     Типы данных определяются автоматически из ответа API.
     → Плейсхолдер: {DF_3_COLUMNS}
     Маппинг на API: creative_id←id, creative_name←name, group_id←groupID,
       campaign_id←campaignID, payment_model←paymentModel, campaign_type←campaignType,
       button_text←buttonText, origin_url←originUrl, preview_url←previewUrl,
       landing_id←landingID, advertiser_id←advertiserID, manager_id←managerID.
```

---

### Функция 4

```
Fn1. Имя функции (snake_case):
     Пример:  get_campaign_dict, get_campaign_daily_stat
     Ответ:   get_campaigns_daily_stat
     → Плейсхолдер: {FUNCTION_4_NAME}

Fn2. Тип (поставь [x] напротив одного варианта):
     [ ] Справочник  — уникальные сущности с атрибутами, без дат
     [x] Статистика  — метрики по дням, date_from / date_to
     [ ] Охват       — кумулятивная метрика, global_start_date + date_from / date_to

Fn4. Описание одной строкой:
     Пример:  Дневная статистика по рекламным кампаниям
     Ответ:   Дневная статистика по кампаниям (POST /ads/v1/account/{accountID}/campaigns/{campaignID}/stats)
     → Плейсхолдер: {FN_4_ONELINER}

Fn5. Колонки выходного DataFrame (перечисли имена через запятую):
     Пример:  date, campaign_id, campaign_name, views, clicks, costs_nds
     Ответ:   date, campaign_id, campaign_name, payment_model, campaign_type, views, clicks, spend, spend_bonus, video_views_25, video_views_50, video_views_75, video_views_100, vtr
     Правило: все имена колонок — snake_case.
     Типы данных определяются автоматически из ответа API.
     → Плейсхолдер: {DF_4_COLUMNS}
     Маппинг на API: date←campaign.data[].timestamp (день), campaign_id←campaign.id,
       campaign_name←campaign.name, payment_model←campaign.paymentModel,
       campaign_type←campaign.campaignType; метрики из StatsData:
       spend_bonus←spendBonus, video_views_25←videoViews25 (…/50/75/100), остальные 1:1.
       Перебор кампаний — по списку из get_campaign_dict. Период ≤100 дней.
```

---

### Функция 5

```
Fn1. Имя функции (snake_case):
     Пример:  get_campaign_dict, get_campaign_daily_stat
     Ответ:   get_groups_daily_stat
     → Плейсхолдер: {FUNCTION_5_NAME}

Fn2. Тип (поставь [x] напротив одного варианта):
     [ ] Справочник  — уникальные сущности с атрибутами, без дат
     [x] Статистика  — метрики по дням, date_from / date_to
     [ ] Охват       — кумулятивная метрика, global_start_date + date_from / date_to

Fn4. Описание одной строкой:
     Пример:  Дневная статистика по рекламным кампаниям
     Ответ:   Дневная статистика по группам (POST /ads/v1/account/{accountID}/campaigns/{campaignID}/groups/stats)
     → Плейсхолдер: {FN_5_ONELINER}

Fn5. Колонки выходного DataFrame (перечисли имена через запятую):
     Пример:  date, campaign_id, campaign_name, views, clicks, costs_nds
     Ответ:   date, campaign_id, group_id, group_name, views, clicks, spend, spend_bonus, video_views_25, video_views_50, video_views_75, video_views_100, vtr
     Правило: все имена колонок — snake_case.
     Типы данных определяются автоматически из ответа API.
     → Плейсхолдер: {DF_5_COLUMNS}
     Маппинг на API: date←groups[].data[].timestamp, group_id←groups[].id,
       group_name←groups[].name, campaign_id←{campaignID} из пути; метрики — StatsData.
       Вход: groupIDs (минимум 1) — берутся из get_group_dict. Период ≤100 дней.
```

---

### Функция 6

```
Fn1. Имя функции (snake_case):
     Пример:  get_campaign_dict, get_campaign_daily_stat
     Ответ:   get_creatives_daily_stat
     → Плейсхолдер: {FUNCTION_6_NAME}

Fn2. Тип (поставь [x] напротив одного варианта):
     [ ] Справочник  — уникальные сущности с атрибутами, без дат
     [x] Статистика  — метрики по дням, date_from / date_to
     [ ] Охват       — кумулятивная метрика, global_start_date + date_from / date_to

Fn4. Описание одной строкой:
     Пример:  Дневная статистика по рекламным кампаниям
     Ответ:   Дневная статистика по креативам (POST /ads/v1/account/{accountID}/campaigns/{campaignID}/creatives/stats)
     → Плейсхолдер: {FN_6_ONELINER}

Fn5. Колонки выходного DataFrame (перечисли имена через запятую):
     Пример:  date, campaign_id, campaign_name, views, clicks, costs_nds
     Ответ:   date, campaign_id, group_id, creative_id, creative_name, views, clicks, spend, spend_bonus, video_views_25, video_views_50, video_views_75, video_views_100, vtr
     Правило: все имена колонок — snake_case.
     Типы данных определяются автоматически из ответа API.
     → Плейсхолдер: {DF_6_COLUMNS}
     Маппинг на API: date←creatives[].data[].timestamp, creative_id←creatives[].id,
       creative_name←creatives[].name, group_id←creatives[].groupId,
       campaign_id←{campaignID} из пути; метрики — StatsData.
       Вход: creativeIDs (минимум 1) — берутся из get_creative_dict. Период ≤100 дней.
```

---

### Функция 7

```
Fn1. Имя функции (snake_case):
     Пример:  get_campaign_dict, get_campaign_daily_stat
     Ответ:   get_admin_audit
     → Плейсхолдер: {FUNCTION_7_NAME}

Fn2. Тип (поставь [x] напротив одного варианта):
     [ ] Справочник  — уникальные сущности с атрибутами, без дат
     [x] Статистика  — метрики по дням, date_from / date_to
         (агрегатная таблица admin_audit поверх get_campaigns_daily_stat,
          собственного эндпоинта API нет)
     [ ] Охват       — кумулятивная метрика, global_start_date + date_from / date_to

Fn4. Описание одной строкой:
     Пример:  Дневная статистика по рекламным кампаниям
     Ответ:   Сводный аудит по дням (admin_audit): суммы impressions/clicks/costs_nds/costs_without_nds
     → Плейсхолдер: {FN_7_ONELINER}

Fn5. Колонки выходного DataFrame (перечисли имена через запятую):
     Пример:  date, campaign_id, campaign_name, views, clicks, costs_nds
     Ответ:   date, account_id, source_type_id, owner_id, impressions, clicks, costs_nds, costs_without_nds, chef_flag
     Правило: все имена колонок — snake_case.
     → Плейсхолдер: {DF_7_COLUMNS}
     Маппинг: собственного API-вызова нет — группировка результата get_campaigns_daily_stat
       по date × account_id × source_type_id × owner_id с суммированием
       impressions/clicks/costs_nds/costs_without_nds; owner_id — из справочника
       кампаний (join по campaign_id); chef_flag — константа 1 (дефолт).
```
