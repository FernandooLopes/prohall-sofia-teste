import json
from decimal import Decimal

from app.catalogo import carregar_catalogo, produto_de_dict


def produto(**extras):
    base = {"id": "p1", "nome": "Produto 1", "nome_curto": "P1", "preco": 100, "peso_g": 200}
    return produto_de_dict(base | extras)


def test_preco_vira_decimal():
    p = produto(preco=74.9)
    assert p.preco == Decimal("74.9")


def test_preco_vigente_usa_promocional():
    p = produto(preco=100, preco_promocional=79.9)
    assert p.em_promocao
    assert p.preco_vigente == Decimal("79.9")


def test_sem_promocao_vale_o_preco_cheio():
    assert produto().preco_vigente == Decimal("100")
    # promocional maior que o cheio não é promoção
    assert produto(preco_promocional=120).preco_vigente == Decimal("100")


def test_carrega_do_json(tmp_path):
    arquivo = tmp_path / "catalogo.json"
    arquivo.write_text(
        json.dumps({
            "precos_copiados_em": "2026-11-16",
            "produtos": [
                {"id": "a", "nome": "A", "nome_curto": "A", "preco": 10, "peso_g": 100},
                {"id": "b", "nome": "B", "nome_curto": "B", "preco": 20, "peso_g": 100},
            ],
        }),
        encoding="utf-8",
    )
    catalogo = carregar_catalogo(arquivo)
    assert len(catalogo) == 2
    assert catalogo.precos_copiados_em == "2026-11-16"
    assert catalogo.obter(" b ").nome == "B"
    assert catalogo.obter("nao-existe") is None


def test_catalogo_real_cumpre_o_enunciado():
    produtos = carregar_catalogo().listar()
    assert len(produtos) == 15
    assert len({p.categoria for p in produtos}) >= 4
    assert any(p.kit for p in produtos)
    assert any(p.uso == "profissional" for p in produtos)
    assert any(p.uso == "home_care" for p in produtos)
    assert all(p.estoque > 0 and p.peso_g > 0 for p in produtos)
