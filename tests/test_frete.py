from decimal import Decimal

import pytest

from app.frete import (
    TABELA,
    CepInvalido,
    calcular_frete,
    normalizar_cep,
    peso_cobrado_g,
    valor_tabela,
    zona_do_cep,
)

D = Decimal


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("01310-100", "01310100"),
        ("01310100", "01310100"),
        ("  37640-000 ", "37640000"),
        (1310100, None),  # número perde o zero à esquerda -> 7 dígitos -> inválido
    ],
)
def test_cep_aceita_com_ou_sem_hifen(entrada, esperado):
    if esperado is None:
        with pytest.raises(CepInvalido):
            normalizar_cep(entrada)
    else:
        assert normalizar_cep(entrada) == esperado


@pytest.mark.parametrize(
    "cep",
    ["", None, "1234567", "123456789", "0131-0100", "01310-10", "abcde-fgh", "01310 100", "01.310-100", "CEP 01310-100"],
)
def test_cep_com_formato_invalido(cep):
    with pytest.raises(CepInvalido):
        normalizar_cep(cep)


@pytest.mark.parametrize("cep", ["00000-000", "00999-999", "00500000"])
def test_cep_fora_das_faixas_e_invalido(cep):
    with pytest.raises(CepInvalido):
        zona_do_cep(cep)


@pytest.mark.parametrize(
    "cep, zona",
    [
        # Z1: SP e MG
        ("01000-000", "Z1"), ("19999-999", "Z1"), ("30000-000", "Z1"), ("39999-999", "Z1"),
        # Z2: RJ, ES, PR e SC
        ("20000-000", "Z2"), ("29999-999", "Z2"), ("80000-000", "Z2"), ("89999-999", "Z2"),
        # Z3: Centro-Oeste e RS
        ("70000-000", "Z3"), ("76799-999", "Z3"), ("78000-000", "Z3"), ("79999-999", "Z3"),
        ("90000-000", "Z3"), ("99999-999", "Z3"),
        # Z4: Nordeste
        ("40000-000", "Z4"), ("65999-999", "Z4"),
        # Z5: Norte
        ("66000-000", "Z5"), ("69999-999", "Z5"), ("76800-000", "Z5"), ("77999-999", "Z5"),
    ],
)
def test_zona_nos_limites_de_cada_faixa(cep, zona):
    assert zona_do_cep(cep) == zona


def test_mudanca_de_zona_em_ceps_vizinhos():
    assert zona_do_cep("19999999") == "Z1" and zona_do_cep("20000000") == "Z2"
    assert zona_do_cep("76799999") == "Z3" and zona_do_cep("76800000") == "Z5"
    assert zona_do_cep("65999999") == "Z4" and zona_do_cep("66000000") == "Z5"


# --- Peso ------------------------------------------------------------------

def test_peso_cobrado_soma_200g_de_embalagem():
    assert peso_cobrado_g(0) == 200
    assert peso_cobrado_g(190) == 390
    assert peso_cobrado_g(2 * 550 + 3 * 102) == 1606


@pytest.mark.parametrize(
    "peso_g, esperado",
    [
        (1, "15.90"), (500, "15.90"),      # ate 0,5 kg (limite inclusivo)
        (501, "18.90"), (1000, "18.90"),   # ate 1 kg (1.000 g ainda e "ate 1 kg")
        (1001, "22.90"), (2000, "22.90"),  # ate 2 kg
        (2001, "29.90"), (5000, "29.90"),  # ate 5 kg
    ],
)
def test_limites_inclusivos_das_faixas_de_peso(peso_g, esperado):
    assert valor_tabela("economica", "Z1", peso_g) == D(esperado)


@pytest.mark.parametrize(
    "peso_g, kg_adicionais",
    [(5001, 1), (5300, 1), (6000, 1), (6001, 2), (6300, 2), (7000, 2), (12000, 7)],
)
def test_adicional_acima_de_5kg_arredonda_para_cima(peso_g, kg_adicionais):
    # Z1 Economica: R$ 29,90 + R$ 3,50 por kg adicional
    assert valor_tabela("economica", "Z1", peso_g) == D("29.90") + D("3.50") * kg_adicionais
    # Z5 Expressa: R$ 129,90 + R$ 16,00 por kg adicional
    assert valor_tabela("expressa", "Z5", peso_g) == D("129.90") + D("16.00") * kg_adicionais


