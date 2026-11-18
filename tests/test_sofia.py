import asyncio
import json

import httpx
import pytest

from app.gemini import ClienteGemini
from app.loja import AGUARDANDO, Loja
from app.sofia import RESPOSTA_FALHA, RESPOSTA_SEM_CHAVE, Sofia, valores_em_reais

CHAVE = "CHAVE-FALSA-DE-TESTE-123"


class GeminiFalso:
    # transporte httpx que devolve respostas roteirizadas e guarda as requisicoes recebidas
    def __init__(self, *roteiro):
        self.roteiro = list(roteiro)
        self.requisicoes = []

    def __call__(self, requisicao):
        self.requisicoes.append(requisicao)
        item = self.roteiro.pop(0)
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(
            200, json={"candidates": [{"content": {"role": "model", "parts": item}, "finishReason": "STOP"}]}
        )

    def corpo(self, indice):
        return json.loads(self.requisicoes[indice].content)


def texto(conteudo, assinatura="assinatura-final"):
    return [{"text": conteudo, "thoughtSignature": assinatura}]


def chamada(nome, args, assinatura="assinatura-da-chamada"):
    return [{"functionCall": {"name": nome, "args": args}, "thoughtSignature": assinatura}]


def montar(*roteiro, chave=CHAVE):
    falso = GeminiFalso(*roteiro)
    loja = Loja(validade_pix_s=900)
    gemini = ClienteGemini(chave=chave, transporte=httpx.MockTransport(falso), pausa_s=0)
    return falso, loja, Sofia(loja, gemini), loja.nova_sessao()


def conversar(sofia, sessao, mensagem):
    return asyncio.run(sofia.responder(sessao, mensagem))


