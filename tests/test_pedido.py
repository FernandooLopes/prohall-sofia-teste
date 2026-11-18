import re
from decimal import Decimal

import pytest

from app.loja import AGUARDANDO, Loja, texto_pix_falso
from app.regras import ErroRegra

D = Decimal


def carrinho_pronto(loja, sessao, cep="01310-100", modalidade="economica"):
    loja.adicionar_item(sessao, "cem", 2)
    loja.aplicar_cupom(sessao, "PROHALL10")
    loja.definir_cep(sessao, cep)
    loja.escolher_modalidade(sessao, modalidade)


def test_pedido_criado_com_numero_valor_e_texto_falso(loja, sessao, cliente):
    carrinho_pronto(loja, sessao)
    pedido = loja.criar_pedido(sessao, cliente)
    assert re.fullmatch(r"PH-TESTE-\d{6}", pedido.numero)
    assert pedido.numero == "PH-TESTE-000001"
    assert pedido.status == AGUARDANDO
    # subtotal 200,00; cupom 20,00; base 180,00; frete Z1 ate 1 kg (600 + 200 g) 18,90
    assert (pedido.subtotal, pedido.desconto_cupom, pedido.base) == (D("200.00"), D("20.00"), D("180.00"))
    assert pedido.frete == D("18.90") and pedido.desconto_pix == D("9.00")
    assert pedido.total == D("189.90")
    assert pedido.copia_e_cola == "PIX-TESTE|PROHALL|PH-TESTE-000001|189.90|NAO-PAGAVEL"
    assert pedido.cupom == "PROHALL10"
    assert pedido.prazo == "3 a 5 dias úteis"
    # o carrinho fecha junto com o pedido
    assert sessao.itens == {} and sessao.cupom is None


def test_texto_do_pix_e_obviamente_falso():
    texto = texto_pix_falso("PH-TESTE-000123", D("123.45"))
    assert texto == "PIX-TESTE|PROHALL|PH-TESTE-000123|123.45|NAO-PAGAVEL"
    assert not texto.startswith("000201")  # comeco de um BR Code real
    assert "br.gov.bcb.pix" not in texto.lower()


def test_qr_code_e_gerado_do_mesmo_texto(loja, sessao, cliente):
    carrinho_pronto(loja, sessao)
    pedido = loja.criar_pedido(sessao, cliente)
    assert pedido.qr_code_data_uri().startswith("data:image/svg+xml")


def test_numeros_de_pedido_sao_sequenciais(loja, cliente):
    numeros = []
    for _ in range(3):
        sessao = loja.nova_sessao()
        loja.adicionar_item(sessao, "cem", 1)
        loja.definir_cep(sessao, cliente["cep"])
        loja.escolher_modalidade(sessao, "expressa")
        numeros.append(loja.criar_pedido(sessao, cliente).numero)
    assert numeros == ["PH-TESTE-000001", "PH-TESTE-000002", "PH-TESTE-000003"]


def test_estoque_e_reservado_no_pedido(loja, cliente):
    sessao = loja.nova_sessao()
    loja.adicionar_item(sessao, "promo", 5)  # todo o estoque
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "economica")
    loja.criar_pedido(sessao, cliente)
    assert loja.estoque["promo"] == 0
    outra = loja.nova_sessao()
    with pytest.raises(ErroRegra) as erro:
        loja.adicionar_item(outra, "promo", 1)
    assert erro.value.codigo == "sem_estoque"


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("nome", ""), ("nome", "A"), ("nome", "123"),
        ("email", ""), ("email", "sem-arroba"), ("email", "a@b"),
        ("cep", ""), ("cep", "1234"), ("cep", "00000-000"),
        ("endereco", ""), ("numero", ""),
    ],
)
def test_dados_do_checkout_sao_validados(loja, sessao, cliente, campo, valor):
    carrinho_pronto(loja, sessao)
    cliente[campo] = valor
    with pytest.raises(ErroRegra) as erro:
        loja.criar_pedido(sessao, cliente)
    assert erro.value.codigo == "dados_invalidos"
    assert campo in erro.value.extra["campos"]
    assert sessao.pedidos == [] and sessao.itens == {"cem": 2}


