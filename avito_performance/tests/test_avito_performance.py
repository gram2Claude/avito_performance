"""Unit-тесты avito_performance (с моками, без сети и .env).

Запуск:  pytest avito_performance/tests/ -q
"""

import math

import pytest
import requests

import avito_performance as ap


# ── Вспомогательное ────────────────────────────────────────────────────────────

class FakeResp:
    def __init__(self, json_data=None, status=200, headers=None):
        self._json = json_data or {}
        self.status_code = status
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(str(self.status_code))
            err.response = self
            raise err


# ── Хелперы дат/НДС/метрик ──────────────────────────────────────────────────────

def test_normalize_iso_dt_z_no_shift():
    # 'Z' = UTC; не должно быть сдвига на локальный offset машины
    assert ap._normalize_iso_dt("2026-06-05T15:54:49Z") == "2026-06-05T15:54:49Z"


def test_normalize_iso_dt_offset_to_utc():
    assert ap._normalize_iso_dt("2026-06-05T15:54:49+03:00") == "2026-06-05T12:54:49Z"


@pytest.mark.parametrize("raw,expected", [
    ("2026-06-19 20:00:00 +0000 UTC", "2026-06-19T20:00:00Z"),
    ("2026-06-05 15:47:00.692 +0000 UTC", "2026-06-05T15:47:00Z"),
])
def test_normalize_iso_dt_go_format(raw, expected):
    assert ap._normalize_iso_dt(raw) == expected


def test_normalize_iso_dt_none():
    assert ap._normalize_iso_dt(None) is None
    assert ap._normalize_iso_dt("") is None


def test_day_from_timestamp_both_formats():
    assert ap._day_from_timestamp("2026-06-05T15:54:49Z") == "2026-06-05"
    assert ap._day_from_timestamp("2026-06-19 20:00:00 +0000 UTC") == "2026-06-19"
    assert ap._day_from_timestamp("2026-06-02T00:00:00+03:00") == "2026-06-02"


def test_vat_divisor_by_year():
    import pandas as pd
    s = pd.Series(["2024-12-31", "2025-06-01", "2026-01-01", "2027-03-03", None])
    div = list(ap._vat_divisor(s))
    assert div == [1.20, 1.20, 1.22, 1.22, 1.20]  # NaN → дефолт 20%


def test_pick_first_non_none():
    assert ap._pick({"a": None, "b": 5}, "a", "b") == 5
    assert ap._pick({"groupID": 3}, "groupId", "groupID") == 3
    assert ap._pick({}, "x", default="d") == "d"


@pytest.mark.parametrize("val,expected", [
    (None, None), (5, 5.0), (2.5, 2.5), ("1,5", 1.5), ("1 000", 1000.0), ("bad", None),
])
def test_parse_num(val, expected):
    assert ap._parse_num(val) == expected


def test_date_range_inclusive_and_reversed():
    assert ap._date_range("2026-05-01", "2026-05-03") == ["2026-05-01", "2026-05-02", "2026-05-03"]
    with pytest.raises(ValueError):
        ap._date_range("2026-05-03", "2026-05-01")


def test_metric_cols_mapping_and_excludes_removed():
    d = {"views": 1, "clicks": 2, "spendKopecs": 300, "spendBonusKopecs": 400, "vtr": 0.5,
         "ctr": 9, "cpm": 9, "cpc": 9, "q25": 9, "q50": 9, "q75": 9}
    m = ap._metric_cols(d)
    assert m["costs_nds"] == 3 and m["spend_bonus"] == 4 and m["impressions"] == 1
    assert m["video_views_25"] is None          # отсутствует в источнике → None
    for removed in ("ctr", "cpm", "cpc", "q25", "q50", "q75", "vtr"):
        assert removed not in m                  # удалённые метрики не извлекаются


def test_metric_cols_converts_kopecs_to_rubles():
    """Деньги приходят в копейках → в DataFrame рубли с копейками (десятичные).

    Падает, если из `_metric_cols` убрать деление на 100 или сделать его
    целочисленным (`//`) — дробная часть обязана дойти до колонки.
    """
    m = ap._metric_cols({"spendKopecs": 122045, "spendBonusKopecs": 55})
    assert m["costs_nds"] == pytest.approx(1220.45)
    assert m["spend_bonus"] == pytest.approx(0.55)
    assert isinstance(m["costs_nds"], float)


