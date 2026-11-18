from app.catalogo import Catalogo
from app.loja import Loja
from app.prompts import INSTRUCOES, SAUDACAO, data_br, montar_instrucao


def test_instrucao_junta_regras_catalogo_e_estado(loja, sessao):
    loja.adicionar_item(sessao, "cem", 1)
    texto = montar_instrucao(loja, sessao)
    assert texto.index("Você é a Sofia") < texto.index("# CATÁLOGO") < texto.index("# ESTADO ATUAL")
    assert "## Produto cem  [id: cem]" in texto
    assert "- 1x Produto cem [id: cem]" in texto
    assert "{{VALIDADE_PIX}}" not in texto and "valem 15 minutos" in texto


def test_instrucao_e_remontada_com_o_estado_novo(loja, sessao):
    assert "Carrinho: vazio." in montar_instrucao(loja, sessao)
    loja.adicionar_item(sessao, "cem", 2)
    texto = montar_instrucao(loja, sessao)
    assert "Carrinho: vazio." not in texto and "2x Produto cem" in texto


def test_nota_de_correcao_vai_no_fim(loja, sessao):
    texto = montar_instrucao(loja, sessao, "# CORREÇÃO OBRIGATÓRIA\nrefaça")
    assert texto.endswith("# CORREÇÃO OBRIGATÓRIA\nrefaça")


def test_data_dos_precos_aparece_em_formato_brasileiro(catalogo):
    loja = Loja(catalogo=Catalogo(catalogo.listar(), "2026-11-16"))
    assert "preços copiados de lojaprohall.com.br em 16/11/2026" in montar_instrucao(loja, loja.nova_sessao())
    assert data_br("") == "" and data_br("sem-data") == "sem-data"


def test_regras_comerciais_do_prompt_batem_com_o_codigo():
    for trecho in ("PROHALL10", "R$ 150,00", "R$ 299,00", "R$ 399,00", "10 unidades", "5% de desconto"):
        assert trecho in INSTRUCOES
    assert "Sofia" in SAUDACAO
