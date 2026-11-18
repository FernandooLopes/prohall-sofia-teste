from decimal import Decimal

from app.dinheiro import D, arredondar, formatar


def test_float_nao_perde_precisao():
    assert D(0.1) + D(0.2) == Decimal("0.3")


def test_arredonda_meio_para_cima():
    assert arredondar("0.005") == Decimal("0.01")
    assert arredondar("2.675") == Decimal("2.68")
    assert arredondar("2.674") == Decimal("2.67")


def test_formata_em_reais():
    assert formatar(0) == "R$ 0,00"
    assert formatar(24.9) == "R$ 24,90"
    assert formatar("1234.5") == "R$ 1.234,50"
    assert formatar(1234567.891) == "R$ 1.234.567,89"


def test_formata_negativo():
    assert formatar(-15) == "-R$ 15,00"
