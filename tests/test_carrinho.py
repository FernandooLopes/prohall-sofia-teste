from decimal import Decimal

import pytest

from app.loja import Loja
from app.regras import ErroRegra

D = Decimal


def test_adicionar_soma_quantidades(loja, sessao):
    loja.adicionar_item(sessao, "cem", 2)
    loja.adicionar_item(sessao, "cem", 3)
    assert sessao.itens == {"cem": 5}


def test_limite_de_10_unidades_por_item(loja, sessao):
    loja.adicionar_item(sessao, "cem", 10)
    with pytest.raises(ErroRegra) as erro:
        loja.adicionar_item(sessao, "cem", 1)
    assert erro.value.codigo == "quantidade_maxima"
    assert erro.value.extra["maximo"] == 10
    assert sessao.itens == {"cem": 10}  # nada mudou
    with pytest.raises(ErroRegra):
        loja.definir_quantidade(sessao, "cem", 11)


def test_nao_deixa_passar_do_estoque(loja, sessao):
    # "promo" tem 5 unidades em estoque
    with pytest.raises(ErroRegra) as erro:
        loja.adicionar_item(sessao, "promo", 6)
    assert erro.value.codigo == "quantidade_maxima" and erro.value.extra["maximo"] == 5
    loja.adicionar_item(sessao, "promo", 5)
    with pytest.raises(ErroRegra):
        loja.adicionar_item(sessao, "promo", 1)
    assert sessao.itens == {"promo": 5}


def test_produto_sem_estoque(loja, sessao):
    with pytest.raises(ErroRegra) as erro:
        loja.adicionar_item(sessao, "esgotado", 1)
    assert erro.value.codigo == "sem_estoque"
    assert sessao.itens == {}


@pytest.mark.parametrize("quantidade", [0, -1, 1.5, "abc", "", None, True, "2,5"])
def test_quantidades_invalidas(loja, sessao, quantidade):
    with pytest.raises(ErroRegra) as erro:
        loja.adicionar_item(sessao, "cem", quantidade)
    assert erro.value.codigo == "quantidade_invalida"
    assert sessao.itens == {}


@pytest.mark.parametrize("quantidade", [2, "2", 2.0])
def test_quantidades_inteiras_em_formatos_diferentes(loja, sessao, quantidade):
    loja.adicionar_item(sessao, "cem", quantidade)
    assert sessao.itens == {"cem": 2}


def test_produto_inexistente(loja, sessao):
    with pytest.raises(ErroRegra) as erro:
        loja.adicionar_item(sessao, "produto-inventado", 1)
    assert erro.value.codigo == "produto_inexistente"


def test_alterar_e_remover(loja, sessao):
    loja.adicionar_item(sessao, "cem", 3)
    loja.definir_quantidade(sessao, "cem", 1)
    assert sessao.itens == {"cem": 1}
    loja.definir_quantidade(sessao, "cem", 0)  # zero remove o item
    assert sessao.itens == {}
    with pytest.raises(ErroRegra):
        loja.remover_item(sessao, "cem")


def test_cupom_precisa_do_minimo_e_so_vale_um_por_pedido(loja, sessao):
    loja.adicionar_item(sessao, "cem", 1)
    with pytest.raises(ErroRegra) as erro:
        loja.aplicar_cupom(sessao, "PROHALL10")
    assert erro.value.codigo == "cupom_minimo" and sessao.cupom is None
    loja.adicionar_item(sessao, "cem", 1)
    assert loja.aplicar_cupom(sessao, "prohall10") == "PROHALL10"
    with pytest.raises(ErroRegra) as erro:
        loja.aplicar_cupom(sessao, "PROHALL10")
    assert erro.value.codigo == "cupom_ja_aplicado"
    with pytest.raises(ErroRegra) as erro:
        loja.aplicar_cupom(sessao, "BLACKFRIDAY")
    assert erro.value.codigo == "cupom_invalido"
    assert loja.totais(sessao).desconto_cupom == D("20.00")  # desconto aplicado uma unica vez


def test_cupom_deixa_de_valer_se_o_subtotal_cair_abaixo_de_150(loja, sessao):
    loja.adicionar_item(sessao, "cem", 2)
    loja.aplicar_cupom(sessao, "PROHALL10")
    assert loja.totais(sessao).base == D("180.00")
    loja.definir_quantidade(sessao, "cem", 1)
    totais = loja.totais(sessao)
    assert not totais.cupom_aplicado
    assert totais.desconto_cupom == D("0.00") and totais.base == D("100.00")
    assert totais.falta_para_cupom == D("50.00")
    # voltando a atingir o minimo, o cupom registrado volta a valer
    loja.adicionar_item(sessao, "cinquenta", 1)
    assert loja.totais(sessao).desconto_cupom == D("15.00")


def test_cep_invalido_nao_e_gravado(loja, sessao):
    for cep in ["123", "00000-000", "abcdefgh"]:
        with pytest.raises(ErroRegra) as erro:
            loja.definir_cep(sessao, cep)
        assert erro.value.codigo == "cep_invalido"
    assert sessao.cep is None
    assert loja.definir_cep(sessao, "01310-100") == "01310100"


def test_modalidade_exige_cep_e_nome_valido(loja, sessao):
    with pytest.raises(ErroRegra) as erro:
        loja.escolher_modalidade(sessao, "economica")
    assert erro.value.codigo == "cep_ausente"
    loja.definir_cep(sessao, "01310100")
    with pytest.raises(ErroRegra) as erro:
        loja.escolher_modalidade(sessao, "sedex")
    assert erro.value.codigo == "modalidade_invalida"
    assert loja.escolher_modalidade(sessao, "Econômica") == "economica"
    assert loja.escolher_modalidade(sessao, "EXPRESSA") == "expressa"


def test_simulacao_nao_altera_o_carrinho(loja, sessao):
    loja.adicionar_item(sessao, "cem", 1)
    totais = loja.simular([{"produto_id": "promo", "quantidade": 2}], cep="01310-100", cupom=None)
    assert totais.subtotal == D("119.80")
    assert totais.cotacao.opcoes["economica"].valor == D("22.90")  # 1.000 g + 200 g
    assert sessao.itens == {"cem": 1} and sessao.cep is None
    with pytest.raises(ErroRegra):
        loja.simular([{"produto_id": "promo", "quantidade": 6}])  # acima do estoque
    with pytest.raises(ErroRegra):
        loja.simular([{"produto_id": "cem", "quantidade": 1}], cupom="FALSO")


def test_catalogo_real_respeita_estoque_baixo():
    loja = Loja(validade_pix_s=900)
    sessao = loja.nova_sessao()
    assert loja.estoque["gelatina-cachos-450g"] == 3
    with pytest.raises(ErroRegra) as erro:
        loja.adicionar_item(sessao, "gelatina-cachos-450g", 4)
    assert erro.value.extra["maximo"] == 3
