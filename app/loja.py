import math
import re
import secrets
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import segno

from . import config
from .catalogo import carregar_catalogo
from .dinheiro import formatar
from .frete import NOMES_MODALIDADE, CepInvalido, formatar_cep, normalizar_cep, zona_do_cep
from .regras import (
    ErroRegra,
    calcular_totais,
    normalizar_cupom,
    normalizar_modalidade,
    quantidade_inteira,
    validar_codigo_cupom,
    validar_cupom,
    validar_quantidade,
)


def validar_cep(cep):
    try:
        cep = normalizar_cep(cep)
        zona_do_cep(cep)
    except CepInvalido as erro:
        raise ErroRegra("cep_invalido", str(erro)) from None
    return cep


AGUARDANDO = "aguardando_pagamento"
PAGO = "pago"
EXPIRADO = "expirado"

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


@dataclass
class Pedido:
    numero: str
    status: str
    criado_em: datetime
    expira_em: datetime
    itens: list
    subtotal: Decimal
    cupom: str | None
    desconto_cupom: Decimal
    base: Decimal
    cep: str
    zona: str
    modalidade: str
    frete: Decimal
    frete_gratis: bool
    prazo: str
    desconto_pix: Decimal
    total: Decimal
    cliente: dict
    copia_e_cola: str
    origem: str = "conversa"
    pago_em: datetime | None = None
    substituido_por: str | None = None

    @property
    def nome_modalidade(self):
        return NOMES_MODALIDADE[self.modalidade]

    def segundos_restantes(self, agora):
        if self.status != AGUARDANDO:
            return 0
        return max(0, math.ceil((self.expira_em - agora).total_seconds()))

    def qr_code_data_uri(self):
        return segno.make(self.copia_e_cola, error="m").svg_data_uri(scale=5, border=2)


def texto_pix_falso(numero, total):
    # de proposito fora do padrao do Banco Central (nao e BR Code/EMV)
    return f"PIX-TESTE|PROHALL|{numero}|{total:.2f}|NAO-PAGAVEL"


