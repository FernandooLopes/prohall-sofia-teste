from decimal import Decimal

import pytest

from app.catalogo import carregar_catalogo
from app.dinheiro import arredondar
from app.regras import calcular_totais

D = Decimal
CEP_Z1 = "01310100"  # Sao Paulo/SP
CEP_Z3 = "70040010"  # Brasilia/DF


# --- Subtotal -------------------------------------------------------------------

def test_subtotal_usa_preco_promocional_quando_houver(catalogo):
    totais = calcular_totais(catalogo, {"promo": 2, "cem": 1})
    # promo: de 80,00 por 59,90 -> 2 x 59,90 = 119,80; cem: 100,00 (sem promocao)
    assert totais.subtotal == D("219.80")
    assert [linha.total for linha in totais.linhas] == [D("119.80"), D("100.00")]
    assert totais.quantidade_itens == 3


def test_carrinho_vazio_zera_tudo(catalogo):
    totais = calcular_totais(catalogo, {}, cupom="PROHALL10", cep=CEP_Z1, modalidade="economica")
    assert totais.vazio
    assert totais.subtotal == totais.base == totais.total_pix == D("0.00")
    assert totais.frete is None and totais.cotacao is None


# --- Cupom ----------------------------------------------------------------------

def test_cupom_de_10_por_cento_sobre_o_subtotal(catalogo):
    totais = calcular_totais(catalogo, {"cem": 2}, cupom="PROHALL10")
    assert totais.cupom_aplicado
    assert totais.desconto_cupom == D("20.00")
    assert totais.base == D("180.00")


def test_cupom_vale_com_subtotal_exatamente_150(catalogo):
    totais = calcular_totais(catalogo, {"cem": 1, "cinquenta": 1}, cupom="PROHALL10")
    assert totais.subtotal == D("150.00")
    assert totais.cupom_aplicado and totais.desconto_cupom == D("15.00")
    assert totais.base == D("135.00")


def test_cupom_nao_vale_abaixo_de_150(catalogo):
    totais = calcular_totais(catalogo, {"quebrado": 1}, cupom="PROHALL10")
    assert totais.subtotal == D("149.99")
    assert not totais.cupom_aplicado
    assert totais.desconto_cupom == D("0.00")
    assert totais.base == D("149.99")
    assert totais.falta_para_cupom == D("0.01")


def test_cupom_arredonda_meio_centavo_para_cima(catalogo):
    totais = calcular_totais(catalogo, {"empate-cupom": 1}, cupom="PROHALL10")
    # 10% de 154,85 = 15,485 -> 15,49
    assert totais.desconto_cupom == D("15.49")
    assert totais.base == D("139.36")


def test_cupom_desconhecido_no_carrinho_e_ignorado(catalogo):
    totais = calcular_totais(catalogo, {"cem": 2}, cupom="OUTRO")
    assert totais.cupom is None and totais.desconto_cupom == D("0.00")


# --- Desconto PIX e total -------------------------------------------------------

def test_desconto_pix_de_5_por_cento_sobre_a_base(catalogo):
    totais = calcular_totais(catalogo, {"cem": 1})
    assert totais.base == D("100.00")
    assert totais.desconto_pix == D("5.00")
    assert totais.produtos_no_pix == D("95.00")
    assert totais.total_pix == D("95.00")
    assert not totais.total_completo  # ainda sem frete


def test_total_pix_e_base_vezes_095_mais_frete(catalogo):
    totais = calcular_totais(catalogo, {"cem": 1}, cep=CEP_Z1, modalidade="expressa")
    # peso 300 g + 200 g = 500 g -> Z1 Expressa ate 0,5 kg = 24,90
    assert totais.frete == D("24.90")
    assert totais.total_pix == D("100.00") * D("0.95") + D("24.90") == D("119.90")
    assert totais.total_completo


def test_desconto_pix_nao_incide_sobre_o_frete(catalogo):
    sem_frete = calcular_totais(catalogo, {"cem": 1})
    com_frete = calcular_totais(catalogo, {"cem": 1}, cep=CEP_Z1, modalidade="economica")
    assert com_frete.desconto_pix == sem_frete.desconto_pix == D("5.00")
    assert com_frete.total_pix - sem_frete.total_pix == com_frete.frete == D("15.90")


def test_centavo_do_pix_segue_a_formula_do_total_e_o_resumo_fecha(catalogo):
    # base 79,90: 79,90 x 0,95 = 75,905 -> 75,91; desconto exibido = 79,90 - 75,91 = 3,99
    totais = calcular_totais(catalogo, {"setenta-nove-noventa": 1}, cep=CEP_Z1, modalidade="economica")
    assert totais.base == D("79.90")
    assert totais.produtos_no_pix == D("75.91")
    assert totais.desconto_pix == D("3.99")
    assert totais.frete == D("15.90")  # 100 g + 200 g
    assert totais.total_pix == D("91.81")
    # o resumo fecha centavo a centavo
    assert totais.base - totais.desconto_pix + totais.frete == totais.total_pix


