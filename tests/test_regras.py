from decimal import Decimal

import pytest

from app.catalogo import produto_de_dict
from app.regras import (
    ErroRegra,
    normalizar_modalidade,
    quantidade_inteira,
    quantidade_maxima,
    validar_cupom,
    validar_quantidade,
)

D = Decimal
PRODUTO = produto_de_dict(
    {"id": "p1", "nome": "Produto 1", "nome_curto": "Produto 1", "preco": 50, "peso_g": 200}
)


@pytest.mark.parametrize("valor, esperado", [(2, 2), ("2", 2), (2.0, 2), (" 3 ", 3), (0, 0)])
def test_quantidade_inteira_aceita(valor, esperado):
    assert quantidade_inteira(valor) == esperado


@pytest.mark.parametrize("valor", [1.5, "1,5", "dois", "", None, True, "nan", "inf"])
def test_quantidade_inteira_recusa(valor):
    with pytest.raises(ErroRegra) as erro:
        quantidade_inteira(valor)
    assert erro.value.codigo == "quantidade_invalida"


@pytest.mark.parametrize("estoque, maximo", [(0, 0), (3, 3), (10, 10), (50, 10), (-2, 0)])
def test_quantidade_maxima_e_o_menor_entre_estoque_e_10(estoque, maximo):
    assert quantidade_maxima(estoque) == maximo


def test_quantidade_dentro_do_limite_passa():
    validar_quantidade(PRODUTO, 1, 50)
    validar_quantidade(PRODUTO, 10, 50)
    validar_quantidade(PRODUTO, 3, 3)


def test_quantidade_zero_ou_negativa():
    for quantidade in (0, -1):
        with pytest.raises(ErroRegra) as erro:
            validar_quantidade(PRODUTO, quantidade, 50)
        assert erro.value.codigo == "quantidade_invalida"


def test_acima_de_10_unidades():
    with pytest.raises(ErroRegra) as erro:
        validar_quantidade(PRODUTO, 11, 50)
    assert erro.value.codigo == "quantidade_maxima"
    assert erro.value.extra["maximo"] == 10


def test_acima_do_estoque():
    with pytest.raises(ErroRegra) as erro:
        validar_quantidade(PRODUTO, 4, 3)
    assert erro.value.codigo == "quantidade_maxima"
    assert erro.value.extra["maximo"] == 3
    assert "3 unidade" in erro.value.mensagem


def test_sem_estoque():
    with pytest.raises(ErroRegra) as erro:
        validar_quantidade(PRODUTO, 1, 0)
    assert erro.value.codigo == "sem_estoque"


@pytest.mark.parametrize("codigo", ["PROHALL20", "PROHALL", "DESCONTO50", "", None, "PROHALL10X", "10"])
def test_qualquer_outro_cupom_e_invalido(codigo):
    with pytest.raises(ErroRegra) as erro:
        validar_cupom(codigo, D("500.00"))
    assert erro.value.codigo == "cupom_invalido"


@pytest.mark.parametrize("codigo", ["PROHALL10", "prohall10", "  ProHall10  "])
def test_cupom_aceita_maiusculas_minusculas_e_espacos(codigo):
    assert validar_cupom(codigo, D("150.00")) == "PROHALL10"


def test_cupom_exige_subtotal_de_150():
    with pytest.raises(ErroRegra) as erro:
        validar_cupom("PROHALL10", D("149.99"))
    assert erro.value.codigo == "cupom_minimo"
    assert erro.value.extra["falta"] == "R$ 0,01"


@pytest.mark.parametrize(
    "texto, esperado",
    [("econômica", "economica"), ("Economica", "economica"), ("expressa", "expressa"),
     ("EXPRESSO", "expressa"), ("sedex", None), ("", None), (None, None)],
)
def test_modalidade_normalizada(texto, esperado):
    assert normalizar_modalidade(texto) == esperado
