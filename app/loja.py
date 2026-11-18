import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config
from .catalogo import carregar_catalogo
from .frete import CepInvalido, normalizar_cep, zona_do_cep
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


@dataclass
class Sessao:
    id: str
    criada_em: datetime
    itens: dict = field(default_factory=dict)  # produto_id -> quantidade
    cupom: str | None = None
    cep: str | None = None
    modalidade: str | None = None


class Loja:
    # toda mudanca no carrinho passa por aqui, venha da conversa ou dos botoes
    def __init__(self, catalogo=None, validade_pix_s=None, relogio=None):
        self.catalogo = catalogo or carregar_catalogo()
        self.estoque = {p.id: p.estoque for p in self.catalogo.listar()}
        self.validade_pix_s = validade_pix_s or config.validade_pix()
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self.sessoes = {}

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