@pytest.mark.parametrize("quantidades", [{"cem": 1}, {"promo": 3}, {"quebrado": 2}, {"empate-cupom": 3, "promo": 1}])
def test_resumo_sempre_fecha(catalogo, quantidades):
    totais = calcular_totais(catalogo, quantidades, cupom="PROHALL10", cep=CEP_Z3, modalidade="expressa")
    assert totais.subtotal - totais.desconto_cupom == totais.base
    assert totais.base - totais.desconto_pix + totais.frete == totais.total_pix
    assert totais.total_pix == arredondar(totais.base * D("0.95")) + totais.frete


# --- Frete dentro dos totais ------------------------------------------------------

def test_frete_gratis_considera_a_base_depois_do_cupom(catalogo):
    # subtotal 310,00 em Z1 (minimo 299,00)
    sem_cupom = calcular_totais(catalogo, {"trezentos-dez": 1}, cep=CEP_Z1, modalidade="economica")
    assert sem_cupom.frete_gratis and sem_cupom.frete == D("0.00")
    # com o cupom a base cai para 279,00 e o frete deixa de ser gratis
    com_cupom = calcular_totais(catalogo, {"trezentos-dez": 1}, cupom="PROHALL10", cep=CEP_Z1, modalidade="economica")
    assert com_cupom.base == D("279.00")
    assert not com_cupom.frete_gratis and com_cupom.frete == D("18.90")  # 400 g + 200 g
    assert com_cupom.cotacao.falta_para_frete_gratis == D("20.00")


def test_frete_gratis_nao_usa_o_valor_com_desconto_pix(catalogo):
    # base 310,00 >= 299,00 mesmo que 310 x 0,95 = 294,50 fique abaixo
    totais = calcular_totais(catalogo, {"trezentos-dez": 1}, cep=CEP_Z1, modalidade="economica")
    assert totais.produtos_no_pix == D("294.50")
    assert totais.frete_gratis
    assert totais.total_pix == D("294.50")


def test_expressa_e_cobrada_mesmo_acima_do_minimo(catalogo):
    totais = calcular_totais(catalogo, {"trezentos-dez": 1}, cep=CEP_Z1, modalidade="expressa")
    assert not totais.frete_gratis
    assert totais.frete == D("29.90")
    assert totais.total_pix == D("324.40")


def test_sem_modalidade_o_total_fica_parcial(catalogo):
    totais = calcular_totais(catalogo, {"cem": 1}, cep=CEP_Z1)
    assert totais.cotacao is not None and set(totais.cotacao.opcoes) == {"economica", "expressa"}
    assert totais.frete is None and not totais.total_completo
    assert totais.total_pix == D("95.00")


def test_peso_acima_de_5kg_entra_no_total(catalogo):
    # 2 x 3.000 g + 200 g = 6.200 g -> Z3 Economica: 49,90 + 2 kg x 6,00 = 61,90
    totais = calcular_totais(catalogo, {"pesado": 2}, cep=CEP_Z3, modalidade="economica")
    assert totais.cotacao.peso_cobrado_g == 6200
    assert totais.frete == D("61.90")
    assert totais.total_pix == D("38.00") + D("61.90")


# --- Cenarios com o catalogo real -------------------------------------------------

def test_cenario_real_com_cupom_e_frete_pago():
    catalogo = carregar_catalogo()
    totais = calcular_totais(
        catalogo,
        {"tonico-force-hair-120ml": 2, "kit-encorpax": 1},
        cupom="PROHALL10",
        cep=CEP_Z1,
        modalidade="economica",
    )
    assert totais.subtotal == D("189.70")       # 2 x 24,90 + 139,90
    assert totais.desconto_cupom == D("18.97")  # 10%
    assert totais.base == D("170.73")
    assert totais.cotacao.peso_cobrado_g == 2580  # 2 x 190 + 2000 + 200
    assert totais.frete == D("29.90")           # Z1, ate 5 kg
    assert totais.produtos_no_pix == D("162.19")  # 170,73 x 0,95 = 162,1935
    assert totais.desconto_pix == D("8.54")
    assert totais.total_pix == D("192.09")


def test_cenario_real_frete_gratis_em_z1_mas_nao_em_z3():
    catalogo = carregar_catalogo()
    itens = {"kit-encorpax": 3}  # 3 x 139,90 = 419,70; com cupom a base e 377,73
    z1 = calcular_totais(catalogo, itens, cupom="PROHALL10", cep=CEP_Z1, modalidade="economica")
    assert z1.base == D("377.73")
    assert z1.frete_gratis and z1.total_pix == D("358.84")  # 377,73 x 0,95 = 358,8435
    z3 = calcular_totais(catalogo, itens, cupom="PROHALL10", cep=CEP_Z3, modalidade="economica")
    assert not z3.frete_gratis  # Z3 exige base >= 399,00
    assert z3.frete == D("61.90")  # 6.200 g: 49,90 + 2 x 6,00
    assert z3.total_pix == D("420.74")
