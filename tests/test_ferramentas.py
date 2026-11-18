from app.ferramentas import DECLARACOES, EXECUTORES, MAX_CARDS_POR_TURNO, EfeitosTurno, executar


def test_nomes_unicos_e_com_descricao():
    nomes = [d["name"] for d in DECLARACOES]
    assert len(nomes) == len(set(nomes)) == 14
    assert all(d["description"] for d in DECLARACOES)


def test_campos_obrigatorios_existem_nas_propriedades():
    for declaracao in DECLARACOES:
        parametros = declaracao.get("parameters")
        if parametros:
            assert set(parametros.get("required", [])) <= set(parametros["properties"]), declaracao["name"]


def rodar(loja, sessao, nome, args=None, efeitos=None):
    return executar(loja, sessao, nome, args or {}, efeitos or EfeitosTurno())


def test_executores_cobrem_todas_as_declaracoes():
    assert set(EXECUTORES) == {d["name"] for d in DECLARACOES}


def test_adicionar_devolve_o_carrinho_calculado(loja, sessao):
    resultado = rodar(loja, sessao, "adicionar_ao_carrinho", {"produto_id": "cem", "quantidade": 2})
    assert resultado["ok"] and sessao.itens == {"cem": 2}
    assert resultado["carrinho"]["subtotal"] == "R$ 200,00"


def test_erro_de_regra_volta_como_dict_com_o_carrinho(loja, sessao):
    loja.adicionar_item(sessao, "cem", 1)
    resultado = rodar(loja, sessao, "adicionar_ao_carrinho", {"produto_id": "esgotado", "quantidade": 1})
    assert resultado["ok"] is False and resultado["erro"] == "sem_estoque"
    assert resultado["carrinho"]["subtotal"] == "R$ 100,00"


def test_ferramenta_inexistente_e_args_invalidos(loja, sessao):
    assert rodar(loja, sessao, "apagar_tudo")["erro"] == "ferramenta_inexistente"
    resultado = executar(loja, sessao, "ver_carrinho", "texto solto", EfeitosTurno())
    assert resultado == {"ok": True, "carrinho": "vazio"}


def test_falha_inesperada_nao_derruba(loja, sessao, monkeypatch):
    def quebrado(*args):
        raise RuntimeError("bug")

    monkeypatch.setitem(EXECUTORES, "ver_carrinho", quebrado)
    assert rodar(loja, sessao, "ver_carrinho")["erro"] == "erro_interno"


def test_mostrar_produtos_registra_cards_sem_repetir_e_avisa_ids_falsos(loja, sessao):
    efeitos = EfeitosTurno()
    resultado = rodar(loja, sessao, "mostrar_produtos", {"produto_ids": ["cem", "cem", "inventado"]}, efeitos)
    assert efeitos.produtos == ["cem"]
    assert resultado["ids_inexistentes"] == ["inventado"]


def test_mostrar_produtos_limita_os_cards(loja, sessao, catalogo):
    efeitos = EfeitosTurno()
    rodar(loja, sessao, "mostrar_produtos", {"produto_ids": [p.id for p in catalogo.listar()]}, efeitos)
    assert len(efeitos.produtos) == MAX_CARDS_POR_TURNO


def test_simular_nao_mexe_no_carrinho(loja, sessao):
    resultado = rodar(
        loja, sessao, "simular_pedido",
        {"itens": [{"produto_id": "promo", "quantidade": 2}], "cep": "01310-100"},
    )
    assert resultado["simulacao"]["subtotal"] == "R$ 119,80"
    assert sessao.itens == {}


def test_frete_com_carrinho_vazio_so_guarda_o_cep(loja, sessao):
    resultado = rodar(loja, sessao, "calcular_frete", {"cep": "01310-100"})
    assert resultado["cep"] == "01310-100" and "carrinho está vazio" in resultado["aviso"]
    assert sessao.cep == "01310100"


def test_abrir_checkout_exige_carrinho(loja, sessao):
    assert rodar(loja, sessao, "abrir_checkout")["erro"] == "carrinho_vazio"
    loja.adicionar_item(sessao, "cem", 1)
    efeitos = EfeitosTurno()
    rodar(loja, sessao, "abrir_checkout", efeitos=efeitos)
    assert efeitos.abrir_checkout is True


def test_venda_completa_pelas_ferramentas(loja, sessao, cliente):
    efeitos = EfeitosTurno()
    rodar(loja, sessao, "adicionar_ao_carrinho", {"produto_id": "cem", "quantidade": 2}, efeitos)
    rodar(loja, sessao, "aplicar_cupom", {"codigo": "prohall10"}, efeitos)
    rodar(loja, sessao, "calcular_frete", {"cep": cliente["cep"]}, efeitos)
    rodar(loja, sessao, "escolher_frete", {"modalidade": "economica"}, efeitos)
    resultado = rodar(loja, sessao, "finalizar_pedido", cliente, efeitos)
    assert resultado["ok"] and resultado["pedido"]["total"] == "R$ 189,90"
    assert efeitos.pedido == "PH-TESTE-000001"
    consulta = rodar(loja, sessao, "consultar_pedido")
    assert consulta["pedido"]["numero"] == "PH-TESTE-000001"
    assert rodar(loja, sessao, "gerar_novo_pix")["erro"] == "pedido_nao_encontrado"  # nenhum expirado
    assert rodar(loja, sessao, "gerar_novo_pix", {"numero": "PH-TESTE-000001"})["erro"] == "pix_ainda_valido"
