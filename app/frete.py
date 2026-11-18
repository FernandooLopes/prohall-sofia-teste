import re
from dataclasses import dataclass
from decimal import Decimal

from .dinheiro import ZERO, D

EMBALAGEM_G = 200
LIMITES_FAIXA_G = (500, 1000, 2000, 5000)  # inclusivos

# (zona, CEP inicial, CEP final), faixas inclusivas
FAIXAS_CEP = (
    ("Z1", 1_000_000, 19_999_999),
    ("Z2", 20_000_000, 29_999_999),
    ("Z1", 30_000_000, 39_999_999),
    ("Z4", 40_000_000, 65_999_999),
    ("Z5", 66_000_000, 69_999_999),
    ("Z3", 70_000_000, 76_799_999),
    ("Z5", 76_800_000, 77_999_999),
    ("Z3", 78_000_000, 79_999_999),
    ("Z2", 80_000_000, 89_999_999),
    ("Z3", 90_000_000, 99_999_999),
)

REGIOES = {
    "Z1": "SP e MG",
    "Z2": "RJ, ES, PR e SC",
    "Z3": "Centro-Oeste e RS",
    "Z4": "Nordeste",
    "Z5": "Norte",
}

NOMES_MODALIDADE = {"economica": "Econômica", "expressa": "Expressa"}

# modalidade -> zona -> (valores das 4 faixas, adicional por kg acima de 5 kg, prazo em dias uteis)
TABELA = {
    "economica": {
        "Z1": (("15.90", "18.90", "22.90", "29.90"), "3.50", (3, 5)),
        "Z2": (("19.90", "23.90", "28.90", "38.90"), "4.50", (4, 7)),
        "Z3": (("24.90", "29.90", "36.90", "49.90"), "6.00", (5, 9)),
        "Z4": (("29.90", "36.90", "45.90", "64.90"), "8.00", (7, 12)),
        "Z5": (("34.90", "42.90", "54.90", "79.90"), "10.00", (9, 15)),
    },
    "expressa": {
        "Z1": (("24.90", "29.90", "35.90", "47.90"), "5.50", (1, 2)),
        "Z2": (("31.90", "38.90", "46.90", "62.90"), "7.00", (2, 3)),
        "Z3": (("39.90", "48.90", "59.90", "82.90"), "9.50", (2, 4)),
        "Z4": (("49.90", "59.90", "74.90", "104.90"), "13.00", (3, 6)),
        "Z5": (("59.90", "72.90", "89.90", "129.90"), "16.00", (4, 8)),
    },
}

_CEP = re.compile(r"^(\d{5})-?(\d{3})$")


class CepInvalido(ValueError):
    pass


def normalizar_cep(cep):
    achado = _CEP.match(str(cep or "").strip())
    if not achado:
        raise CepInvalido("O CEP precisa ter 8 dígitos, com ou sem hífen (ex.: 01310-100).")
    return achado.group(1) + achado.group(2)


def formatar_cep(cep):
    cep = normalizar_cep(cep)
    return f"{cep[:5]}-{cep[5:]}"


def zona_do_cep(cep):
    numero = int(normalizar_cep(cep))
    for zona, inicio, fim in FAIXAS_CEP:
        if inicio <= numero <= fim:
            return zona
    # 00000-000 a 00999-999 não está em nenhuma zona da tabela
    raise CepInvalido("Esse CEP está fora das faixas de entrega atendidas.")


def peso_cobrado_g(peso_itens_g):
    return int(peso_itens_g) + EMBALAGEM_G


def minimo_frete_gratis(zona):
    return D("299.00") if zona in ("Z1", "Z2") else D("399.00")


def valor_tabela(modalidade, zona, peso_g):
    faixas, adicional_kg, _ = TABELA[modalidade][zona]
    for limite, valor in zip(LIMITES_FAIXA_G, faixas):
        if peso_g <= limite:
            return D(valor)
    excedente_g = peso_g - LIMITES_FAIXA_G[-1]
    kg_adicionais = -(-excedente_g // 1000)  # arredonda pra cima: 5,3 kg -> 1; 6,3 kg -> 2
    return D(faixas[-1]) + D(adicional_kg) * kg_adicionais


@dataclass(frozen=True)
class OpcaoFrete:
    modalidade: str
    nome: str
    valor: Decimal  # o que sera cobrado (0,00 quando e gratis)
    valor_tabela: Decimal
    gratis: bool
    prazo_min: int
    prazo_max: int

    @property
    def prazo(self):
        return f"{self.prazo_min} a {self.prazo_max} dias úteis"


@dataclass(frozen=True)
class CotacaoFrete:
    cep: str
    zona: str
    regiao: str
    peso_cobrado_g: int
    opcoes: dict  # modalidade -> OpcaoFrete
    minimo_frete_gratis: Decimal
    falta_para_frete_gratis: Decimal


def calcular_frete(cep, peso_itens_g, base_produtos):
    # base_produtos = produtos depois do cupom e antes do desconto PIX
    cep = normalizar_cep(cep)
    zona = zona_do_cep(cep)
    peso = peso_cobrado_g(peso_itens_g)
    base = D(base_produtos)
    minimo = minimo_frete_gratis(zona)

    opcoes = {}
    for modalidade in ("economica", "expressa"):
        tabela = valor_tabela(modalidade, zona, peso)
        gratis = modalidade == "economica" and base >= minimo
        prazo_min, prazo_max = TABELA[modalidade][zona][2]
        opcoes[modalidade] = OpcaoFrete(
            modalidade=modalidade,
            nome=NOMES_MODALIDADE[modalidade],
            valor=ZERO if gratis else tabela,
            valor_tabela=tabela,
            gratis=gratis,
            prazo_min=prazo_min,
            prazo_max=prazo_max,
        )

    return CotacaoFrete(
        cep=cep,
        zona=zona,
        regiao=REGIOES[zona],
        peso_cobrado_g=peso,
        opcoes=opcoes,
        minimo_frete_gratis=minimo,
        falta_para_frete_gratis=max(minimo - base, ZERO),
    )
