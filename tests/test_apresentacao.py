from app.apresentacao import (
    carrinho_para_ui,
    cartao_produto,
    estado_para_ui,
    mensagem_para_ui,
    pedido_para_ui,
)


def test_cartao_de_produto_em_promocao(loja, catalogo):
    cartao = cartao_produto(loja, catalogo.obter("promo"))
    assert cartao["em_promocao"] is True
    assert cartao["preco"] == "R$ 80,00" and cartao["preco_vigente"] == "R$ 59,90"
    assert cartao["estoque"] == 5 and cartao["maximo"] == 5


def test_cartao_limita_o_maximo_em_10(loja, catalogo):
    cartao = cartao_produto(loja, catalogo.obter("cem"))
    assert cartao["estoque"] == 50 and cartao["maximo"] == 10


def test_carrinho_vazio(loja, sessao):
    carrinho = carrinho_para_ui(loja, sessao)
    assert carrinho["vazio"] and carrinho["itens"] == []
    assert carrinho["frete"] is None and carrinho["cupom"] is None
    assert carrinho["total_pix"] == "R$ 0,00"


def test_carrinho_com_itens_e_frete(loja, sessao):
    loja.adicionar_item(sessao, "promo", 2)
    loja.definir_cep(sessao, "01310100")
    carrinho = carrinho_para_ui(loja, sessao)
    assert carrinho["quantidade_itens"] == 2
    assert carrinho["subtotal"] == "R$ 119,80"
    assert carrinho["cep"] == "01310-100"
    assert carrinho["frete"]["zona"] == "Z1"
    assert [o["valor"] for o in carrinho["frete"]["opcoes"]] == ["R$ 22,90", "R$ 35,90"]
    # sem modalidade escolhida o total ainda nao tem frete
    assert carrinho["total_completo"] is False and carrinho["total_pix"] == "R$ 113,81"

    loja.escolher_modalidade(sessao, "economica")
    carrinho = carrinho_para_ui(loja, sessao)
    assert carrinho["total_completo"] is True and carrinho["total_pix"] == "R$ 136,71"
    assert carrinho["frete"]["valor"] == "R$ 22,90"


def test_cupom_que_ainda_nao_vale_aparece_com_o_que_falta(loja, sessao):
    loja.adicionar_item(sessao, "cem", 2)
    loja.aplicar_cupom(sessao, "PROHALL10")
    loja.definir_quantidade(sessao, "cem", 1)
    cupom = carrinho_para_ui(loja, sessao)["cupom"]
    assert cupom["aplicado"] is False and cupom["falta"] == "R$ 50,00"


def test_pedido_e_estado(loja, sessao, cliente):
    assert estado_para_ui(loja, sessao)["pedido"] is None
    loja.adicionar_item(sessao, "cem", 2)
    loja.aplicar_cupom(sessao, "PROHALL10")
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "economica")
    pedido = loja.criar_pedido(sessao, cliente)

    dados = pedido_para_ui(pedido, loja.agora())
    assert dados["status_rotulo"] == "aguardando pagamento"
    assert dados["total"] == "R$ 189,90" and dados["segundos_restantes"] == 900
    assert dados["qr_code"].startswith("data:image/svg+xml")
    assert "qr_code" not in pedido_para_ui(pedido, loja.agora(), com_qr=False)

    estado = estado_para_ui(loja, sessao)
    assert estado["pedido"]["numero"] == pedido.numero
    assert estado["carrinho"]["vazio"] and estado["validade_pix_s"] == 900


def test_mensagem_ignora_produto_que_nao_existe(loja, sessao):
    mensagem = sessao.registrar("sofia", "olha esses", ["cem", "inventado"])
    dados = mensagem_para_ui(loja, mensagem)
    assert [p["id"] for p in dados["produtos"]] == ["cem"]
    assert dados["autor"] == "sofia"
