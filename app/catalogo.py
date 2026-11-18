import json
from dataclasses import dataclass, field
from decimal import Decimal

from .config import CAMINHO_CATALOGO
from .dinheiro import D


@dataclass(frozen=True)
class Produto:
    id: str
    nome: str
    nome_curto: str
    preco: Decimal
    peso_g: int
    preco_promocional: Decimal | None = None
    categoria: str = ""
    linha: str = ""
    uso: str = "nao_informado"
    kit: bool = False
    peso_estimado: bool = False
    estoque: int = 0
    conteudo: str = ""
    imagem: str = ""
    url: str = ""
    indicacao: str = ""
    beneficios: list = field(default_factory=list)
    ativos: list = field(default_factory=list)
    modo_de_uso: str = ""
    observacoes: str = ""

    @property
    def em_promocao(self):
        return self.preco_promocional is not None and self.preco_promocional < self.preco

    @property
    def preco_vigente(self):
        return self.preco_promocional if self.em_promocao else self.preco


def produto_de_dict(dados):
    dados = dict(dados)
    dados["preco"] = D(dados["preco"])
    if dados.get("preco_promocional") is not None:
        dados["preco_promocional"] = D(dados["preco_promocional"])
    return Produto(**dados)


class Catalogo:
    def __init__(self, produtos, precos_copiados_em=""):
        self.produtos = {p.id: p for p in produtos}
        self.precos_copiados_em = precos_copiados_em

    def obter(self, produto_id):
        return self.produtos.get(str(produto_id).strip())

    def listar(self):
        return list(self.produtos.values())

    def __len__(self):
        return len(self.produtos)


def carregar_catalogo(caminho=CAMINHO_CATALOGO):
    with open(caminho, encoding="utf-8") as arquivo:
        bruto = json.load(arquivo)
    return Catalogo(
        [produto_de_dict(p) for p in bruto["produtos"]],
        bruto.get("precos_copiados_em", ""),
    )
