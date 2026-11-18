import asyncio
import logging

import httpx

from . import config

log = logging.getLogger("sofia.gemini")

STATUS_TEMPORARIOS = {429, 500, 502, 503, 504}
TENTATIVAS = 3


class ErroGemini(Exception):
    def __init__(self, mensagem, status=None):
        super().__init__(mensagem)
        self.status = status


class ClienteGemini:
    # a chave so vai no cabecalho x-goog-api-key: nunca na URL, em log ou em mensagem de erro
    def __init__(
        self,
        chave=None,
        url=config.GEMINI_URL,
        nivel_raciocinio=None,
        transporte=None,
        timeout_s=60.0,
        pausa_s=1.0,
    ):
        self._chave = config.chave_gemini() if chave is None else chave
        self._url = url
        self._nivel = nivel_raciocinio or config.nivel_raciocinio()
        self._enviar_nivel = True
        self._pausa_s = pausa_s
        self._http = httpx.AsyncClient(timeout=timeout_s, transport=transporte)

    @property
    def configurado(self):
        return bool(self._chave)

    async def fechar(self):
        await self._http.aclose()

    def _corpo(self, instrucao, conteudos, ferramentas):
        corpo = {
            "systemInstruction": {"parts": [{"text": instrucao}]},
            "contents": conteudos,
        }
        if ferramentas:
            corpo["tools"] = [{"functionDeclarations": ferramentas}]
        if self._enviar_nivel:
            corpo["generationConfig"] = {"thinkingConfig": {"thinkingLevel": self._nivel}}
        return corpo

    async def gerar(self, instrucao, conteudos, ferramentas):
        """Chama o modelo e devolve {'role': 'model', 'parts': [...]}.

        O content volta intacto (com thoughtSignature), porque o Gemini 3
        exige receber as assinaturas de volta no function calling.
        """
        if not self.configurado:
            raise ErroGemini("GEMINI_API_KEY não configurada no servidor.")
        cabecalhos = {"x-goog-api-key": self._chave, "Content-Type": "application/json"}
        ultimo_erro = None

        for tentativa in range(1, TENTATIVAS + 1):
            try:
                resposta = await self._http.post(
                    self._url, headers=cabecalhos, json=self._corpo(instrucao, conteudos, ferramentas)
                )
            except httpx.HTTPError as erro:
                ultimo_erro = ErroGemini(f"Falha de rede ao chamar o Gemini ({type(erro).__name__}).")
            else:
                if resposta.status_code == 200:
                    return self._extrair_conteudo(resposta)
                mensagem = self._mensagem_de_erro(resposta)
                if resposta.status_code == 400 and self._enviar_nivel and "thinking" in mensagem.lower():
                    # o modelo recusou o nivel de raciocinio: tenta de novo sem ele
                    log.warning("Gemini recusou thinkingLevel=%s; repetindo sem thinkingConfig.", self._nivel)
                    self._enviar_nivel = False
                    continue
                ultimo_erro = ErroGemini(
                    f"Gemini respondeu HTTP {resposta.status_code}: {mensagem}", resposta.status_code
                )
                if resposta.status_code not in STATUS_TEMPORARIOS:
                    break
            if tentativa < TENTATIVAS:
                await asyncio.sleep(self._pausa_s * tentativa)

        raise ultimo_erro or ErroGemini("Falha desconhecida ao chamar o Gemini.")

    @staticmethod
    def _mensagem_de_erro(resposta):
        try:
            mensagem = resposta.json().get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            mensagem = resposta.text
        return str(mensagem)[:300]

    @staticmethod
    def _extrair_conteudo(resposta):
        try:
            dados = resposta.json()
        except ValueError:
            raise ErroGemini("Resposta do Gemini não é JSON válido.") from None
        candidatos = dados.get("candidates") or []
        if not candidatos:
            motivo = (dados.get("promptFeedback") or {}).get("blockReason", "sem candidatos")
            raise ErroGemini(f"Gemini não devolveu resposta ({motivo}).")
        partes = (candidatos[0].get("content") or {}).get("parts") or []
        if not partes:
            motivo = candidatos[0].get("finishReason", "sem conteúdo")
            raise ErroGemini(f"Gemini devolveu resposta vazia ({motivo}).")
        return {"role": "model", "parts": partes}
