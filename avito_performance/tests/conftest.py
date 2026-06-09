"""Фикстуры pytest для unit-тестов avito_performance.

Тесты не ходят в сеть и не читают .env — HTTP-слой и методы клиента мокаются.
"""

import sys
from pathlib import Path

import pytest

# avito_performance.py лежит на уровень выше (avito_performance/), а тесты — в tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _env_creds(monkeypatch):
    """Подставляет фиктивные креды, чтобы конструктор клиента не падал."""
    monkeypatch.setenv("CLIENT_ID", "test_id")
    monkeypatch.setenv("CLIENT_SECRET", "test_secret")
    monkeypatch.setenv("ACCOUNT_ID", "123456789")


@pytest.fixture
def sample_campaigns():
    """Список кампаний из list-метода. Содержит дубликат id (для проверки дедупликации)
    и оба формата дат (ISO-Z и Go-time)."""
    return [
        {
            "id": 297840407, "name": "camp_med", "status": "active", "budget": 1390800,
            "paymentModel": "CPM", "campaignType": "textImage",
            "startDate": "2026-06-05 15:47:00.692 +0000 UTC",      # Go-time c мс
            "endDate": "2026-06-19 20:00:00 +0000 UTC",            # Go-time
            "advertiserId": 574505283, "contractId": 786670188, "managerID": 313033278,
            "createdAt": "2026-06-05T15:54:49Z",                    # ISO-Z
            "updatedAt": "2026-06-19 20:00:00 +0000 UTC",
            "accountId": 123456789, "userId": 1,
        },
        {  # дубликат id — должен быть удалён, выживает первый ("camp_med")
            "id": 297840407, "name": "dup", "status": "paused", "budget": 1,
            "paymentModel": "CPC", "campaignType": "textImage",
            "startDate": "2026-06-05T00:00:00Z", "endDate": "2026-06-06T00:00:00Z",
            "advertiserId": 1, "contractId": 1, "managerID": 1,
            "createdAt": "2026-06-05T10:00:00Z", "updatedAt": "2026-06-05T10:00:00Z",
        },
        {
            "id": 563334516, "name": "camp_nat", "status": "finished", "budget": 274500,
            "paymentModel": "CPC", "campaignType": "textImage",
            "startDate": "2026-06-02T04:00:00Z", "endDate": "2026-06-29T20:59:00Z",
            "advertiserId": 574505283, "contractId": 786670188, "managerID": 410865360,
            "createdAt": "2026-06-01T17:17:39Z", "updatedAt": "2026-06-02T04:10:00Z",
        },
    ]


@pytest.fixture
def sample_groups():
    return [
        {"id": 10, "name": "g1", "campaignID": 100, "status": "active",
         "paymentModel": "CPC", "budget": 1000, "price": 90, "priceControl": "auto",
         "pace": "even", "audienceType": "basic", "format": "native",
         "frequencyCount": 0, "frequencyPeriod": "no_limit", "scheduleType": "custom",
         "periodStartAt": "2026-06-02T04:00:00Z", "periodEndAt": "2026-06-29T20:59:00Z",
         "advertiserID": 7, "managerID": 8,
         "createdAt": "2026-06-01T14:17:39Z", "updatedAt": "2026-06-02T04:10:00Z"},
    ]


@pytest.fixture
def sample_creatives():
    return [
        {"id": 1000, "name": "cr1", "groupID": 10, "campaignID": 100, "status": "active",
         "paymentModel": "CPC", "campaignType": "textImage", "title": "t", "description": "d",
         "link": "http://x", "previewUrl": "http://p", "advertiserID": 7, "managerID": 8},
        # buttonText/originUrl/landingID отсутствуют — должны стать None
    ]


@pytest.fixture
def stat_campaigns():
    """Минимальный список кампаний для stat-функций (1 кампания, без дублей)."""
    return [{"id": 100, "name": "c1", "paymentModel": "CPC", "campaignType": "textImage"}]


def _two_day_data():
    """Два дня StatsData: 2026 (НДС 22%) и 2025 (НДС 20%). spend подобран так,
    что costs_without_nds в обоих случаях = 1000.0."""
    return [
        {"timestamp": "2026-06-05T00:00:00+03:00", "views": 1000, "clicks": 50,
         "spend": 1220, "spendBonus": 0},                       # 1220/1.22 = 1000
        {"timestamp": "2025-06-05T00:00:00+03:00", "views": 2000, "clicks": 10,
         "spend": 1200, "spendBonus": 7},                       # 1200/1.20 = 1000
    ]


@pytest.fixture
def campaign_stats_resp():
    return {
        "campaign": {"id": 100, "name": "c1", "paymentModel": "CPC",
                     "campaignType": "textImage", "data": _two_day_data(),
                     "totalData": {"views": 3000}},
        "groups": [], "creatives": [],
    }


@pytest.fixture
def groups_stats_resp():
    return {"groups": [{"id": 10, "name": "g1", "data": _two_day_data(), "totalData": {}}]}


@pytest.fixture
def creatives_stats_resp():
    # в ответе stats поле группы называется groupId (строчная d)
    return {"creatives": [{"id": 1000, "groupId": 10, "name": "cr1",
                           "data": _two_day_data(), "totalData": {}}]}
