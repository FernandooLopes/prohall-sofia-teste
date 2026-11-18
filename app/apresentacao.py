from .dinheiro import formatar
from .frete import formatar_cep
from .regras import quantidade_maxima

ROTULOS_STATUS = {
    "aguardando_pagamento": "aguardando pagamento",
    "pago": "pago",
    "expirado": "expirado",
}


def cartao_produto(loja, produto):
    estoque = loja.estoque[produto.id]
    return {
        "id": produto.id,
        "nome": produto.nome,
        "nome_curto": produto.nome_curto,
        "categoria": produto.categoria,
        "conteudo": produto.conteudo,
        "imagem": produto.imagem,
        "url": produto.url,
        "em_promocao": produto.em_promocao,
        "preco": formatar(produto.preco),
        "preco_vigente": formatar(produto.preco_vigente),
        "estoque": estoque,
        "maximo": quantidade_maxima(estoque),
    }


def _frete_para_ui(totais):
    cotacao = totais.cotacao
    if cotacao is None:
        return None
    falta = cotacao.falta_para_frete_gratis
    return {
        "zona": cotacao.zona,
        "regiao": cotacao.regiao,
        "peso_cobrado_g": cotacao.peso_cobrado_g,
        "opcoes": [
            {
                "modalidade": opcao.modalidade,
                "nome": opcao.nome,
                "valor": formatar(opcao.valor),
                "valor_tabela": formatar(opcao.valor_tabela),
                "gratis": opcao.gratis,
                "prazo": opcao.prazo,
            }
            for opcao in cotacao.opcoes.values()
        ],
        "modalidade": totais.modalidade,
        "valor": formatar(totais.frete) if totais.frete is not None else None,
        "gratis": totais.frete_gratis,
        "minimo_gratis": formatar(cotacao.minimo_frete_gratis),
        "falta_para_gratis": formatar(falta) if falta > 0 else None,
    }


def carrinho_para_ui(loja, sessao):
    totais = loja.totais(sessao)
    cupom = None
    if totais.cupom:
        cupom = {
            "codigo": totais.cupom,
            "aplicado": totais.cupom_aplicado,
            "desconto": formatar(totais.desconto_cupom),
            "falta": formatar(totais.falta_para_cupom),
        }
    return {
        "vazio": totais.vazio,
        "quantidade_itens": totais.quantidade_itens,
        "itens": [
            {
                "produto_id": linha.produto.id,
                "nome": linha.produto.nome_curto,
                "imagem": linha.produto.imagem,
                "quantidade": linha.quantidade,
                "preco_unitario": formatar(linha.preco_unitario),
                "total": formatar(linha.total),
                "maximo": quantidade_maxima(loja.estoque[linha.produto.id]),
            }
            for linha in totais.linhas
        ],
        "subtotal": formatar(totais.subtotal),
        "cupom": cupom,
        "base": formatar(totais.base),
        "cep": formatar_cep(sessao.cep) if sessao.cep else None,
        "frete": _frete_para_ui(totais),
        "desconto_pix": formatar(totais.desconto_pix),
        "total_pix": formatar(totais.total_pix),
        "total_completo": totais.total_completo,
    }


def pedido_para_ui(pedido, agora, com_qr=True):
    dados = {
        "numero": pedido.numero,
        "status": pedido.status,
        "status_rotulo": ROTULOS_STATUS[pedido.status],
        "itens": [
            {
                "nome": item["nome"],
                "quantidade": item["quantidade"],
                "preco_unitario": formatar(item["preco_unitario"]),
                "total": formatar(item["total"]),
            }
            for item in pedido.itens
        ],
        "subtotal": formatar(pedido.subtotal),
        "cupom": pedido.cupom,
        "desconto_cupom": formatar(pedido.desconto_cupom),
        "frete": formatar(pedido.frete),
        "frete_gratis": pedido.frete_gratis,
        "modalidade": pedido.nome_modalidade,
        "prazo": pedido.prazo,
        "desconto_pix": formatar(pedido.desconto_pix),
        "total": formatar(pedido.total),
        "cliente": pedido.cliente,
        "cep": formatar_cep(pedido.cep),
        "copia_e_cola": pedido.copia_e_cola,
        "segundos_restantes": pedido.segundos_restantes(agora),
        "substituido_por": pedido.substituido_por,
    }
    if com_qr:
        dados["qr_code"] = pedido.qr_code_data_uri()
    return dados


def mensagem_para_ui(loja, mensagem):
    produtos = (loja.catalogo.obter(produto_id) for produto_id in mensagem["produtos"])
    return {
        "id": mensagem["id"],
        "autor": mensagem["autor"],
        "texto": mensagem["texto"],
        "quando": mensagem["quando"],
        "produtos": [cartao_produto(loja, p) for p in produtos if p is not None],
    }


def estado_para_ui(loja, sessao):
    pedido = sessao.ultimo_pedido()
    return {
        "sessao_id": sessao.id,
        "carrinho": carrinho_para_ui(loja, sessao),
        "cliente": sessao.cliente,
        "pedido": pedido_para_ui(pedido, loja.agora()) if pedido else None,
        "validade_pix_s": loja.validade_pix_s,
    }