def test_turno_simples_envia_chave_so_no_cabecalho():
    falso, _loja, sofia, sessao = montar(texto("Oi! Me conta do seu cabelo 😊"))
    resposta = conversar(sofia, sessao, "oi")
    assert resposta.texto == "Oi! Me conta do seu cabelo 😊" and not resposta.falhou
    requisicao = falso.requisicoes[0]
    assert requisicao.headers["x-goog-api-key"] == CHAVE
    assert CHAVE not in str(requisicao.url)
    assert CHAVE not in requisicao.content.decode()
    assert str(requisicao.url).endswith("/models/gemini-3.8-flash:generateContent")
    corpo = falso.corpo(0)
    instrucao = corpo["systemInstruction"]["parts"][0]["text"]
    assert "CATÁLOGO" in instrucao and "ESTADO ATUAL" in instrucao
    assert corpo["contents"] == [{"role": "user", "parts": [{"text": "oi"}]}]
    assert {f["name"] for f in corpo["tools"][0]["functionDeclarations"]} >= {"adicionar_ao_carrinho", "finalizar_pedido"}
    assert corpo["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"


def test_function_calling_executa_no_codigo_e_devolve_assinatura():
    falso, loja, sofia, sessao = montar(
        chamada("adicionar_ao_carrinho", {"produto_id": "tonico-force-hair-120ml", "quantidade": 2}, "ASSINATURA-1"),
        texto("Adicionei 2 tônicos! O subtotal ficou em R$ 49,80."),
    )
    resposta = conversar(sofia, sessao, "quero 2 tônicos")
    assert sessao.itens == {"tonico-force-hair-120ml": 2}
    assert resposta.texto == "Adicionei 2 tônicos! O subtotal ficou em R$ 49,80."
    # na 2a requisicao o historico traz a chamada do modelo intacta (com thoughtSignature) e o resultado
    conteudos = falso.corpo(1)["contents"]
    assert conteudos[1]["role"] == "model"
    assert conteudos[1]["parts"][0]["thoughtSignature"] == "ASSINATURA-1"
    retorno = conteudos[2]["parts"][0]["functionResponse"]
    assert conteudos[2]["role"] == "user" and retorno["name"] == "adicionar_ao_carrinho"
    assert retorno["response"]["ok"] is True
    assert retorno["response"]["carrinho"]["subtotal"] == "R$ 49,80"
    # o estado do prompt e remontado depois da ferramenta
    assert "2x Tônico Force Hair 120ml" in falso.corpo(1)["systemInstruction"]["parts"][0]["text"]


def test_cards_de_produto_vao_para_a_interface():
    _falso, _loja, sofia, sessao = montar(
        chamada("mostrar_produtos", {"produto_ids": ["gelatina-cachos-450g", "nao-existe", "kit-encorpax"]}),
        texto("Olha essas duas opções!"),
    )
    resposta = conversar(sofia, sessao, "tenho cachos")
    assert resposta.produtos == ["gelatina-cachos-450g", "kit-encorpax"]


def test_erro_de_regra_volta_para_o_modelo_sem_alterar_o_carrinho():
    falso, _loja, sofia, sessao = montar(
        chamada("adicionar_ao_carrinho", {"produto_id": "gelatina-cachos-450g", "quantidade": 9}),
        texto("Só temos 3 unidades da gelatina. Quer levar as 3?"),
    )
    conversar(sofia, sessao, "quero 9 gelatinas")
    assert sessao.itens == {}
    retorno = falso.corpo(1)["contents"][2]["parts"][0]["functionResponse"]["response"]
    assert retorno["ok"] is False and retorno["erro"] == "quantidade_maxima" and retorno["maximo"] == 3


def test_cupom_invalido_e_recusado_pelo_codigo():
    falso, _loja, sofia, sessao = montar(
        chamada("aplicar_cupom", {"codigo": "SOFIA50"}),
        texto("Esse cupom não é válido. O único cupom ativo é o PROHALL10."),
    )
    conversar(sofia, sessao, "aplica o cupom SOFIA50")
    retorno = falso.corpo(1)["contents"][2]["parts"][0]["functionResponse"]["response"]
    assert retorno["erro"] == "cupom_invalido" and sessao.cupom is None


def test_valor_inventado_descarta_a_resposta_e_pede_outra():
    falso, _loja, sofia, sessao = montar(
        texto("Levando dois, fica R$ 13,37 no total!"),
        texto("O tônico sai por R$ 24,90 cada."),
    )
    resposta = conversar(sofia, sessao, "quanto custa o tônico?")
    assert resposta.texto == "O tônico sai por R$ 24,90 cada."
    assert len(falso.requisicoes) == 2
    segunda = falso.corpo(1)
    assert "CORREÇÃO OBRIGATÓRIA" in segunda["systemInstruction"]["parts"][0]["text"]
    assert "13,37" not in json.dumps(segunda["contents"], ensure_ascii=False)  # a resposta descartada saiu do historico
    assert "13,37" not in json.dumps(sessao.historico, ensure_ascii=False)


def test_valores_do_catalogo_e_da_cliente_sao_aceitos():
    falso, _loja, sofia, sessao = montar(
        texto("Com R$ 100,00 dá para levar o shampoo de R$ 49,90 e sobra! Frete grátis a partir de R$ 299,00.")
    )
    resposta = conversar(sofia, sessao, "tenho 100 reais")
    assert "R$ 49,90" in resposta.texto and len(falso.requisicoes) == 1


def test_fechamento_pela_conversa_gera_o_mesmo_pedido_do_formulario():
    dados = {
        "nome": "Ana Teste", "email": "ana@exemplo.com", "cep": "01310-100",
        "endereco": "Av. Paulista", "numero": "1000", "complemento": "",
    }
    _falso, loja, sofia, sessao = montar(
        chamada("adicionar_ao_carrinho", {"produto_id": "kit-encorpax", "quantidade": 1}),
        chamada("calcular_frete", {"cep": "01310-100"}),
        chamada("escolher_frete", {"modalidade": "economica"}),
        chamada("finalizar_pedido", dados),
        texto("Pedido PH-TESTE-000001 gerado, no total de R$ 162,81!"),
    )
    resposta = conversar(sofia, sessao, "fecha o pedido")
    pedido = sessao.ultimo_pedido()
    assert resposta.pedido == pedido.numero == "PH-TESTE-000001"
    assert pedido.status == AGUARDANDO and str(pedido.total) == "162.81"  # 139,90 x 0,95 = 132,91 (132,905) + 29,90
    # o mesmo carrinho fechado pelo formulario, em outra loja
    outra = Loja(validade_pix_s=900)
    sessao_formulario = outra.nova_sessao()
    outra.adicionar_item(sessao_formulario, "kit-encorpax", 1)
    outra.definir_cep(sessao_formulario, "01310-100")
    outra.escolher_modalidade(sessao_formulario, "economica")
    pelo_formulario = outra.criar_pedido(sessao_formulario, dados, origem="formulario")
    assert (pelo_formulario.numero, pelo_formulario.total, pelo_formulario.itens, pelo_formulario.copia_e_cola) == (
        pedido.numero, pedido.total, pedido.itens, pedido.copia_e_cola,
    )


def test_falha_do_gemini_desfaz_o_turno_e_responde_com_mensagem_amigavel():
    erro = httpx.Response(500, json={"error": {"message": "internal"}})
    falso, _loja, sofia, sessao = montar(erro, erro, erro)
    resposta = conversar(sofia, sessao, "oi")
    assert resposta.falhou and resposta.texto == RESPOSTA_FALHA
    assert len(falso.requisicoes) == 3  # tentou de novo antes de desistir
    assert sessao.historico == []


def test_repete_em_erro_temporario():
    falso, _loja, sofia, sessao = montar(httpx.Response(429, json={"error": {"message": "quota"}}), texto("Oi!"))
    assert conversar(sofia, sessao, "oi").texto == "Oi!"
    assert len(falso.requisicoes) == 2


def test_se_o_modelo_recusar_o_thinking_level_segue_sem_ele():
    recusa = httpx.Response(400, json={"error": {"message": "Invalid value for thinking_level"}})
    falso, _loja, sofia, sessao = montar(recusa, texto("Oi!"))
    assert conversar(sofia, sessao, "oi").texto == "Oi!"
    assert "generationConfig" not in falso.corpo(1)


def test_sem_chave_nao_chama_a_api():
    falso, _loja, sofia, sessao = montar(chave="")
    resposta = conversar(sofia, sessao, "oi")
    assert resposta.falhou and resposta.texto == RESPOSTA_SEM_CHAVE
    assert falso.requisicoes == []


def test_erro_da_api_nunca_expoe_a_chave(caplog):
    negado = httpx.Response(403, json={"error": {"message": "API key not valid"}})
    _falso, _loja, sofia, sessao = montar(negado)
    resposta = conversar(sofia, sessao, "oi")
    assert CHAVE not in resposta.texto
    assert CHAVE not in caplog.text


@pytest.mark.parametrize(
    "frase, esperado",
    [
        ("sai por R$ 24,90", {"24.90"}),
        ("R$1.234,56 e R$ 299", {"1234.56", "299.00"}),
        ("de 74,90 por 24,90", {"74.90", "24.90"}),
        ("frete grátis (R$ 0,00)", {"0.00"}),
        ("3 a 5 dias úteis, 2 unidades, 500 ml", set()),
        ("total R$ 162.81.", {"162.81"}),
    ],
)
def test_extracao_de_valores_em_reais(frase, esperado):
    assert {str(v) for v in valores_em_reais(frase)} == esperado
