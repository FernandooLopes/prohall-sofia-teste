import asyncio
import json

import httpx
import pytest

from app.gemini import ClienteGemini, ErroGemini

CHAVE = "chave-secreta-de-teste"
OK = {"candidates": [{"content": {"parts": [{"text": "Oi!", "thoughtSignature": "assinatura"}]}}]}


def cliente(respostas, **opcoes):
    """Cliente com transporte falso. `respostas` e uma lista de (status, json) usada em ordem."""
    chamadas = []

    def falso(requisicao):
        chamadas.append(requisicao)
        item = respostas[min(len(chamadas), len(respostas)) - 1]
        if isinstance(item, Exception):
            raise item
        status, corpo = item
        return httpx.Response(status, json=corpo)

    gemini = ClienteGemini(chave=CHAVE, transporte=httpx.MockTransport(falso), pausa_s=0, **opcoes)
    return gemini, chamadas


def gerar(gemini, ferramentas=None):
    return asyncio.run(gemini.gerar("instrucao", [{"role": "user", "parts": [{"text": "oi"}]}], ferramentas or []))


def test_sem_chave_nao_chama_a_api():
    gemini = ClienteGemini(chave="")
    assert not gemini.configurado
    with pytest.raises(ErroGemini):
        gerar(gemini)


def test_resposta_volta_intacta_com_a_assinatura():
    gemini, _ = cliente([(200, OK)])
    assert gerar(gemini) == {"role": "model", "parts": [{"text": "Oi!", "thoughtSignature": "assinatura"}]}


def test_chave_so_vai_no_cabecalho():
    gemini, chamadas = cliente([(200, OK)])
    gerar(gemini)
    requisicao = chamadas[0]
    assert requisicao.headers["x-goog-api-key"] == CHAVE
    assert CHAVE not in str(requisicao.url) and CHAVE.encode() not in requisicao.content
    assert "gemini-3.8-flash" in str(requisicao.url)


def test_corpo_leva_instrucao_ferramentas_e_raciocinio():
    gemini, chamadas = cliente([(200, OK)], nivel_raciocinio="medium")
    gerar(gemini, [{"name": "ver_carrinho", "description": "x"}])
    corpo = json.loads(chamadas[0].content)
    assert corpo["systemInstruction"]["parts"][0]["text"] == "instrucao"
    assert corpo["tools"][0]["functionDeclarations"][0]["name"] == "ver_carrinho"
    assert corpo["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "medium"


def test_erro_temporario_tenta_de_novo():
    gemini, chamadas = cliente([(429, {"error": {"message": "calma"}}), (503, {}), (200, OK)])
    assert gerar(gemini)["parts"][0]["text"] == "Oi!"
    assert len(chamadas) == 3


def test_desiste_depois_de_3_tentativas():
    gemini, chamadas = cliente([(503, {"error": {"message": "fora do ar"}})])
    with pytest.raises(ErroGemini) as erro:
        gerar(gemini)
    assert erro.value.status == 503 and len(chamadas) == 3


def test_erro_definitivo_nao_repete_e_nao_vaza_a_chave():
    gemini, chamadas = cliente([(403, {"error": {"message": "sem permissao"}})])
    with pytest.raises(ErroGemini) as erro:
        gerar(gemini)
    assert len(chamadas) == 1 and erro.value.status == 403
    assert CHAVE not in str(erro.value)


def test_falha_de_rede_vira_erro_gemini():
    gemini, chamadas = cliente([httpx.ConnectError("sem rede")])
    with pytest.raises(ErroGemini) as erro:
        gerar(gemini)
    assert "rede" in str(erro.value) and len(chamadas) == 3


def test_se_recusar_o_raciocinio_repete_sem_ele():
    recusa = {"error": {"message": "Thinking level is not supported"}}
    gemini, chamadas = cliente([(400, recusa), (200, OK)])
    gerar(gemini)
    assert "generationConfig" in json.loads(chamadas[0].content)
    assert "generationConfig" not in json.loads(chamadas[1].content)
    gerar(gemini)  # nas proximas chamadas ja vai sem
    assert "generationConfig" not in json.loads(chamadas[2].content)


@pytest.mark.parametrize(
    "corpo, trecho",
    [
        ({"candidates": []}, "sem candidatos"),
        ({"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}, "SAFETY"),
        ({"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}, "MAX_TOKENS"),
    ],
)
def test_resposta_sem_conteudo(corpo, trecho):
    gemini, _ = cliente([(200, corpo)])
    with pytest.raises(ErroGemini) as erro:
        gerar(gemini)
    assert trecho in str(erro.value)


def test_resposta_que_nao_e_json():
    def falso(requisicao):
        return httpx.Response(200, text="<html>")

    gemini = ClienteGemini(chave=CHAVE, transporte=httpx.MockTransport(falso), pausa_s=0)
    with pytest.raises(ErroGemini):
        gerar(gemini)
