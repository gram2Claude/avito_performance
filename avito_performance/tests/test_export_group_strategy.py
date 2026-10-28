"""Тесты конвертации копеек в рубли для выгрузки стратегий.

Требование владельца: делим на 100, два знака, округление ПО ПРАВИЛАМ МАТЕМАТИКИ
(половина — вверх). Встроенный round() в Python округляет БАНКОВСКИ
(round(2.5) == 2), поэтому нужна отдельная реализация, и её надо закрепить тестом.
"""

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

EXPORT = Path(__file__).resolve().parent.parent / "exports" / "export_group_strategy.py"


def _load():
    """Грузим скрипт выгрузки как модуль, не выполняя его main-часть."""
    spec = importlib.util.spec_from_file_location("export_group_strategy", EXPORT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_group_strategy"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load()


def test_whole_kopeks_to_rubles(mod):
    """Целые копейки: 21500 коп = 215.00 ₽."""
    assert mod.kopeks_to_rubles(21500) == Decimal("215.00")
    assert mod.kopeks_to_rubles(25000) == Decimal("250.00")
    assert mod.kopeks_to_rubles(1) == Decimal("0.01")
    assert mod.kopeks_to_rubles(0) == Decimal("0.00")


def test_half_rounds_up_not_bankers(mod):
    """Половина округляется ВВЕРХ — это и отличает математическое от банковского.

    Входы подобраны ЗАМЕРОМ (28.10.2026), а не на глаз: встроенный round() на
    делении копеек расходится с half-up не всегда. 2.5 коп НЕ годится в контроль —
    0.025 в double чуть больше точного значения, и round() случайно уводит вверх
    (0.03, как и надо). Различают те входы, где x/100 представимо ТОЧНО и срабатывает
    банковское правило: 1.5 / 12.5 / 62.5 / 212.5 копейки.

    Мутация «вернуть round(float(x)/100, 2)» обязана валить именно этот тест.
    """
    assert mod.kopeks_to_rubles(Decimal("12.5")) == Decimal("0.13")   # round дал бы 0.12
    assert mod.kopeks_to_rubles(Decimal("1.5")) == Decimal("0.02")    # round дал бы 0.01
    assert mod.kopeks_to_rubles(Decimal("62.5")) == Decimal("0.63")   # round дал бы 0.62
    assert mod.kopeks_to_rubles(Decimal("212.5")) == Decimal("2.13")  # round дал бы 2.12
    assert mod.kopeks_to_rubles(Decimal("12345.5")) == Decimal("123.46")

    # Положительный контроль НА САМ КОНТРОЛЬ: убеждаемся, что эти входы реально
    # различают две стратегии округления, иначе ассерты выше ничего не проверяют.
    for kop, bankers in (("12.5", 0.12), ("1.5", 0.01), ("62.5", 0.62), ("212.5", 2.12)):
        assert round(float(kop) / 100, 2) == bankers
        assert mod.kopeks_to_rubles(Decimal(kop)) != Decimal(str(bankers))


def test_negative_half_rounds_away_from_zero(mod):
    """Отрицательные — тоже от нуля: -2.5 коп = -0.03 ₽."""
    assert mod.kopeks_to_rubles(Decimal("-2.5")) == Decimal("-0.03")


def test_missing_value_stays_none(mod):
    """Нет поля — None, а не 0.00: «не прислали» и «ноль» различаются."""
    assert mod.kopeks_to_rubles(None) is None
    assert mod.kopeks_to_rubles("") is None


def test_no_float_artifacts(mod):
    """Результат не несёт float-мусора вроде 0.30000000000000004."""
    assert str(mod.kopeks_to_rubles(30)) == "0.30"
    assert str(mod.kopeks_to_rubles(2000)) == "20.00"


def test_string_input_accepted(mod):
    """Если API отдаст число строкой — считаем так же, а не падаем."""
    assert mod.kopeks_to_rubles("21500") == Decimal("215.00")


def test_garbage_input_is_none(mod):
    """Нечисловое значение не превращается в 0.00 — это был бы тихий подлог."""
    assert mod.kopeks_to_rubles("не число") is None
