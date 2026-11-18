import re

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