def test_complemento_e_opcional(loja, sessao, cliente):
    carrinho_pronto(loja, sessao)
    cliente["complemento"] = ""
    assert loja.criar_pedido(sessao, cliente).status == AGUARDANDO


def test_carrinho_vazio_nao_vira_pedido(loja, sessao, cliente):
    with pytest.raises(ErroRegra) as erro:
        loja.criar_pedido(sessao, cliente)
    assert erro.value.codigo == "carrinho_vazio"


def test_sem_modalidade_nao_gera_pix(loja, sessao, cliente):
    loja.adicionar_item(sessao, "cem", 1)
    with pytest.raises(ErroRegra) as erro:
        loja.criar_pedido(sessao, cliente)  # o CEP veio so no formulario, sem modalidade
    assert erro.value.codigo == "frete_nao_escolhido"
    assert sessao.cep == "01310100"  # o CEP informado fica guardado
    loja.escolher_modalidade(sessao, "economica")
    assert loja.criar_pedido(sessao, cliente).frete == D("15.90")


def test_cep_de_entrega_diferente_do_cotado_recalcula_e_pede_confirmacao(loja, sessao, cliente):
    carrinho_pronto(loja, sessao, cep="01310-100")  # cotado em Z1
    cliente["cep"] = "69005-000"  # entrega em Manaus (Z5)
    with pytest.raises(ErroRegra) as erro:
        loja.criar_pedido(sessao, cliente)
    assert erro.value.codigo == "frete_recalculado"
    assert sessao.pedidos == []
    assert loja.totais(sessao).frete == D("42.90")  # Z5 economica ate 1 kg
    pedido = loja.criar_pedido(sessao, cliente)  # confirmando, sai com o frete novo
    assert pedido.zona == "Z5" and pedido.frete == D("42.90")
    assert pedido.total == D("171.00") + D("42.90")


def test_conversa_e_formulario_geram_o_mesmo_pedido(catalogo, relogio, cliente):
    pedidos = []
    for origem in ("conversa", "formulario"):
        loja = Loja(catalogo=catalogo, validade_pix_s=900, relogio=relogio)
        sessao = loja.nova_sessao()
        carrinho_pronto(loja, sessao)
        pedidos.append(loja.criar_pedido(sessao, cliente, origem=origem))
    pela_conversa, pelo_formulario = pedidos
    for campo in (
        "numero", "status", "itens", "subtotal", "cupom", "desconto_cupom", "base", "cep", "zona",
        "modalidade", "frete", "prazo", "desconto_pix", "total", "cliente", "copia_e_cola", "expira_em",
    ):
        assert getattr(pela_conversa, campo) == getattr(pelo_formulario, campo), campo


def test_formulario_faz_a_sofia_avisar_no_chat(loja, sessao, cliente):
    carrinho_pronto(loja, sessao)
    pedido = loja.criar_pedido(sessao, cliente, origem="formulario")
    aviso = sessao.mensagens[-1]
    assert aviso["autor"] == "sofia"
    assert pedido.numero in aviso["texto"] and "R$ 189,90" in aviso["texto"]


def test_pedido_nao_guarda_cupom_que_nao_foi_aplicado(loja, sessao, cliente):
    loja.adicionar_item(sessao, "cem", 2)
    loja.aplicar_cupom(sessao, "PROHALL10")
    loja.definir_quantidade(sessao, "cem", 1)  # o subtotal cai pra 100,00
    loja.definir_cep(sessao, cliente["cep"])
    loja.escolher_modalidade(sessao, "economica")
    pedido = loja.criar_pedido(sessao, cliente)
    assert pedido.cupom is None and pedido.desconto_cupom == D("0.00")
    assert pedido.total == D("95.00") + D("15.90")
