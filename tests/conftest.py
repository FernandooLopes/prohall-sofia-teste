from datetime import datetime, timedelta, timezone

import pytest

from app.catalogo import Catalogo, produto_de_dict
from app.loja import Loja


def _produto(id, preco, promocional=None, peso_g=300, estoque=50):
    return produto_de_dict(
        {
            "id": id,
            "nome": f"Produto {id}",
            "nome_curto": f"Produto {id}",
            "categoria": "Teste",
            "preco": preco,
            "preco_promocional": promocional,
            "peso_g": peso_g,
            "estoque": estoque,
        }
    )


@pytest.fixture
def catalogo():
    return Catalogo(
        [
            _produto("cem", "100.00"),
            _produto("cinquenta", "50.00"),
            _produto("promo", "80.00", promocional="59.90", peso_g=500, estoque=5),
            _produto("quebrado", "149.99"),
            _produto("empate-cupom", "154.85"),
            _produto("setenta-nove-noventa", "159.90", promocional="79.90", peso_g=100),
            _produto("pesado", "20.00", peso_g=3000, estoque=20),
            _produto("esgotado", "30.00", estoque=0),
            _produto("trezentos-dez", "310.00", peso_g=400),
        ]
    )


class Relogio:
    def __init__(self):
        self.agora = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.agora

    def avancar(self, **kwargs):
        self.agora += timedelta(**kwargs)


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def loja(catalogo, relogio):
    return Loja(catalogo=catalogo, validade_pix_s=900, relogio=relogio)


@pytest.fixture
def sessao(loja):
    return loja.nova_sessao()


@pytest.fixture
def cliente():
    return {
        "nome": "Maria Teste",
        "email": "maria@exemplo.com",
        "cep": "01310-100",
        "endereco": "Avenida Paulista",
        "numero": "1000",
        "complemento": "apto 12",
    }
