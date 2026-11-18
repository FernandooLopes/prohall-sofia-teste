from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .catalogo import Produto
from .dinheiro import ZERO, D, arredondar, formatar
from .frete import CepInvalido, CotacaoFrete, calcular_frete

CUPOM = "PROHALL10"
PERCENTUAL_CUPOM = D("0.10")
MINIMO_CUPOM = D("150.00")
FATOR_PIX = D("0.95")  # 5% de desconto sobre os produtos
LIMITE_POR_ITEM = 10


class ErroRegra(Exception):
    # codigo e estavel (a Sofia e os testes usam), mensagem e pra cliente
    def __init__(self, codigo, mensagem, **extra):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.extra = extra

    def como_dict(self):
        return {"ok": False, "erro": self.codigo, "mensagem": self.mensagem, **self.extra}


def normalizar_cupom(codigo):
    return str(codigo or "").strip().upper()


def normalizar_modalidade(modalidade):
    texto = str(modalidade or "").strip().lower().replace("ô", "o").replace("ó", "o")
    if texto.startswith("econ"):
        return "economica"
    if texto.startswith("expres"):
        return "expressa"
    return None


def quantidade_inteira(valor):
    # aceita 2, "2" e 2.0; recusa fracao, booleano e texto
    erro = ErroRegra("quantidade_invalida", "A quantidade precisa ser um número inteiro.")
    if isinstance(valor, bool):
        raise erro
    try:
        numero = D(str(valor).strip())
    except InvalidOperation:
        raise erro from None
    if not numero.is_finite() or numero != numero.to_integral_value():
        raise erro
    return int(numero)


def quantidade_maxima(estoque):
    return max(0, min(LIMITE_POR_ITEM, estoque))


def validar_quantidade(produto, quantidade, estoque):
    if quantidade < 1:
        raise ErroRegra("quantidade_invalida", "A quantidade mínima é 1 unidade.")
    maximo = quantidade_maxima(estoque)
    if maximo == 0:
        raise ErroRegra(
            "sem_estoque",
            f"{produto.nome_curto} está sem estoque no momento.",
            produto_id=produto.id,
            maximo=0,
        )
    if quantidade > maximo:
        if estoque < LIMITE_POR_ITEM:
            motivo = f"só temos {estoque} unidade(s) em estoque"
        else:
            motivo = f"o limite é de {LIMITE_POR_ITEM} unidades por item"
        raise ErroRegra(
            "quantidade_maxima",
            f"Não dá para levar {quantidade} unidades de {produto.nome_curto}: {motivo}. "
            f"O máximo no carrinho é {maximo}.",
            produto_id=produto.id,
            maximo=maximo,
        )


def validar_cupom(codigo, subtotal):
    codigo = normalizar_cupom(codigo)
    if codigo != CUPOM:
        raise ErroRegra(
            "cupom_invalido",
            f"O cupom informado não é válido. O único cupom ativo é {CUPOM}.",
        )
    if subtotal < MINIMO_CUPOM:
        falta = MINIMO_CUPOM - subtotal
        raise ErroRegra(
            "cupom_minimo",
            f"O cupom {CUPOM} vale para pedidos a partir de {formatar(MINIMO_CUPOM)} "
            f"em produtos (subtotal). Faltam {formatar(falta)}.",
            falta=formatar(falta),
        )
    return codigo


@dataclass(frozen=True)
class LinhaCarrinho:
    produto: Produto
    quantidade: int
    preco_unitario: Decimal
    total: Decimal


@dataclass(frozen=True)
class Totais:
    linhas: tuple
    quantidade_itens: int
    peso_itens_g: int
    subtotal: Decimal
    cupom: str | None  # so guarda o codigo se for o PROHALL10
    cupom_aplicado: bool
    desconto_cupom: Decimal
    falta_para_cupom: Decimal
    base: Decimal
    cotacao: CotacaoFrete | None
    modalidade: str | None
    frete: Decimal | None  # None enquanto faltar CEP ou modalidade
    frete_gratis: bool
    desconto_pix: Decimal
    produtos_no_pix: Decimal
    total_pix: Decimal
    total_completo: bool  # True quando o frete ja entrou no total

    @property
    def vazio(self):
        return not self.linhas


def calcular_totais(catalogo, itens, cupom=None, cep=None, modalidade=None):
    """itens: {produto_id: quantidade}. Cada etapa arredonda pra 2 casas."""
    linhas = []
    for produto_id, quantidade in itens.items():
        produto = catalogo.obter(produto_id)
        if produto is None or quantidade <= 0:
            continue
        preco = produto.preco_vigente
        linhas.append(LinhaCarrinho(produto, quantidade, preco, arredondar(preco * quantidade)))

    subtotal = arredondar(sum((l.total for l in linhas), ZERO))
    peso_itens = sum(l.produto.peso_g * l.quantidade for l in linhas)

    # o cupom deixa de valer se o subtotal cair abaixo do minimo
    cupom = normalizar_cupom(cupom)
    if cupom != CUPOM:
        cupom = None
    cupom_aplicado = cupom is not None and subtotal >= MINIMO_CUPOM
    desconto_cupom = arredondar(subtotal * PERCENTUAL_CUPOM) if cupom_aplicado else ZERO
    falta_para_cupom = MINIMO_CUPOM - subtotal if cupom and not cupom_aplicado else ZERO

    base = arredondar(subtotal - desconto_cupom)

    # o frete e cotado sobre a base; so entra no total com CEP e modalidade
    cotacao = None
    if cep and linhas:
        try:
            cotacao = calcular_frete(cep, peso_itens, base)
        except CepInvalido:
            pass
    modalidade = normalizar_modalidade(modalidade)
    opcao = cotacao.opcoes.get(modalidade) if cotacao else None
    frete = opcao.valor if opcao else None

    # o total segue a formula base x 0,95 + frete, e o desconto mostrado e a
    # diferenca. Assim o resumo fecha no centavo (base 79,90 -> 75,91 e desconto 3,99)
    produtos_no_pix = arredondar(base * FATOR_PIX)
    desconto_pix = base - produtos_no_pix
    total_pix = produtos_no_pix + (frete or ZERO)

    return Totais(
        linhas=tuple(linhas),
        quantidade_itens=sum(l.quantidade for l in linhas),
        peso_itens_g=peso_itens,
        subtotal=subtotal,
        cupom=cupom,
        cupom_aplicado=cupom_aplicado,
        desconto_cupom=desconto_cupom,
        falta_para_cupom=falta_para_cupom,
        base=base,
        cotacao=cotacao,
        modalidade=modalidade if opcao else None,
        frete=frete,
        frete_gratis=opcao.gratis if opcao else False,
        desconto_pix=desconto_pix,
        produtos_no_pix=produtos_no_pix,
        total_pix=total_pix,
        total_completo=opcao is not None,
    )