def test_metric_cols_ignores_legacy_rouble_spend_field():
    """Старое рублёвое поле `spend` больше не читается.

    Если бы оно продолжало подхватываться, рубли молча проехали бы как копейки
    (расход занижен в 100 раз). Пустое значение видно, тихо неверное — нет.
    """
    m = ap._metric_cols({"views": 1, "spend": 1220, "spendBonus": 7})
    assert m["costs_nds"] is None
    assert m["spend_bonus"] is None


def test_metric_cols_missing_money_keys_stay_none():
    """Отсутствующие денежные поля остаются None, а не превращаются в 0.0."""
    m = ap._metric_cols({"views": 5, "clicks": 1})
    assert m["costs_nds"] is None and m["spend_bonus"] is None


def test_apply_stat_enrichment_year_based_vat():
    import pandas as pd
    df = pd.DataFrame([
        {"date": "2026-06-05", "campaign_id": 100, "costs_nds": 1220},  # 22%
        {"date": "2025-06-05", "campaign_id": 100, "costs_nds": 1200},  # 20%
    ])
    out = ap._apply_stat_enrichment(df)
    assert out.loc[0, "costs_without_nds"] == pytest.approx(1000.0)
    assert out.loc[1, "costs_without_nds"] == pytest.approx(1000.0)
    assert out.loc[0, "costs_nds_ak"] == pytest.approx(1830.0)   # 1220 * 1.5
    assert (out["ak"] == 0.5).all()
    assert (out["account_id"] == 1).all() and (out["source_type_id"] == 9).all()
    assert list(out["id_key_camp"]) == ["1_100", "1_100"]


# ── Авторизация / HTTP ──────────────────────────────────────────────────────────

def test_refresh_token_uses_form_and_sets_bearer():
    client = ap.AvitoPerformanceClient()
    captured = {}

    def fake_post(url, data=None, json=None, timeout=None):
        captured.update(url=url, data=data, json=json)
        return FakeResp({"access_token": "TOK", "expires_in": 86400, "token_type": "Bearer"})

    client._session.post = fake_post
    client._refresh_token()
    assert client._token == "TOK"
    assert client._token_expires_at > 0
    assert captured["json"] is None                       # форма, не JSON
    assert captured["data"]["grant_type"] == "client_credentials"
    assert captured["url"].endswith("/token")


def test_request_retries_on_429_then_succeeds(monkeypatch):
    client = ap.AvitoPerformanceClient()
    client._token = "x"
    client._token_expires_at = math.inf                   # пропустить рефреш
    monkeypatch.setattr(ap.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_request(method, url, headers=None, timeout=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp(status=429, headers={"Retry-After": "0"})
        return FakeResp({"ok": True})

    client._session.request = fake_request
    assert client._get("/x") == {"ok": True}
    assert calls["n"] == 2


def test_request_raises_after_max_429(monkeypatch):
    client = ap.AvitoPerformanceClient()
    client._token = "x"
    client._token_expires_at = math.inf
    monkeypatch.setattr(ap.time, "sleep", lambda *_: None)
    client._session.request = lambda *a, **k: FakeResp(status=429, headers={"Retry-After": "0"})
    with pytest.raises(requests.HTTPError):
        client._get("/x")


def test_account_path():
    client = ap.AvitoPerformanceClient()
    assert client._account_path("/campaigns") == "/ads/v1/account/123456789/campaigns"


def test_constructor_requires_account(monkeypatch):
    monkeypatch.delenv("ACCOUNT_ID", raising=False)
    with pytest.raises(RuntimeError):
        ap.AvitoPerformanceClient(client_id="a", client_secret="b")


# ── Справочники ──────────────────────────────────────────────────────────────────

def test_get_campaign_dict(monkeypatch, sample_campaigns):
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, suffix, entity_key, filter_body=None: sample_campaigns)
    df = ap.get_campaign_dict()
    assert list(df.columns) == ap.CAMPAIGN_DICT_COLUMNS
    assert len(df) == 2                                   # дубликат id удалён
    row = df[df.campaign_id == 297840407].iloc[0]
    assert row.campaign_name == "camp_med"               # выжил первый
    assert row.campaign_type == "textImage"
    assert row.advertiser_id == 574505283 and row.contract_id == 786670188
    assert row.account_id == 1 and row.source_type_id == 9
    assert row.id_key_camp == "1_297840407"
    # поля удалены из справочника 2026-06-10
    assert not ({"status", "budget", "payment_model", "start_date",
                 "end_date", "created_at", "updated_at"} & set(df.columns))


def test_get_campaign_dict_empty(monkeypatch):
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, *a, **k: [])
    df = ap.get_campaign_dict()
    assert len(df) == 0
    assert list(df.columns) == ap.CAMPAIGN_DICT_COLUMNS


