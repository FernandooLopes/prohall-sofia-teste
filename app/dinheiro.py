from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


def D(valor):
    # passa por str para não herdar a imprecisão do float
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def arredondar(valor):
    return D(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def formatar(valor):
    """1234.5 -> 'R$ 1.234,50'"""
    valor = arredondar(valor)
    #troca vírgula e ponto do formato americano pelos do brasileiro
    numero = f"{abs(valor):,.2f}".translate(str.maketrans(",.", ".,"))
    return f"{'-' if valor < 0 else ''}R$ {numero}"
