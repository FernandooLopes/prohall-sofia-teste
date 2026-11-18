from decimal import InvalidOperation

from .dinheiro import D, formatar

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