def test_get_group_dict(monkeypatch, sample_groups, stat_campaigns):
    # get_group_dict дополнительно зовёт get_campaign_dict (camp_type/camp_category/owner_id)
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, suffix, entity_key, filter_body=None:
                            stat_campaigns if suffix == "/campaigns" else sample_groups)
    df = ap.get_group_dict()
    assert list(df.columns) == ap.GROUP_DICT_COLUMNS
    row = df.iloc[0]
    assert row.group_id == 10 and row.campaign_id == 100
    assert row.status == "active" and row.payment_model == "CPC" and row.format == "native"
    assert row.camp_type == "camp_test" and row.camp_category == "cat_test"  # из справочника кампаний
    assert row.group_type == "other" and row.group_category == "other"       # дефолт
    assert row.owner_id == 1                                                 # из справочника кампаний
    assert row.id_key_camp == "1_100"
    assert row.id_key_group == "1_100_10"                # id_key_camp + "_" + group_id
    assert "id_key_ad" not in df.columns                 # у групп нет ad-level ключа
    # поля удалены из справочника 2026-06-10
    assert not ({"budget", "price", "price_control", "pace", "audience_type",
                 "frequency_count", "frequency_period", "schedule_type",
                 "period_start_at", "period_end_at", "have_creative",
                 "created_at", "updated_at"} & set(df.columns))


def test_get_creative_dict(monkeypatch, sample_creatives, sample_groups, stat_campaigns):
    # get_creative_dict зовёт get_group_dict (id_key_group/owner_id), тот — get_campaign_dict
    def fake_fetch(self, suffix, entity_key, filter_body=None):
        if suffix == "/campaigns":
            return stat_campaigns
        if suffix == "/groups":
            return sample_groups
        return sample_creatives
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages", fake_fetch)
    df = ap.get_creative_dict()
    assert list(df.columns) == ap.CREATIVE_DICT_COLUMNS
    row = df.iloc[0]
    assert row.creative_id == 1000 and row.group_id == 10 and row.campaign_id == 100
    assert row.id_key_group == "1_100_10"                # из справочника групп
    assert row.id_key_ad == "1_100_10_1000"              # id_key_group + "_" + creative_id
    assert row.owner_id == 1                             # из справочника групп
    assert row.button_text is None                       # отсутствует в API → None


# ── Статистика ───────────────────────────────────────────────────────────────────

def test_get_campaigns_daily_stat(monkeypatch, stat_campaigns, campaign_stats_resp):
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, suffix, entity_key, filter_body=None: stat_campaigns)
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_campaign_stats",
                        lambda self, cid, d_from, d_to: campaign_stats_resp)
    df = ap.get_campaigns_daily_stat("2025-06-05", "2026-06-05")
    assert list(df.columns) == ap.CAMPAIGNS_STAT_COLUMNS
    assert len(df) == 2                                   # два дня данных
    assert set(df["date"]) == {"2026-06-05", "2025-06-05"}
    # costs_nds ← spendKopecs/100 (122000 коп = 1220.00 ₽, 120000 коп = 1200.00 ₽)
    assert list(df["costs_nds"]) == [1220.0, 1200.0]
    assert df["costs_nds"].dtype == "float64"             # десятичный тип, 2 знака
    assert list(df["spend_bonus"]) == [0.0, 7.0]          # spendBonusKopecs/100
    # НДС по году: оба → 1000.0
    assert df["costs_without_nds"].round(2).tolist() == [1000.0, 1000.0]
    assert (df["id_key_camp"] == "1_100").all()
    for removed in ("ctr", "cpm", "cpc", "q25", "q50", "q75"):
        assert removed not in df.columns


