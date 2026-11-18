from app.apresentacao import exportar_conversa, texto_catalogo, texto_estado


def test_catalogo_traz_id_preco_e_estoque(loja):
    texto = texto_catalogo(loja)
    assert "## Produto promo  [id: promo]" in texto
    assert "- preço: de R$ 80,00 por R$ 59,90 (economia de R$ 20,10)" in texto
    assert "- preço: R$ 100,00" in texto
    assert "- estoque agora: 5 un. (máximo por pedido: 5)" in texto
    assert "- ativos citados na página: a página não cita" in texto


def test_catalogo_mostra_o_estoque_atual(loja, sessao, cliente):
    loja.adicionar_item(sessao, "promo", 2)
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "economica")
    loja.criar_pedido(sessao, cliente)
    assert "- estoque agora: 3 un. (máximo por pedido: 3)" in texto_catalogo(loja)


def test_estado_com_carrinho_vazio(loja, sessao):
    texto = texto_estado(loja, sessao)
    assert "Carrinho: vazio." in texto
    assert "Cupom disponível: PROHALL10" in texto
    assert "Pedidos desta conversa: nenhum ainda." in texto


def test_estado_diz_quanto_falta_para_o_cupom(loja, sessao):
    loja.adicionar_item(sessao, "cem", 1)
    texto = texto_estado(loja, sessao)
    assert "- 1x Produto cem [id: cem] — R$ 100,00 cada — R$ 100,00" in texto
    assert "Faltam R$ 50,00 no subtotal para poder usar." in texto
    loja.adicionar_item(sessao, "cem", 1)
    assert "já permite usar" in texto_estado(loja, sessao)


def test_estado_lista_o_frete_e_o_pedido(loja, sessao, cliente):
    loja.adicionar_item(sessao, "cem", 2)
    loja.definir_cep(sessao, cliente["cep"])
    texto = texto_estado(loja, sessao)
    assert "- frete Econômica: R$ 18,90, 3 a 5 dias úteis" in texto
    loja.escolher_modalidade(sessao, "economica")
    pedido = loja.criar_pedido(sessao, cliente)
    texto = texto_estado(loja, sessao)
    assert f"- {pedido.numero}: aguardando pagamento" in texto
    assert "PIX expira em 15 min 00 s" in texto
    assert "Maria Teste" in texto and "01310-100" in texto


def test_exportacao_da_conversa(loja, sessao, cliente):
    sessao.registrar("cliente", "oi")
    sessao.registrar("sofia", "Olá! Olha esse:", ["cem"])
    loja.adicionar_item(sessao, "cem", 1)
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "expressa")
    pedido = loja.criar_pedido(sessao, cliente)
    texto = exportar_conversa(loja, sessao)
    assert "Modelo: gemini-3.8-flash" in texto
    assert "Cliente:\noi" in texto and "Sofia:\nOlá! Olha esse:" in texto
    assert "[cards exibidos no chat: Produto cem (R$ 100,00)]" in texto
    assert f"- {pedido.numero} — aguardando pagamento — total" in texto
    assert texto.endswith("\n")