TABELA_ESPERADA = {
    # modalidade, zona: (ate 0,5 kg, ate 1 kg, ate 2 kg, ate 5 kg, adicional/kg, prazo)
    ("economica", "Z1"): ("15.90", "18.90", "22.90", "29.90", "3.50", (3, 5)),
    ("economica", "Z2"): ("19.90", "23.90", "28.90", "38.90", "4.50", (4, 7)),
    ("economica", "Z3"): ("24.90", "29.90", "36.90", "49.90", "6.00", (5, 9)),
    ("economica", "Z4"): ("29.90", "36.90", "45.90", "64.90", "8.00", (7, 12)),
    ("economica", "Z5"): ("34.90", "42.90", "54.90", "79.90", "10.00", (9, 15)),
    ("expressa", "Z1"): ("24.90", "29.90", "35.90", "47.90", "5.50", (1, 2)),
    ("expressa", "Z2"): ("31.90", "38.90", "46.90", "62.90", "7.00", (2, 3)),
    ("expressa", "Z3"): ("39.90", "48.90", "59.90", "82.90", "9.50", (2, 4)),
    ("expressa", "Z4"): ("49.90", "59.90", "74.90", "104.90", "13.00", (3, 6)),
    ("expressa", "Z5"): ("59.90", "72.90", "89.90", "129.90", "16.00", (4, 8)),
}


@pytest.mark.parametrize("chave", sorted(TABELA_ESPERADA))
def test_tabela_completa_de_valores_e_prazos(chave):
    modalidade, zona = chave
    f1, f2, f3, f4, adicional, prazo = TABELA_ESPERADA[chave]
    assert valor_tabela(modalidade, zona, 500) == D(f1)
    assert valor_tabela(modalidade, zona, 1000) == D(f2)
    assert valor_tabela(modalidade, zona, 2000) == D(f3)
    assert valor_tabela(modalidade, zona, 5000) == D(f4)
    assert valor_tabela(modalidade, zona, 5001) == D(f4) + D(adicional)
    assert TABELA[modalidade][zona][2] == prazo


# --- Cotacao completa --------------------------------------------------------

def test_cotacao_usa_peso_dos_itens_mais_embalagem():
    # 800 g de itens + 200 g = 1.000 g -> ainda "ate 1 kg"
    cotacao = calcular_frete("01310-100", 800, "100.00")
    assert cotacao.zona == "Z1"
    assert cotacao.peso_cobrado_g == 1000
    assert cotacao.opcoes["economica"].valor == D("18.90")
    assert cotacao.opcoes["expressa"].valor == D("29.90")
    # 801 g de itens + 200 g = 1.001 g -> "ate 2 kg"
    cotacao = calcular_frete("01310-100", 801, "100.00")
    assert cotacao.opcoes["economica"].valor == D("22.90")


def test_cotacao_traz_prazos_da_zona():
    cotacao = calcular_frete("69000-000", 300, "50.00")  # Manaus -> Z5
    economica, expressa = cotacao.opcoes["economica"], cotacao.opcoes["expressa"]
    assert (economica.prazo_min, economica.prazo_max) == (9, 15)
    assert (expressa.prazo_min, expressa.prazo_max) == (4, 8)
    assert economica.valor == D("34.90") and expressa.valor == D("59.90")


@pytest.mark.parametrize(
    "cep, base, gratis",
    [
        ("01310-100", "298.99", False),  # Z1 abaixo do minimo
        ("01310-100", "299.00", True),   # Z1 exatamente no minimo
        ("22041-001", "299.00", True),   # Z2
        ("80010-000", "350.00", True),   # Z2
        ("70040-010", "299.00", False),  # Z3 exige 399
        ("70040-010", "398.99", False),
        ("70040-010", "399.00", True),
        ("40020-000", "399.00", True),   # Z4
        ("69005-000", "398.99", False),  # Z5
        ("69005-000", "400.00", True),
    ],
)
def test_frete_gratis_so_na_economica_e_pelo_minimo_da_zona(cep, base, gratis):
    cotacao = calcular_frete(cep, 1500, base)
    economica, expressa = cotacao.opcoes["economica"], cotacao.opcoes["expressa"]
    assert economica.gratis is gratis
    if gratis:
        assert economica.valor == D("0.00")
        assert economica.valor_tabela > 0  # o valor de tabela continua disponivel para exibicao
        assert cotacao.falta_para_frete_gratis == D("0.00")
    else:
        assert economica.valor == economica.valor_tabela
        assert cotacao.falta_para_frete_gratis == cotacao.minimo_frete_gratis - D(base)
    # Expressa nunca e gratis
    assert expressa.gratis is False
    assert expressa.valor == expressa.valor_tabela > 0


def test_cotacao_com_cep_invalido_levanta_erro():
    with pytest.raises(CepInvalido):
        calcular_frete("123", 500, "100.00")
    with pytest.raises(CepInvalido):
        calcular_frete("00100-000", 500, "100.00")
