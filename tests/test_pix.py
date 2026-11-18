import pytest

from app.loja import AGUARDANDO, EXPIRADO, PAGO
from app.regras import ErroRegra


def pedido_pronto(loja, sessao, cliente):
    loja.adicionar_item(sessao, "cem", 2)
    loja.aplicar_cupom(sessao, "PROHALL10")
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "economica")
    return loja.criar_pedido(sessao, cliente)


def test_pix_vale_15_minutos_e_depois_expira(loja, sessao, cliente, relogio):
    pedido = pedido_pronto(loja, sessao, cliente)
    assert (pedido.expira_em - pedido.criado_em).total_seconds() == 15 * 60
    relogio.avancar(minutes=14, seconds=59)
    assert loja.atualizar_pedidos(sessao) == []
    assert pedido.status == AGUARDANDO and pedido.segundos_restantes(relogio()) == 1
    relogio.avancar(seconds=1)
    assert loja.atualizar_pedidos(sessao) == [pedido]
    assert pedido.status == EXPIRADO and pedido.segundos_restantes(relogio()) == 0
    # a Sofia oferece um novo PIX, uma unica vez
    avisos = [m for m in sessao.mensagens if "expirou" in m["texto"]]
    assert len(avisos) == 1 and "novo PIX" in avisos[0]["texto"]
    assert loja.atualizar_pedidos(sessao) == []
    assert len([m for m in sessao.mensagens if "expirou" in m["texto"]]) == 1


def test_simular_pagamento_muda_para_pago_e_sofia_confirma(loja, sessao, cliente):
    pedido = pedido_pronto(loja, sessao, cliente)
    pago = loja.pagar_pedido(sessao, pedido.numero)
    assert pago.status == PAGO and pago.pago_em is not None
    confirmacoes = [m for m in sessao.mensagens if "Pagamento confirmado" in m["texto"]]
    assert len(confirmacoes) == 1
    assert pedido.numero in confirmacoes[0]["texto"] and "R$ 189,90" in confirmacoes[0]["texto"]
    # clicar de novo nao duplica a confirmacao
    loja.pagar_pedido(sessao, pedido.numero)
    assert len([m for m in sessao.mensagens if "Pagamento confirmado" in m["texto"]]) == 1


def test_nao_paga_pix_expirado(loja, sessao, cliente, relogio):
    pedido = pedido_pronto(loja, sessao, cliente)
    relogio.avancar(minutes=15)
    with pytest.raises(ErroRegra) as erro:
        loja.pagar_pedido(sessao, pedido.numero)
    assert erro.value.codigo == "pix_expirado"
    assert pedido.status == EXPIRADO


def test_pedido_pago_nao_expira(loja, sessao, cliente, relogio):
    pedido = pedido_pronto(loja, sessao, cliente)
    loja.pagar_pedido(sessao, pedido.numero)
    relogio.avancar(hours=2)
    loja.atualizar_pedidos(sessao)
    assert pedido.status == PAGO


def test_pedido_inexistente(loja, sessao):
    with pytest.raises(ErroRegra) as erro:
        loja.pagar_pedido(sessao, "PH-TESTE-999999")
    assert erro.value.codigo == "pedido_nao_encontrado"


def test_gerar_novo_pix_depois_de_expirar(loja, sessao, cliente, relogio):
    pedido = pedido_pronto(loja, sessao, cliente)
    with pytest.raises(ErroRegra) as erro:
        loja.gerar_novo_pix(sessao, pedido.numero)
    assert erro.value.codigo == "pix_ainda_valido"
    relogio.avancar(minutes=16)
    novo = loja.gerar_novo_pix(sessao)
    assert novo.numero == "PH-TESTE-000002" and novo.status == AGUARDANDO
    assert novo.total == pedido.total and novo.itens == pedido.itens
    assert novo.copia_e_cola == "PIX-TESTE|PROHALL|PH-TESTE-000002|189.90|NAO-PAGAVEL"
    assert pedido.status == EXPIRADO and pedido.substituido_por == novo.numero
    assert (novo.expira_em - relogio()).total_seconds() == 15 * 60
    with pytest.raises(ErroRegra):
        loja.gerar_novo_pix(sessao, pedido.numero)  # o expirado ja foi substituido
    assert loja.pagar_pedido(sessao, novo.numero).status == PAGO


def test_estoque_volta_quando_o_pix_expira(loja, cliente, relogio):
    sessao = loja.nova_sessao()
    loja.adicionar_item(sessao, "promo", 5)  # todo o estoque
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "economica")
    pedido = loja.criar_pedido(sessao, cliente)
    assert loja.estoque["promo"] == 0
    relogio.avancar(minutes=15)
    loja.atualizar_pedidos(sessao)
    assert pedido.status == EXPIRADO and loja.estoque["promo"] == 5
    loja.adicionar_item(loja.nova_sessao(), "promo", 1)


def test_estoque_continua_baixado_depois_de_pago(loja, sessao, cliente, relogio):
    loja.adicionar_item(sessao, "promo", 2)
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "economica")
    pedido = loja.criar_pedido(sessao, cliente)
    loja.pagar_pedido(sessao, pedido.numero)
    relogio.avancar(hours=1)
    loja.atualizar_pedidos(sessao)
    assert loja.estoque["promo"] == 3