def test_campaigns_stat_keeps_kopecs_precision(monkeypatch, stat_campaigns):
    """Сквозная проверка: дробная часть копеек доезжает до выходного DataFrame.

    Падает, если деление на 100 убрать (получим 122045.0) или сделать
    целочисленным (получим 1220.0 вместо 1220.45).
    """
    resp = {
        "campaign": {
            "id": 100, "paymentModel": "CPC", "campaignType": "textImage",
            "data": [{"timestamp": "2026-06-05T00:00:00+03:00", "views": 10, "clicks": 1,
                      "spendKopecs": 122045, "spendBonusKopecs": 55}],
        }
    }
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, suffix, entity_key, filter_body=None: stat_campaigns)
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_campaign_stats",
                        lambda self, cid, d_from, d_to: resp)
    df = ap.get_campaigns_daily_stat("2026-06-05", "2026-06-05")
    assert df.loc[0, "costs_nds"] == pytest.approx(1220.45)
    assert df.loc[0, "spend_bonus"] == pytest.approx(0.55)
    # производные считаются от рублёвой суммы, а не от копеечной
    assert df.loc[0, "costs_without_nds"] == pytest.approx(1220.45 / 1.22)
    assert df.loc[0, "costs_nds_ak"] == pytest.approx(1830.675)


def test_get_groups_daily_stat(monkeypatch, sample_groups, groups_stats_resp):
    def fake_pages(self, suffix, entity_key, filter_body=None):
        return sample_groups
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages", fake_pages)
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_groups_stats",
                        lambda self, cid, gids, d_from, d_to: groups_stats_resp)
    df = ap.get_groups_daily_stat("2025-06-05", "2026-06-05")
    assert list(df.columns) == ap.GROUPS_STAT_COLUMNS
    assert len(df) == 2
    assert (df["campaign_id"] == 100).all() and (df["group_id"] == 10).all()
    assert df["costs_without_nds"].round(2).tolist() == [1000.0, 1000.0]


def test_get_creatives_daily_stat(monkeypatch, sample_creatives, creatives_stats_resp):
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, suffix, entity_key, filter_body=None: sample_creatives)
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_creatives_stats",
                        lambda self, cid, crids, d_from, d_to: creatives_stats_resp)
    df = ap.get_creatives_daily_stat("2025-06-05", "2026-06-05")
    assert list(df.columns) == ap.CREATIVES_STAT_COLUMNS
    assert len(df) == 2
    assert (df["creative_id"] == 1000).all() and (df["group_id"] == 10).all()
    assert list(df["id_key_ad"].unique()) == ["1_100_10_1000"]   # id_key_group+"_"+creative_id; groupId (строчное) подхвачен


def test_stat_empty(monkeypatch, stat_campaigns):
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, *a, **k: stat_campaigns)
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_campaign_stats",
                        lambda self, *a, **k: {"campaign": {"data": []}})
    df = ap.get_campaigns_daily_stat("2026-06-05", "2026-06-05")
    assert len(df) == 0
    assert list(df.columns) == ap.CAMPAIGNS_STAT_COLUMNS


def test_get_admin_audit(monkeypatch, stat_campaigns, campaign_stats_resp):
    # агрегат поверх get_campaigns_daily_stat + owner_id из get_campaign_dict
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, suffix, entity_key, filter_body=None: stat_campaigns)
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_campaign_stats",
                        lambda self, cid, d_from, d_to: campaign_stats_resp)
    df = ap.get_admin_audit("2025-06-05", "2026-06-05")
    assert list(df.columns) == ap.ADMIN_AUDIT_COLUMNS
    assert len(df) == 2                                   # по строке на день
    by_date = df.set_index("date")
    assert by_date.loc["2026-06-05", "impressions"] == 1000
    assert by_date.loc["2025-06-05", "impressions"] == 2000
    assert by_date.loc["2026-06-05", "clicks"] == 50
    assert df["costs_without_nds"].round(2).tolist() == [1000.0, 1000.0]
    assert (df["account_id"] == 1).all() and (df["source_type_id"] == 9).all()
    assert (df["owner_id"] == 1).all()                    # из справочника кампаний
    assert (df["chef_flag"] == 1).all()                   # дефолт


def test_get_admin_audit_empty(monkeypatch, stat_campaigns):
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_fetch_all_pages",
                        lambda self, *a, **k: stat_campaigns)
    monkeypatch.setattr(ap.AvitoPerformanceClient, "_campaign_stats",
                        lambda self, *a, **k: {"campaign": {"data": []}})
    df = ap.get_admin_audit("2026-06-05", "2026-06-05")
    assert len(df) == 0
    assert list(df.columns) == ap.ADMIN_AUDIT_COLUMNS


@pytest.mark.parametrize("cols", ["CAMPAIGNS_STAT_COLUMNS", "GROUPS_STAT_COLUMNS", "CREATIVES_STAT_COLUMNS"])
def test_removed_metrics_absent_from_columns(cols):
    columns = getattr(ap, cols)
    assert not ({"ctr", "cpm", "cpc", "q25", "q50", "q75"} & set(columns))
