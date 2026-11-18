import logging
import mimetypes
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .apresentacao import estado_para_ui, exportar_conversa, mensagem_para_ui
from .gemini import ClienteGemini
from .loja import Loja
from .prompts import SAUDACAO
from .regras import ErroRegra
from .sofia import Sofia

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

# em alguns Windows o registro mapeia .js e .css pra tipos errados e o navegador recusa o arquivo
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class Entrada(BaseModel):
    sessao_id: str = ""
    ultima_mensagem: int = 0


class EntradaChat(Entrada):
    mensagem: str = Field(default="", max_length=2000)


class EntradaItem(Entrada):
    produto_id: str = ""
    quantidade: int = 1


class EntradaCupom(Entrada):
    codigo: str = ""


class EntradaCep(Entrada):
    cep: str = ""


class EntradaModalidade(Entrada):
    modalidade: str = ""


class EntradaPedido(Entrada):
    nome: str = ""
    email: str = ""
    cep: str = ""
    endereco: str = ""
    numero: str = ""
    complemento: str = ""


class EntradaNumero(Entrada):
    numero: str = ""


def criar_app(loja=None, gemini=None):
    loja = loja or Loja()
    gemini = gemini or ClienteGemini()
    sofia = Sofia(loja, gemini)

    @asynccontextmanager
    async def ciclo_de_vida(_app):
        if not gemini.configurado:
            logging.getLogger("sofia").warning(
                "GEMINI_API_KEY não configurada: o chat só responde depois de preencher o .env."
            )
        yield
        await gemini.fechar()

    app = FastAPI(title="Sofia - Prohall (teste)", docs_url=None, redoc_url=None, lifespan=ciclo_de_vida)

    def resposta(sessao, ultima, **extra):
        return {
            "ok": True,
            "mensagens": [mensagem_para_ui(loja, m) for m in sessao.mensagens_apos(ultima)],
            "estado": estado_para_ui(loja, sessao),
            **extra,
        }

    def resposta_de_erro(sessao, ultima, erro):
        corpo = erro.como_dict()
        corpo["mensagens"] = [mensagem_para_ui(loja, m) for m in sessao.mensagens_apos(ultima)]
        corpo["estado"] = estado_para_ui(loja, sessao)
        return JSONResponse(corpo, status_code=400)

    def sessao_inexistente():
        corpo = {"ok": False, "erro": "sessao_inexistente", "mensagem": "Sessão não encontrada. Inicie uma nova conversa."}
        return JSONResponse(corpo, status_code=404)

    @app.middleware("http")
    async def sem_cache(request: Request, call_next):
        retorno = await call_next(request)
        retorno.headers["Cache-Control"] = "no-store"
        return retorno

    @app.get("/")
    async def pagina_inicial():
        return FileResponse(config.PASTA_STATIC / "index.html")

    @app.get("/api/saude")
    async def saude():
        return {"ok": True, "modelo": config.MODELO_GEMINI, "gemini_configurado": gemini.configurado}

    # --- sessao e chat ---

    @app.post("/api/sessao")
    async def nova_sessao():
        sessao = loja.nova_sessao()
        sessao.registrar("sofia", SAUDACAO)
        return resposta(sessao, 0, gemini_configurado=gemini.configurado)

    @app.get("/api/estado")
    async def estado(sessao_id: str = "", ultima_mensagem: int = 0):
        sessao = loja.obter_sessao(sessao_id)
        if sessao is None:
            return sessao_inexistente()
        loja.atualizar_pedidos(sessao)
        return resposta(sessao, ultima_mensagem, gemini_configurado=gemini.configurado)

    @app.post("/api/chat")
    async def chat(entrada: EntradaChat):
        sessao = loja.obter_sessao(entrada.sessao_id)
        if sessao is None:
            return sessao_inexistente()
        texto = entrada.mensagem.strip()
        if not texto:
            erro = ErroRegra("mensagem_vazia", "Escreva uma mensagem para a Sofia.")
            return resposta_de_erro(sessao, entrada.ultima_mensagem, erro)
        async with sessao.trava:
            loja.atualizar_pedidos(sessao)
            sessao.registrar("cliente", texto)
            retorno = await sofia.responder(sessao, texto)
            autor = "sofia" if gemini.configurado else "sistema"
            sessao.registrar(autor, retorno.texto, retorno.produtos)
        acoes = {"abrir_checkout": retorno.abrir_checkout, "abrir_pix": bool(retorno.pedido)}
        return resposta(sessao, entrada.ultima_mensagem, acoes=acoes)

    @app.get("/api/conversa/exportar")
    async def exportar(sessao_id: str = ""):
        sessao = loja.obter_sessao(sessao_id)
        if sessao is None:
            return sessao_inexistente()
        nome = f"conversa-sofia-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        return PlainTextResponse(
            exportar_conversa(loja, sessao),
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )

    # --- botoes da interface: carrinho, frete, checkout e PIX ---

    def operar(entrada, operacao, abrir_pix=False):
        """Roda a operacao na sessao e devolve o estado novo, ou o erro de regra."""
        sessao = loja.obter_sessao(entrada.sessao_id)
        if sessao is None:
            return sessao_inexistente()
        loja.atualizar_pedidos(sessao)
        try:
            operacao(sessao)
        except ErroRegra as erro:
            return resposta_de_erro(sessao, entrada.ultima_mensagem, erro)
        extra = {"acoes": {"abrir_checkout": False, "abrir_pix": True}} if abrir_pix else {}
        return resposta(sessao, entrada.ultima_mensagem, **extra)

    @app.post("/api/carrinho/adicionar")
    async def carrinho_adicionar(entrada: EntradaItem):
        def operacao(sessao):
            produto = loja.adicionar_item(sessao, entrada.produto_id, entrada.quantidade)
            sessao.registrar("sistema", f"A cliente adicionou {entrada.quantidade}x {produto.nome_curto} pelo botão.")

        return operar(entrada, operacao)

    @app.post("/api/carrinho/quantidade")
    async def carrinho_quantidade(entrada: EntradaItem):
        return operar(entrada, lambda s: loja.definir_quantidade(s, entrada.produto_id, entrada.quantidade))

    @app.post("/api/carrinho/remover")
    async def carrinho_remover(entrada: EntradaItem):
        return operar(entrada, lambda s: loja.remover_item(s, entrada.produto_id))

    @app.post("/api/cupom")
    async def cupom_aplicar(entrada: EntradaCupom):
        return operar(entrada, lambda s: loja.aplicar_cupom(s, entrada.codigo))

    @app.post("/api/cupom/remover")
    async def cupom_remover(entrada: Entrada):
        return operar(entrada, loja.remover_cupom)

    @app.post("/api/frete")
    async def frete_calcular(entrada: EntradaCep):
        return operar(entrada, lambda s: loja.definir_cep(s, entrada.cep))

    @app.post("/api/frete/modalidade")
    async def frete_modalidade(entrada: EntradaModalidade):
        return operar(entrada, lambda s: loja.escolher_modalidade(s, entrada.modalidade))

    @app.post("/api/pedido")
    async def pedido_criar(entrada: EntradaPedido):
        dados = entrada.model_dump(exclude={"sessao_id", "ultima_mensagem"})
        return operar(entrada, lambda s: loja.criar_pedido(s, dados, origem="formulario"), abrir_pix=True)

    @app.post("/api/pedido/pagar")
    async def pedido_pagar(entrada: EntradaNumero):
        return operar(entrada, lambda s: loja.pagar_pedido(s, entrada.numero))

    @app.post("/api/pedido/novo-pix")
    async def pedido_novo_pix(entrada: EntradaNumero):
        return operar(entrada, lambda s: loja.gerar_novo_pix(s, entrada.numero or None, origem="botao"), abrir_pix=True)

    app.mount("/static", StaticFiles(directory=config.PASTA_STATIC), name="static")
    return app


app = criar_app()
