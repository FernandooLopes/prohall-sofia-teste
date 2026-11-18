import pytest

from app.frete import CepInvalido, normalizar_cep, zona_do_cep


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
