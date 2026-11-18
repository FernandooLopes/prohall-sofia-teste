import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from . import ferramentas
from .dinheiro import arredondar, formatar
from .ferramentas import EfeitosTurno
from .gemini import ErroGemini
from .prompts import montar_instrucao

log = logging.getLogger("sofia")

MAX_PASSOS = 8

RESPOSTA_FALHA = "Ai, tive um probleminha técnico aqui do meu lado 😅 Pode mandar sua mensagem de novo, por favor?"
RESPOSTA_SEM_CHAVE = (
    "A chave do Gemini não está configurada no servidor. Crie o arquivo .env a partir do .env.example, "
    "preencha GEMINI_API_KEY e reinicie o servidor."
)
RESPOSTA_VAZIA = "Prontinho! Posso te ajudar com mais alguma coisa? 😊"

# "R$ 1.234,56", "R$ 24,9", "R$ 299" e tambem "24,90" sem o R$
COM_CIFRAO = re.compile(r"R\$\s*([\d.]+(?:,\d{1,2})?)")
SEM_CIFRAO = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})*,\d{2})(?![\d,])")
NUMERO_SOLTO = re.compile(r"\d+(?:[.,]\d+)*")


def _para_decimal(texto):
    texto = texto.strip().strip(".")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif not re.fullmatch(r"\d+\.\d{2}", texto):
        texto = texto.replace(".", "")  # ponto de milhar
    try:
        return arredondar(Decimal(texto))
    except InvalidOperation:
        return None


def _valores(padrao, texto):
    valores = (_para_decimal(bruto) for bruto in padrao.findall(texto or ""))
    return {valor for valor in valores if valor is not None}


def valores_em_reais(texto):
    return _valores(COM_CIFRAO, texto) | _valores(SEM_CIFRAO, texto)


def numeros_da_cliente(texto):
    # qualquer numero que a cliente digitou pode ser repetido pela Sofia
    return _valores(NUMERO_SOLTO, texto)


def nota_de_correcao(desconhecidos):
    lista = ", ".join(formatar(valor) for valor in sorted(desconhecidos))
    return (
        "# CORREÇÃO OBRIGATÓRIA\n"
        f"Sua última resposta foi descartada porque citava valores que não vieram do catálogo, do "
        f"ESTADO ATUAL nem das ferramentas: {lista}. Refaça a resposta usando somente valores vindos "
        "dessas fontes. Se precisar de uma soma ou total, chame simular_pedido ou ver_carrinho."
    )


@dataclass
class RespostaSofia:
    texto: str
    produtos: list = field(default_factory=list)
    abrir_checkout: bool = False
    pedido: str | None = None
    falhou: bool = False


class Sofia:
    """Um turno: a cliente fala, o modelo responde (ou pede ferramentas), o codigo executa
    e o resultado volta ao modelo, ate sair uma resposta em texto.

    Rede de seguranca: todo valor em reais da resposta precisa ter sido mostrado pelo sistema
    (catalogo, estado, ferramentas) ou digitado pela cliente. Se aparecer um valor
    desconhecido, a resposta e descartada e refeita uma vez.
    """

    def __init__(self, loja, gemini):
        self.loja = loja
        self.gemini = gemini

    async def responder(self, sessao, texto_cliente):
        if not self.gemini.configurado:
            return RespostaSofia(RESPOSTA_SEM_CHAVE, falhou=True)

        efeitos = EfeitosTurno()
        inicio_do_turno = len(sessao.historico)
        sessao.historico.append({"role": "user", "parts": [{"text": texto_cliente}]})
        sessao.valores_vistos |= numeros_da_cliente(texto_cliente)

        try:
            texto = await self._conversar(sessao, efeitos)
        except ErroGemini as erro:
            log.error("Falha ao falar com o Gemini: %s", erro)
            # desfaz o turno pra conversa continuar consistente
            del sessao.historico[inicio_do_turno:]
            return self._resposta(RESPOSTA_FALHA, efeitos, falhou=True)
        return self._resposta(texto or RESPOSTA_VAZIA, efeitos)

    @staticmethod
    def _resposta(texto, efeitos, falhou=False):
        return RespostaSofia(
            texto,
            produtos=efeitos.produtos,
            abrir_checkout=efeitos.abrir_checkout,
            pedido=efeitos.pedido,
            falhou=falhou,
        )

    def _executar(self, sessao, chamadas, efeitos):
        respostas = []
        for chamada in chamadas:
            nome = chamada.get("name", "")
            resultado = ferramentas.executar(self.loja, sessao, nome, chamada.get("args") or {}, efeitos)
            sessao.valores_vistos |= valores_em_reais(json.dumps(resultado, ensure_ascii=False))
            resposta = {"name": nome, "response": resultado}
            if chamada.get("id"):
                resposta["id"] = chamada["id"]
            respostas.append({"functionResponse": resposta})
        return respostas

    async def _conversar(self, sessao, efeitos):
        nota = ""
        ja_corrigiu = False
        trechos = []

        for _ in range(MAX_PASSOS):
            # a instrucao e remontada a cada passo: uma ferramenta pode ter mudado o estado
            instrucao = montar_instrucao(self.loja, sessao, nota)
            sessao.valores_vistos |= valores_em_reais(instrucao)
            conteudo = await self.gemini.gerar(instrucao, sessao.historico, ferramentas.DECLARACOES)
            sessao.historico.append(conteudo)

            partes = conteudo["parts"]
            texto = "".join(p["text"] for p in partes if "text" in p and not p.get("thought")).strip()
            chamadas = [p["functionCall"] for p in partes if isinstance(p.get("functionCall"), dict)]

            if chamadas:
                if texto:
                    trechos.append(texto)
                sessao.historico.append({"role": "user", "parts": self._executar(sessao, chamadas, efeitos)})
                continue

            desconhecidos = valores_em_reais(texto) - sessao.valores_vistos
            if desconhecidos and not ja_corrigiu:
                log.warning("Resposta descartada por citar valores não verificados: %s", sorted(desconhecidos))
                ja_corrigiu = True
                sessao.historico.pop()
                nota = nota_de_correcao(desconhecidos)
                continue
            if desconhecidos:
                log.warning("Resposta enviada ainda com valores não verificados: %s", sorted(desconhecidos))

            trechos.append(texto)
            break
        else:
            log.warning("Limite de %s passos atingido sem resposta final.", MAX_PASSOS)

        return "\n\n".join(t for t in trechos if t)
