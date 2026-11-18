from app.apresentacao import (
    carrinho_para_ui,
    cartao_produto,
    estado_para_ui,
    mensagem_para_ui,
    pedido_para_modelo,
    pedido_para_ui,
    produto_para_modelo,
    totais_para_modelo,
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


# --- dados para o modelo ----------------------------------------------------

def test_produto_para_modelo_mostra_preco_cheio_so_na_promocao(loja, catalogo):
    promo = produto_para_modelo(loja, catalogo.obter("promo"))
    assert promo["preco"] == "R$ 59,90" and promo["preco_cheio"] == "R$ 80,00"
    assert "preco_cheio" not in produto_para_modelo(loja, catalogo.obter("cem"))


def test_totais_sem_cep(loja, sessao):
    loja.adicionar_item(sessao, "promo", 2)
    dados = totais_para_modelo(loja.totais(sessao))
    assert dados["frete"] == "não calculado (falta o CEP)"
    assert dados["total_no_pix_sem_frete"] == "R$ 113,81"
    assert dados["desconto_pix_5_por_cento"] == "-R$ 5,99"


def test_totais_com_cep_listam_as_duas_modalidades(loja, sessao):
    loja.adicionar_item(sessao, "promo", 2)
    loja.definir_cep(sessao, "01310100")
    dados = totais_para_modelo(loja.totais(sessao), sessao.cep)
    economica, expressa = dados["opcoes_de_frete"]
    assert economica["valor"] == "R$ 22,90"
    assert economica["total_no_pix_com_esta_modalidade"] == "R$ 136,71"
    assert expressa["total_no_pix_com_esta_modalidade"] == "R$ 149,71"
    assert dados["frete_gratis_na_economica"] == "faltam R$ 179,20 em produtos para atingir R$ 299,00"
    assert dados["frete_escolhido"].startswith("nenhum")


def test_totais_com_frete_gratis_escolhido(loja, sessao):
    loja.adicionar_item(sessao, "trezentos-dez", 1)
    loja.definir_cep(sessao, "01310100")
    loja.escolher_modalidade(sessao, "economica")
    dados = totais_para_modelo(loja.totais(sessao), sessao.cep)
    assert dados["frete_escolhido"]["valor"] == "GRÁTIS (R$ 0,00)"
    assert dados["frete_gratis_na_economica"] == "atingido"
    assert dados["total_no_pix"] == "R$ 294,50"


def test_cupom_sem_valer_e_explicado_ao_modelo(loja, sessao):
    loja.adicionar_item(sessao, "cem", 2)
    loja.aplicar_cupom(sessao, "PROHALL10")
    assert totais_para_modelo(loja.totais(sessao))["cupom"] == "PROHALL10 aplicado: -R$ 20,00"
    loja.definir_quantidade(sessao, "cem", 1)
    cupom = totais_para_modelo(loja.totais(sessao))["cupom"]
    assert "SEM VALER" in cupom and "faltam R$ 50,00" in cupom


def test_pedido_para_modelo(loja, sessao, cliente):
    loja.adicionar_item(sessao, "cem", 2)
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "economica")
    pedido = loja.criar_pedido(sessao, cliente)
    dados = pedido_para_modelo(pedido, loja.agora())
    assert dados["status"] == "aguardando pagamento"
    assert dados["itens"] == ["2x Produto cem (R$ 200,00)"]
    assert dados["pix_expira_em"] == "15 min 00 s"
    assert dados["frete"] == "Econômica: R$ 18,90, prazo de 3 a 5 dias úteis"
    assert dados["entrega"] == "Avenida Paulista, 1000 — CEP 01310-100"
