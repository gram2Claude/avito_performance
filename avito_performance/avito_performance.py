"""Avito Performance (Авито Реклама) API client.

Публичные функции, возвращающие pandas DataFrame:
- get_campaign_dict()                              — справочник рекламных кампаний аккаунта
- get_group_dict()                                 — справочник групп объявлений аккаунта
- get_creative_dict()                              — справочник креативов аккаунта
- get_campaigns_daily_stat(date_from, date_to)     — дневная статистика по кампаниям
- get_groups_daily_stat(date_from, date_to)        — дневная статистика по группам
- get_creatives_daily_stat(date_from, date_to)     — дневная статистика по креативам
- get_admin_audit(date_from, date_to)              — сводный аудит по дням (admin_audit,
                                                     агрегат поверх статистики кампаний)

Учётные данные читаются из переменных окружения CLIENT_ID и CLIENT_SECRET,
ID рекламного аккаунта — из ACCOUNT_ID (или передаются явно в AvitoPerformanceClient).

Авторизация — OAuth 2.0 grant_type=client_credentials (`POST /token`, Bearer-токен,
TTL 24 ч). API синхронный, формат JSON. Полный разбор методов — в info/00_api_methods.md.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import pandas as pd
import requests
from tqdm.auto import tqdm

# Перенастройка кодировки — обязательно на Windows (cp1251 по умолчанию).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

# ── Константы ─────────────────────────────────────────────────────────────────

BASE_URL = "https://api.avito.ru"        # prod. Sandbox: префикс /ads → /ads-sandbox
TOKEN_PATH = "/token"                    # POST, x-www-form-urlencoded, client_credentials
ADS_PREFIX = "/ads/v1"                   # все методы Авито Реклама

PAGE_LIMIT = 100                         # макс. размер страницы в list-методах (1..100)
PERIOD_MAX_DAYS = 100                    # макс. период между dateFrom и dateTo в статистике

HTTP_TIMEOUT_SEC = 30
RATE_LIMIT_RETRY_MAX = 5                 # максимум повторов при 429
RATE_LIMIT_BASE_SEC = 1                  # начальная пауза при 429 (удваивается: 1→2→4→8…)

TOKEN_TTL_SEC = 86400                    # 24 ч — дефолт, если API не вернёт expires_in
TOKEN_REFRESH_LEEWAY_SEC = 60           # обновлять токен за 60 сек до истечения

# ── Колонки итоговых DataFrame ────────────────────────────────────────────────
# Состав/порядок полей фиксируется здесь. API-поля взяты из manual_forms/03_ENTITY_FUNCTIONS.md.
# Константные/вычисляемые поля добавляются по соглашению «Обогащение DataFrame» (см. CLAUDE.md).
# Точный маппинг (особенно costs_nds ← spend и ставка НДС) подтверждается в spec каждой функции на Шаге 4.

CAMPAIGN_DICT_COLUMNS = [
    "campaign_id", "campaign_name", "campaign_type", "advertiser_id",
    "contract_id", "manager_id",
    # обогащение (соглашение проекта):
    "account_id", "source_type_id", "product_id", "product_name",
    "camp_type", "camp_category", "id_key_camp", "owner_id",
]

GROUP_DICT_COLUMNS = [
    "group_id", "group_name", "campaign_id", "status", "payment_model", "format",
    "advertiser_id", "manager_id",
    # обогащение (camp_type/camp_category/owner_id — из справочника кампаний):
    "account_id", "source_type_id", "camp_type", "camp_category",
    "group_type", "group_category", "id_key_camp", "id_key_group", "owner_id",
]

CREATIVE_DICT_COLUMNS = [
    "creative_id", "creative_name", "group_id", "campaign_id", "status",
    "payment_model", "campaign_type", "title", "description", "button_text",
    "link", "origin_url", "preview_url", "landing_id", "advertiser_id", "manager_id",
    # обогащение (ad-level → id_key_ad; id_key_group/owner_id — из справочника групп):
    "account_id", "source_type_id", "id_key_camp", "id_key_group", "id_key_ad", "owner_id",
]

# Метрики статистики (StatsData), общие для всех трёх stat-функций.
# Намеренно НЕ включаем ctr, cpm, cpc, q25, q50, q75 (исключены по требованию проекта).
_STAT_METRICS = [
    "impressions", "clicks", "costs_nds", "spend_bonus",
    "video_views_25", "video_views_50", "video_views_75", "video_views_100",
    "vtr",
]
# costs_nds ← API spend (целые ₽ с НДС); spend_bonus ← spendBonus. Подтвердить в Шаге 4.
_COST_ENRICHMENT = ["costs_without_nds", "ak", "costs_nds_ak", "costs_without_nds_ak"]

CAMPAIGNS_STAT_COLUMNS = (
    ["date", "campaign_id", "payment_model", "campaign_type"]
    + _STAT_METRICS + _COST_ENRICHMENT
    + ["account_id", "source_type_id", "id_key_camp"]
)

GROUPS_STAT_COLUMNS = (
    ["date", "campaign_id", "group_id"]
    + _STAT_METRICS + _COST_ENRICHMENT
    + ["account_id", "source_type_id", "id_key_camp"]
)

CREATIVES_STAT_COLUMNS = (
    ["date", "campaign_id", "group_id", "creative_id"]
    + _STAT_METRICS + _COST_ENRICHMENT
    + ["account_id", "source_type_id", "id_key_camp", "id_key_ad"]
)

# admin_audit — сводный аудит: агрегат поверх статистики кампаний (без своего эндпоинта)
ADMIN_AUDIT_COLUMNS = [
    "date", "account_id", "source_type_id", "owner_id",
    "impressions", "clicks", "costs_nds", "costs_without_nds",
    "chef_flag",
]


# ── Клиент ────────────────────────────────────────────────────────────────────

class AvitoPerformanceClient:
    """HTTP-клиент для Avito Performance (Авито Реклама) с автоматической авторизацией.

    Авторизация — OAuth 2.0 grant_type=client_credentials. Токен живёт ~24 ч;
    клиент сам запрашивает новый при истечении. Все запросы к /ads/* идут с
    заголовком Authorization: Bearer <token>.

    Токен и ключи привязаны к одному рекламному аккаунту (account_id) — он
    обязателен для построения путей /ads/v1/account/{accountID}/...
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        account_id: int | str | None = None,
    ) -> None:
        self._client_id = client_id or os.environ.get("CLIENT_ID")
        self._client_secret = client_secret or os.environ.get("CLIENT_SECRET")
        if not self._client_id or not self._client_secret:
            raise RuntimeError(
                "Учётные данные Avito Performance не предоставлены. "
                "Передайте client_id/client_secret или задайте CLIENT_ID и CLIENT_SECRET."
            )

        self._account_id = str(account_id or os.environ.get("ACCOUNT_ID") or "").strip()
        if not self._account_id:
            raise RuntimeError(
                "ID рекламного аккаунта не предоставлен. "
                "Передайте account_id или задайте ACCOUNT_ID (из кабинета Авито Реклама)."
            )

        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._session = requests.Session()

    @property
    def account_id(self) -> str:
        return self._account_id

    def _account_path(self, suffix: str = "") -> str:
        """Строит путь /ads/v1/account/{accountID}{suffix}."""
        return f"{ADS_PREFIX}/account/{self._account_id}{suffix}"

    # ── Авторизация ────────────────────────────────────────────────────────────

    def _refresh_token(self) -> None:
        # ВАЖНО: /token принимает x-www-form-urlencoded (data=), НЕ json=.
        url = f"{BASE_URL}{TOKEN_PATH}"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        resp = self._session.post(url, data=payload, timeout=HTTP_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", TOKEN_TTL_SEC))
        self._token_expires_at = time.time() + expires_in

    def _ensure_token(self) -> None:
        if self._token is None or time.time() >= self._token_expires_at - TOKEN_REFRESH_LEEWAY_SEC:
            self._refresh_token()

    def _headers(self) -> dict[str, str]:
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    # ── HTTP-обёртки ──────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Базовый запрос с обработкой 429 (экспоненциальный backoff)."""
        url = f"{BASE_URL}{path}"
        headers = self._headers()
        if method == "POST":
            headers = headers | {"Content-Type": "application/json"}
        wait = RATE_LIMIT_BASE_SEC
        for attempt in range(RATE_LIMIT_RETRY_MAX + 1):
            try:
                resp = self._session.request(
                    method, url, headers=headers, timeout=HTTP_TIMEOUT_SEC, **kwargs
                )
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    if attempt == RATE_LIMIT_RETRY_MAX:
                        raise
                    retry_after = int(exc.response.headers.get("Retry-After", wait))
                    logger.warning(
                        "429 Too Many Requests — ждём %d сек (попытка %d/%d)",
                        retry_after, attempt + 1, RATE_LIMIT_RETRY_MAX,
                    )
                    time.sleep(retry_after)
                    wait *= 2
                else:
                    raise

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("POST", path, json=body)

    # ── Статистика ─────────────────────────────────────────────────────────────

    def _campaign_stats(self, campaign_id: int, date_from: str, date_to: str) -> dict[str, Any]:
        """POST /campaigns/{campaignID}/stats — статистика кампании (+ группы/креативы)."""
        return self._post(
            self._account_path(f"/campaigns/{campaign_id}/stats"),
            {"dateFrom": date_from, "dateTo": date_to},
        )

    def _groups_stats(
        self, campaign_id: int, group_ids: list[int], date_from: str, date_to: str
    ) -> dict[str, Any]:
        """POST /campaigns/{campaignID}/groups/stats — статистика по группам кампании."""
        return self._post(
            self._account_path(f"/campaigns/{campaign_id}/groups/stats"),
            {"dateFrom": date_from, "dateTo": date_to, "groupIDs": group_ids},
        )

    def _creatives_stats(
        self, campaign_id: int, creative_ids: list[int], date_from: str, date_to: str
    ) -> dict[str, Any]:
        """POST /campaigns/{campaignID}/creatives/stats — статистика по креативам кампании."""
        return self._post(
            self._account_path(f"/campaigns/{campaign_id}/creatives/stats"),
            {"dateFrom": date_from, "dateTo": date_to, "creativeIDs": creative_ids},
        )

    # ── Пагинация list-методов (справочники) ──────────────────────────────────

    def _fetch_all_pages(
        self, suffix: str, entity_key: str, filter_body: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Постранично выгружает все записи list-метода.

        Тело запроса: {"filter": {...}, "limit": PAGE_LIMIT, "page": N}.
        Ответ: {"<entity_key>": [...], "total": int}. Идём по страницам, пока
        массив не опустеет (или page*limit >= total).

        Параметры:
            suffix      — хвост пути после /account/{accountID}, напр. "/campaigns"
            entity_key  — ключ массива в ответе: "campaigns" / "groups" / "creatives"
            filter_body — содержимое поля "filter" (по умолчанию {})
        """
        path = self._account_path(suffix)
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            body = {"filter": filter_body or {}, "limit": PAGE_LIMIT, "page": page}
            data = self._post(path, body)
            chunk = (data or {}).get(entity_key) or []
            results.extend(chunk)
            total = (data or {}).get("total")
            if not chunk or (isinstance(total, int) and page * PAGE_LIMIT >= total):
                break
            page += 1
        return results


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _date_range(date_from: str, date_to: str) -> list[str]:
    """Список дат от date_from до date_to включительно (YYYY-MM-DD)."""
    start = datetime.strptime(date_from, "%Y-%m-%d").date()
    end = datetime.strptime(date_to, "%Y-%m-%d").date()
    if end < start:
        raise ValueError(f"date_to ({date_to}) раньше date_from ({date_from})")
    days, cur = [], start
    while cur <= end:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def _chunks(seq: list, size: int) -> Iterable[list]:
    """Разбивает список на подсписки заданного размера."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _pick(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Возвращает значение первого найденного непустого ключа из словаря."""
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return default


def _day_from_timestamp(value: str | None) -> str | None:
    """Извлекает дату YYYY-MM-DD из таймстампа.

    Работает для обоих форматов Avito — оба начинаются с YYYY-MM-DD:
    ISO 8601 ('2026-06-05T15:54:49Z') и Go-time ('2026-06-19 20:00:00 +0000 UTC').
    """
    if not value or len(str(value)) < 10:
        return value
    return str(value)[:10]


def _normalize_iso_dt(value: Any) -> str | None:
    """Нормализует таймстамп Avito к ISO 8601 UTC: 'YYYY-MM-DDTHH:MM:SSZ'.

    API отдаёт даты в двух форматах:
      - ISO 8601:  '2026-06-05T15:54:49Z'
      - Go-time:   '2026-06-19 20:00:00 +0000 UTC' (иногда с миллисекундами)
    Оба — в UTC. Возвращает None для пустого значения, исходную строку — если формат не распознан.
    """
    if not value:
        return None
    s = str(value).strip()
    # ISO 8601 с 'Z' — это уже UTC; strptime даёт naive, поэтому НЕ применяем astimezone
    # (иначе naive ошибочно трактуется как локальное время и сдвигается на offset машины).
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass
    # ISO 8601 с явным смещением (+03:00 и т.п.) — приводим к UTC
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass
    # Go time.String(): "YYYY-MM-DD HH:MM:SS[.fff] +0000 UTC" — у Avito всегда +0000,
    # поэтому первые 19 символов = UTC-время как есть.
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return s


def _parse_num(value: Any) -> float | None:
    """Конвертирует число из ответа API в float. Avito отдаёт числа как числа."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except (ValueError, TypeError):
        return None


# Маппинг полей StatsData (API → колонка DataFrame). Видео-поля отсутствуют у
# не-видео кампаний → приходит None. costs_nds ← spend (целые ₽ с НДС).
# ctr/cpm/cpc/q25/q50/q75 из API не выгружаем (исключены по требованию проекта).
_STAT_METRIC_KEYS = [
    ("impressions", "views"), ("clicks", "clicks"),
    ("costs_nds", "spend"), ("spend_bonus", "spendBonus"),
    ("video_views_25", "videoViews25"), ("video_views_50", "videoViews50"),
    ("video_views_75", "videoViews75"), ("video_views_100", "videoViews100"),
    ("vtr", "vtr"),
]


def _metric_cols(data_item: dict[str, Any]) -> dict[str, Any]:
    """Достаёт метрики StatsData из одного элемента data[] по маппингу."""
    return {col: data_item.get(api) for col, api in _STAT_METRIC_KEYS}


def _vat_divisor(date_series: pd.Series) -> pd.Series:
    """Делитель НДС по году даты строки: год ≥ 2026 → 1.22 (22%), иначе 1.20 (20%).

    Avito отдаёт `spend` уже С НДС; чтобы получить сумму без НДС, делим на (1 + ставка).
    Ставка зависит от года, в котором понесён расход (берётся из колонки `date`).
    """
    year = pd.to_numeric(date_series.astype(str).str[:4], errors="coerce")
    div = pd.Series(1.20, index=date_series.index, dtype="float64")
    div[year >= 2026] = 1.22
    return div


def _apply_stat_enrichment(df: pd.DataFrame) -> pd.DataFrame:
    """Обогащение для статистики с расходами (соглашение проекта).

    НДС зависит от года даты строки: 2026+ → 22%, ранее → 20% (см. `_vat_divisor`).
    Агентская комиссия ak = 0.5.
    """
    # costs_nds — десятичный тип, округление до 2 знаков (API отдаёт целые ₽ с НДС)
    df["costs_nds"] = pd.to_numeric(df["costs_nds"], errors="coerce").astype(float).round(2)
    df["costs_without_nds"] = df["costs_nds"] / _vat_divisor(df["date"])
    df["ak"] = 0.5
    df["costs_nds_ak"] = df["costs_nds"] * (1 + 0.5)
    df["costs_without_nds_ak"] = df["costs_without_nds"] * (1 + 0.5)
    df["account_id"] = 1
    df["source_type_id"] = 9
    df["id_key_camp"] = "1_" + df["campaign_id"].astype(str)
    return df


# ── Публичные функции ─────────────────────────────────────────────────────────

def get_campaign_dict() -> pd.DataFrame:
    """Справочник рекламных кампаний аккаунта (POST /ads/v1/account/{accountID}/campaigns).

    Возвращает DataFrame с колонками: CAMPAIGN_DICT_COLUMNS.
    """
    client = AvitoPerformanceClient()
    entities = client._fetch_all_pages("/campaigns", "campaigns", filter_body={})
    if not entities:
        return pd.DataFrame(columns=CAMPAIGN_DICT_COLUMNS)

    df = pd.DataFrame([
        {
            "campaign_id": _pick(e, "id"),
            "campaign_name": _pick(e, "name"),
            "campaign_type": _pick(e, "campaignType"),
            "advertiser_id": _pick(e, "advertiserId"),
            "contract_id": _pick(e, "contractId"),
            "manager_id": _pick(e, "managerID"),   # внимание: в API заглавные ID
        }
        for e in entities
    ])
    df = df.dropna(subset=["campaign_id"]).drop_duplicates(subset=["campaign_id"])
    df["campaign_id"] = df["campaign_id"].astype("int64")

    # Обогащение DataFrame (соглашение проекта) — см. CLAUDE.md
    df["account_id"] = 1
    df["source_type_id"] = 9
    df["product_id"] = 1
    df["product_name"] = "prod_test"
    df["camp_type"] = "camp_test"
    df["camp_category"] = "cat_test"
    df["id_key_camp"] = "1_" + df["campaign_id"].astype(str)
    df["owner_id"] = 1

    return df.reindex(columns=CAMPAIGN_DICT_COLUMNS).reset_index(drop=True)


def get_group_dict() -> pd.DataFrame:
    """Справочник групп объявлений аккаунта (POST /ads/v1/account/{accountID}/groups).

    Возвращает DataFrame с колонками: GROUP_DICT_COLUMNS.
    """
    client = AvitoPerformanceClient()
    entities = client._fetch_all_pages("/groups", "groups", filter_body={})
    if not entities:
        return pd.DataFrame(columns=GROUP_DICT_COLUMNS)

    df = pd.DataFrame([
        {
            "group_id": _pick(e, "id"),
            "group_name": _pick(e, "name"),
            "campaign_id": _pick(e, "campaignID"),
            "status": _pick(e, "status"),
            "payment_model": _pick(e, "paymentModel"),
            "format": _pick(e, "format"),
            "advertiser_id": _pick(e, "advertiserID"),
            "manager_id": _pick(e, "managerID"),
        }
        for e in entities
    ])
    df = df.dropna(subset=["group_id"]).drop_duplicates(subset=["group_id"])
    df["group_id"] = df["group_id"].astype("int64")
    df["campaign_id"] = df["campaign_id"].astype("int64")

    df["account_id"] = 1
    df["source_type_id"] = 9
    # camp_type / camp_category / owner_id — из справочника кампаний (join по campaign_id)
    camps = get_campaign_dict()[["campaign_id", "camp_type", "camp_category", "owner_id"]]
    df = df.merge(camps, on="campaign_id", how="left")
    df["group_type"] = "other"
    df["group_category"] = "other"
    df["id_key_camp"] = "1_" + df["campaign_id"].astype(str)
    df["id_key_group"] = df["id_key_camp"] + "_" + df["group_id"].astype(str)

    return df.reindex(columns=GROUP_DICT_COLUMNS).reset_index(drop=True)


def get_creative_dict() -> pd.DataFrame:
    """Справочник креативов аккаунта (POST /ads/v1/account/{accountID}/creatives).

    Возвращает DataFrame с колонками: CREATIVE_DICT_COLUMNS.
    """
    client = AvitoPerformanceClient()
    entities = client._fetch_all_pages("/creatives", "creatives", filter_body={})
    if not entities:
        return pd.DataFrame(columns=CREATIVE_DICT_COLUMNS)

    df = pd.DataFrame([
        {
            "creative_id": _pick(e, "id"),
            "creative_name": _pick(e, "name"),
            "group_id": _pick(e, "groupID", "groupId"),
            "campaign_id": _pick(e, "campaignID"),
            "status": _pick(e, "status"),
            "payment_model": _pick(e, "paymentModel"),
            "campaign_type": _pick(e, "campaignType"),
            "title": _pick(e, "title"),
            "description": _pick(e, "description"),
            "button_text": _pick(e, "buttonText"),
            "link": _pick(e, "link"),
            "origin_url": _pick(e, "originUrl"),
            "preview_url": _pick(e, "previewUrl"),
            "landing_id": _pick(e, "landingID"),
            "advertiser_id": _pick(e, "advertiserID"),
            "manager_id": _pick(e, "managerID"),
        }
        for e in entities
    ])
    df = df.dropna(subset=["creative_id"]).drop_duplicates(subset=["creative_id"])
    df["creative_id"] = df["creative_id"].astype("int64")
    df["campaign_id"] = df["campaign_id"].astype("int64")

    df["account_id"] = 1
    df["source_type_id"] = 9
    # id_key_group / owner_id — из справочника групп (join по group_id)
    groups = get_group_dict()[["group_id", "id_key_group", "owner_id"]]
    df = df.merge(groups, on="group_id", how="left")
    df["id_key_camp"] = "1_" + df["campaign_id"].astype(str)
    df["id_key_ad"] = df["id_key_group"] + "_" + df["creative_id"].astype(str)

    return df.reindex(columns=CREATIVE_DICT_COLUMNS).reset_index(drop=True)


def get_campaigns_daily_stat(date_from: str, date_to: str) -> pd.DataFrame:
    """Дневная статистика по кампаниям.

    Эндпоинт: POST /ads/v1/account/{accountID}/campaigns/{campaignID}/stats
    Перебор кампаний — по списку из get_campaign_dict. Ответ разворачивается из
    campaign.data[] (по дням). Период [date_from, date_to] ≤ PERIOD_MAX_DAYS дней.

    Параметры:
        date_from — начало периода, YYYY-MM-DD
        date_to   — конец периода,  YYYY-MM-DD

    Возвращает DataFrame с колонками: CAMPAIGNS_STAT_COLUMNS.
    """
    client = AvitoPerformanceClient()
    campaigns = client._fetch_all_pages("/campaigns", "campaigns", filter_body={})

    rows: list[dict[str, Any]] = []
    for c in tqdm(campaigns, desc="Статистика по кампаниям", unit="камп"):
        cid = _pick(c, "id")
        if cid is None:
            continue
        resp = client._campaign_stats(cid, date_from, date_to)
        camp = (resp or {}).get("campaign") or {}
        for d in camp.get("data") or []:
            rows.append({
                "date": _day_from_timestamp(d.get("timestamp")),
                "campaign_id": cid,
                "payment_model": _pick(camp, "paymentModel") or _pick(c, "paymentModel"),
                "campaign_type": _pick(camp, "campaignType") or _pick(c, "campaignType"),
                **_metric_cols(d),
            })

    if not rows:
        return pd.DataFrame(columns=CAMPAIGNS_STAT_COLUMNS)
    df = pd.DataFrame(rows)
    df = _apply_stat_enrichment(df)
    return df.reindex(columns=CAMPAIGNS_STAT_COLUMNS).reset_index(drop=True)


def get_groups_daily_stat(date_from: str, date_to: str) -> pd.DataFrame:
    """Дневная статистика по группам.

    Эндпоинт: POST /ads/v1/account/{accountID}/campaigns/{campaignID}/groups/stats
    Вход groupIDs — из get_group_dict (сгруппированы по campaign_id). Ответ
    разворачивается из groups[].data[]. Период ≤ PERIOD_MAX_DAYS дней.

    Возвращает DataFrame с колонками: GROUPS_STAT_COLUMNS.
    """
    client = AvitoPerformanceClient()
    groups = client._fetch_all_pages("/groups", "groups", filter_body={})

    # Сгруппировать ID групп по кампании (stats-метод вызывается на уровне кампании)
    gids_by_camp: dict[int, list[int]] = {}
    for g in groups:
        gid, camp = _pick(g, "id"), _pick(g, "campaignID")
        if gid is None or camp is None:
            continue
        gids_by_camp.setdefault(camp, []).append(gid)

    rows: list[dict[str, Any]] = []
    for camp, gids in tqdm(gids_by_camp.items(), desc="Статистика по группам", unit="камп"):
        resp = client._groups_stats(camp, gids, date_from, date_to)
        for grp in (resp or {}).get("groups") or []:
            gid = _pick(grp, "id")
            for d in grp.get("data") or []:
                rows.append({
                    "date": _day_from_timestamp(d.get("timestamp")),
                    "campaign_id": camp,
                    "group_id": gid,
                    **_metric_cols(d),
                })

    if not rows:
        return pd.DataFrame(columns=GROUPS_STAT_COLUMNS)
    df = pd.DataFrame(rows)
    df = _apply_stat_enrichment(df)
    return df.reindex(columns=GROUPS_STAT_COLUMNS).reset_index(drop=True)


def get_creatives_daily_stat(date_from: str, date_to: str) -> pd.DataFrame:
    """Дневная статистика по креативам.

    Эндпоинт: POST /ads/v1/account/{accountID}/campaigns/{campaignID}/creatives/stats
    Вход creativeIDs — из get_creative_dict (сгруппированы по campaign_id). Ответ
    разворачивается из creatives[].data[]. Период ≤ PERIOD_MAX_DAYS дней.

    Возвращает DataFrame с колонками: CREATIVES_STAT_COLUMNS.
    """
    client = AvitoPerformanceClient()
    creatives = client._fetch_all_pages("/creatives", "creatives", filter_body={})

    # Сгруппировать ID креативов по кампании
    crids_by_camp: dict[int, list[int]] = {}
    for c in creatives:
        crid, camp = _pick(c, "id"), _pick(c, "campaignID")
        if crid is None or camp is None:
            continue
        crids_by_camp.setdefault(camp, []).append(crid)

    rows: list[dict[str, Any]] = []
    for camp, crids in tqdm(crids_by_camp.items(), desc="Статистика по креативам", unit="камп"):
        resp = client._creatives_stats(camp, crids, date_from, date_to)
        for cr in (resp or {}).get("creatives") or []:
            crid = _pick(cr, "id")
            for d in cr.get("data") or []:
                rows.append({
                    "date": _day_from_timestamp(d.get("timestamp")),
                    "campaign_id": camp,
                    "group_id": _pick(cr, "groupId", "groupID"),
                    "creative_id": crid,
                    **_metric_cols(d),
                })

    if not rows:
        return pd.DataFrame(columns=CREATIVES_STAT_COLUMNS)
    df = pd.DataFrame(rows)
    df = _apply_stat_enrichment(df)
    # id_key_ad = id_key_group + "_" + creative_id (id_key_group = id_key_camp + "_" + group_id)
    df["id_key_ad"] = (df["id_key_camp"] + "_" + df["group_id"].astype(str)
                       + "_" + df["creative_id"].astype(str))
    return df.reindex(columns=CREATIVES_STAT_COLUMNS).reset_index(drop=True)


def get_admin_audit(date_from: str, date_to: str) -> pd.DataFrame:
    """Сводный аудит (admin_audit): суммы метрик по дням.

    Собственного эндпоинта в API нет — агрегат поверх get_campaigns_daily_stat:
    impressions / clicks / costs_nds / costs_without_nds суммируются по
    date × account_id × source_type_id × owner_id (owner_id — из справочника
    кампаний, join по campaign_id). chef_flag = 1 (дефолт).

    Параметры:
        date_from — начало периода, YYYY-MM-DD
        date_to   — конец периода,  YYYY-MM-DD

    Возвращает DataFrame с колонками: ADMIN_AUDIT_COLUMNS.
    """
    stats = get_campaigns_daily_stat(date_from, date_to)
    if stats.empty:
        return pd.DataFrame(columns=ADMIN_AUDIT_COLUMNS)

    camps = get_campaign_dict()[["campaign_id", "owner_id"]]
    df = stats.merge(camps, on="campaign_id", how="left")
    df = (
        df.groupby(["date", "account_id", "source_type_id", "owner_id"], as_index=False)
          [["impressions", "clicks", "costs_nds", "costs_without_nds"]]
          .sum()
    )
    df["costs_nds"] = df["costs_nds"].round(2)  # десятичный тип, 2 знака после запятой
    df["chef_flag"] = 1
    return df.reindex(columns=ADMIN_AUDIT_COLUMNS).reset_index(drop=True)