@dataclass
class Sessao:
    id: str
    criada_em: datetime
    itens: dict = field(default_factory=dict)  # produto_id -> quantidade
    cupom: str | None = None
    cep: str | None = None
    modalidade: str | None = None
    cliente: dict = field(default_factory=dict)
    pedidos: list = field(default_factory=list)
    mensagens: list = field(default_factory=list)  # o que aparece no chat
    historico: list = field(default_factory=list)  # o que foi trocado com o Gemini
    valores_vistos: set = field(default_factory=set)  # valores em R$ que o modelo ja viu
    _ultima_mensagem: int = 0

    def registrar(self, autor, texto, produtos=None):
        self._ultima_mensagem += 1
        mensagem = {
            "id": self._ultima_mensagem,
            "autor": autor,  # cliente, sofia ou sistema
            "texto": texto,
            "produtos": list(produtos or []),
            "quando": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.mensagens.append(mensagem)
        return mensagem

    def pedido(self, numero):
        numero = str(numero or "").strip().upper()
        return next((p for p in self.pedidos if p.numero == numero), None)

    def ultimo_pedido(self):
        return self.pedidos[-1] if self.pedidos else None


def _texto(valor, limite):
    return " ".join(str(valor or "").split())[:limite]


def validar_cliente(dados):
    dados = dados or {}
    erros = {}

    nome = _texto(dados.get("nome"), 100)
    if len(nome) < 3 or not any(c.isalpha() for c in nome):
        erros["nome"] = "Informe o nome completo."

    email = str(dados.get("email") or "").strip()
    if len(email) > 120 or not EMAIL.match(email):
        erros["email"] = "Informe um e-mail válido (ex.: nome@exemplo.com)."

    cep = ""
    try:
        cep = validar_cep(dados.get("cep"))
    except ErroRegra as erro:
        erros["cep"] = erro.mensagem

    endereco = _texto(dados.get("endereco"), 150)
    if len(endereco) < 3:
        erros["endereco"] = "Informe o endereço (rua, avenida...)."

    numero = str(dados.get("numero") or "").strip()
    if not numero or len(numero) > 10:
        erros["numero"] = "Informe o número do endereço (ou s/n)."

    if erros:
        raise ErroRegra(
            "dados_invalidos",
            "Para fechar o pedido ainda falta corrigir: " + " ".join(erros.values()),
            campos=erros,
        )
    return {
        "nome": nome,
        "email": email,
        "cep": cep,
        "endereco": endereco,
        "numero": numero,
        "complemento": _texto(dados.get("complemento"), 80),
    }


class Loja:
    # toda mudanca no carrinho passa por aqui, venha da conversa ou dos botoes
    def __init__(self, catalogo=None, validade_pix_s=None, relogio=None):
        self.catalogo = catalogo or carregar_catalogo()
        self.estoque = {p.id: p.estoque for p in self.catalogo.listar()}
        self.validade_pix_s = validade_pix_s or config.validade_pix()
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self.sessoes = {}
        self._ultimo_pedido = 0

    def agora(self):
        return self._relogio()

    def nova_sessao(self):
        sessao = Sessao(id=secrets.token_urlsafe(16), criada_em=self.agora())
        self.sessoes[sessao.id] = sessao
        return sessao

    def obter_sessao(self, sessao_id):
        return self.sessoes.get(str(sessao_id or ""))

    def totais(self, sessao):
        return calcular_totais(self.catalogo, sessao.itens, sessao.cupom, sessao.cep, sessao.modalidade)

    def _produto(self, produto_id):
        produto = self.catalogo.obter(produto_id)
        if produto is None:
            raise ErroRegra(
                "produto_inexistente",
                "Esse produto não existe no catálogo. Use apenas os ids do catálogo.",
            )
        return produto

    def adicionar_item(self, sessao, produto_id, quantidade=1):
        produto = self._produto(produto_id)
        quantidade = quantidade_inteira(quantidade)
        if quantidade < 1:
            raise ErroRegra("quantidade_invalida", "A quantidade mínima é 1 unidade.")
        total = sessao.itens.get(produto.id, 0) + quantidade
        validar_quantidade(produto, total, self.estoque[produto.id])
        sessao.itens[produto.id] = total
        return produto

    def definir_quantidade(self, sessao, produto_id, quantidade):
        produto = self._produto(produto_id)
        quantidade = quantidade_inteira(quantidade)
        if quantidade <= 0:
            return self.remover_item(sessao, produto_id)
        if produto.id not in sessao.itens:
            raise ErroRegra("item_fora_do_carrinho", f"{produto.nome_curto} não está no carrinho.")
        validar_quantidade(produto, quantidade, self.estoque[produto.id])
        sessao.itens[produto.id] = quantidade
        return produto

    def remover_item(self, sessao, produto_id):
        produto = self._produto(produto_id)
        if produto.id not in sessao.itens:
            raise ErroRegra("item_fora_do_carrinho", f"{produto.nome_curto} não está no carrinho.")
        del sessao.itens[produto.id]
        return produto

    def aplicar_cupom(self, sessao, codigo):
        if normalizar_cupom(codigo) == sessao.cupom and self.totais(sessao).cupom_aplicado:
            raise ErroRegra(
                "cupom_ja_aplicado",
                f"O cupom {sessao.cupom} já está aplicado. Vale um cupom por pedido.",
            )
        sessao.cupom = validar_cupom(codigo, self.totais(sessao).subtotal)
        return sessao.cupom

    def remover_cupom(self, sessao):
        sessao.cupom = None

    def definir_cep(self, sessao, cep):
        sessao.cep = validar_cep(cep)
        return sessao.cep

    def escolher_modalidade(self, sessao, modalidade):
        escolhida = normalizar_modalidade(modalidade)
        if escolhida is None:
            raise ErroRegra("modalidade_invalida", "As modalidades de frete são Econômica e Expressa.")
        if not sessao.cep:
            raise ErroRegra("cep_ausente", "Antes de escolher o frete é preciso informar o CEP de entrega.")
        sessao.modalidade = escolhida
        return escolhida

    def simular(self, itens, cep=None, cupom=None):
        """Totais de uma lista de itens qualquer, sem mexer no carrinho."""
        simulados = {}
        for item in itens or []:
            produto = self._produto(item.get("produto_id"))
            total = simulados.get(produto.id, 0) + quantidade_inteira(item.get("quantidade", 1))
            validar_quantidade(produto, total, self.estoque[produto.id])
            simulados[produto.id] = total
        if not simulados:
            raise ErroRegra("simulacao_vazia", "Informe ao menos um produto para simular.")
        cep = validar_cep(cep) if cep else None
        codigo = validar_codigo_cupom(cupom) if cupom else None
        return calcular_totais(self.catalogo, simulados, codigo, cep)

    def validade_em_texto(self):
        minutos, segundos = divmod(self.validade_pix_s, 60)
        return f"{minutos} minutos" if segundos == 0 else f"{self.validade_pix_s} segundos"

    def criar_pedido(self, sessao, dados_cliente, origem="conversa"):
        """Fecha o carrinho num pedido com PIX falso. Chat e formulario usam este mesmo metodo."""
        self.atualizar_pedidos(sessao)
        if not sessao.itens:
            raise ErroRegra("carrinho_vazio", "O carrinho está vazio: adicione produtos antes de fechar o pedido.")

        cliente = validar_cliente(dados_cliente)
        sessao.cliente = cliente

        if cliente["cep"] != sessao.cep:
            cep_cotado, sessao.cep = sessao.cep, cliente["cep"]
            if cep_cotado is not None:
                raise ErroRegra(
                    "frete_recalculado",
                    f"O CEP de entrega ({formatar_cep(cliente['cep'])}) é diferente do CEP usado na cotação "
                    f"({formatar_cep(cep_cotado)}). O frete foi recalculado: confira o novo total e confirme "
                    "para gerar o PIX.",
                )
        if sessao.modalidade is None:
            raise ErroRegra(
                "frete_nao_escolhido",
                "Falta escolher a modalidade de frete (Econômica ou Expressa) antes de gerar o PIX.",
            )

        for produto_id, quantidade in sessao.itens.items():
            validar_quantidade(self._produto(produto_id), quantidade, self.estoque[produto_id])

        totais = self.totais(sessao)
        if not totais.total_completo:
            raise ErroRegra("frete_nao_escolhido", "Não foi possível calcular o frete para fechar o pedido.")

        numero = self._novo_numero()
        agora = self.agora()
        pedido = Pedido(
            numero=numero,
            status=AGUARDANDO,
            criado_em=agora,
            expira_em=agora + timedelta(seconds=self.validade_pix_s),
            itens=[
                {
                    "produto_id": linha.produto.id,
                    "nome": linha.produto.nome_curto,
                    "quantidade": linha.quantidade,
                    "preco_unitario": linha.preco_unitario,
                    "total": linha.total,
                }
                for linha in totais.linhas
            ],
            subtotal=totais.subtotal,
            cupom=totais.cupom if totais.cupom_aplicado else None,
            desconto_cupom=totais.desconto_cupom,
            base=totais.base,
            cep=totais.cotacao.cep,
            zona=totais.cotacao.zona,
            modalidade=totais.modalidade,
            frete=totais.frete,
            frete_gratis=totais.frete_gratis,
            prazo=totais.cotacao.opcoes[totais.modalidade].prazo,
            desconto_pix=totais.desconto_pix,
            total=totais.total_pix,
            cliente=dict(cliente),
            copia_e_cola=texto_pix_falso(numero, totais.total_pix),
            origem=origem,
        )
        self._reservar_estoque(pedido)
        sessao.pedidos.append(pedido)
        sessao.itens = {}
        sessao.cupom = None

        if origem == "formulario":
            primeiro_nome = cliente["nome"].split()[0]
            sessao.registrar(
                "sofia",
                f"Prontinho, {primeiro_nome}! Gerei o PIX de teste do pedido {pedido.numero}, no valor de "
                f"{formatar(pedido.total)}. Ele vale por {self.validade_em_texto()} ⏰ "
                "É só usar o botão “Simular pagamento” (ambiente de teste: nenhum pagamento é real).",
            )
        return pedido

    def _novo_numero(self):
        self._ultimo_pedido += 1
        return f"PH-TESTE-{self._ultimo_pedido:06d}"

    def _reservar_estoque(self, pedido):
        for item in pedido.itens:
            self.estoque[item["produto_id"]] -= item["quantidade"]

    def _devolver_estoque(self, pedido):
        for item in pedido.itens:
            self.estoque[item["produto_id"]] += item["quantidade"]

    def atualizar_pedidos(self, sessao):
        """Expira os PIX vencidos (so uma vez) e devolve os que acabaram de expirar."""
        agora = self.agora()
        expirados = []
        for pedido in sessao.pedidos:
            if pedido.status == AGUARDANDO and agora >= pedido.expira_em:
                pedido.status = EXPIRADO
                self._devolver_estoque(pedido)
                expirados.append(pedido)
                sessao.registrar(
                    "sofia",
                    f"O PIX do pedido {pedido.numero} expirou ⏰ (a validade é de {self.validade_em_texto()}). "
                    "Quer que eu gere um novo PIX com os mesmos itens? É só me avisar aqui ou tocar em "
                    "“Gerar novo PIX”.",
                )
        return expirados

    def pagar_pedido(self, sessao, numero):
        """Simula o pagamento (botao do PIX de teste)."""
        self.atualizar_pedidos(sessao)
        pedido = sessao.pedido(numero)
        if pedido is None:
            raise ErroRegra("pedido_nao_encontrado", "Não encontrei esse pedido nesta conversa.")
        if pedido.status == PAGO:
            return pedido
        if pedido.status == EXPIRADO:
            raise ErroRegra(
                "pix_expirado",
                f"O PIX do pedido {pedido.numero} já expirou. É preciso gerar um novo PIX.",
            )
        pedido.status = PAGO
        pedido.pago_em = self.agora()
        primeiro_nome = pedido.cliente["nome"].split()[0]
        sessao.registrar(
            "sofia",
            f"Pagamento confirmado, {primeiro_nome}! 🎉 O pedido {pedido.numero}, no valor de "
            f"{formatar(pedido.total)}, está pago (simulação: nenhum pagamento real foi feito). "
            f"A entrega é pela modalidade {pedido.nome_modalidade}, com prazo de {pedido.prazo}. "
            "Se quiser dicas de como usar seus produtos, é só me chamar 💜",
        )
        return pedido

    def gerar_novo_pix(self, sessao, numero=None, origem="conversa"):
        """Novo pedido com os mesmos itens de um pedido que expirou."""
        self.atualizar_pedidos(sessao)
        if numero:
            anterior = sessao.pedido(numero)
        else:
            expirados = [p for p in sessao.pedidos if p.status == EXPIRADO and not p.substituido_por]
            anterior = expirados[-1] if expirados else None
        if anterior is None:
            raise ErroRegra("pedido_nao_encontrado", "Não há pedido com PIX expirado nesta conversa.")
        if anterior.status == PAGO:
            raise ErroRegra("pedido_ja_pago", f"O pedido {anterior.numero} já está pago.")
        if anterior.status == AGUARDANDO:
            raise ErroRegra(
                "pix_ainda_valido",
                f"O PIX do pedido {anterior.numero} ainda está válido; não é preciso gerar outro.",
            )
        if anterior.substituido_por:
            raise ErroRegra(
                "pix_ja_substituido",
                f"Esse pedido já foi substituído pelo {anterior.substituido_por}.",
            )
        for item in anterior.itens:
            validar_quantidade(
                self._produto(item["produto_id"]), item["quantidade"], self.estoque[item["produto_id"]]
            )

        numero_novo = self._novo_numero()
        agora = self.agora()
        novo = replace(
            anterior,
            numero=numero_novo,
            status=AGUARDANDO,
            criado_em=agora,
            expira_em=agora + timedelta(seconds=self.validade_pix_s),
            itens=[dict(item) for item in anterior.itens],
            cliente=dict(anterior.cliente),
            copia_e_cola=texto_pix_falso(numero_novo, anterior.total),
            origem=origem,
        )
        self._reservar_estoque(novo)
        anterior.substituido_por = novo.numero
        sessao.pedidos.append(novo)
        if origem == "botao":
            sessao.registrar(
                "sofia",
                f"Novo PIX de teste gerado! Agora o pedido é o {novo.numero}, no mesmo valor de "
                f"{formatar(novo.total)}, válido por {self.validade_em_texto()} ⏰",
            )
        return novo
