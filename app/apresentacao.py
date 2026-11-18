from datetime import datetime

from .config import MODELO_GEMINI
from .dinheiro import formatar
from .frete import formatar_cep
from .loja import AGUARDANDO
from .regras import CUPOM, MINIMO_CUPOM, quantidade_maxima

ROTULOS_STATUS = {
    "aguardando_pagamento": "aguardando pagamento",
    "pago": "pago",
    "expirado": "expirado",
}

ROTULOS_USO = {
    "profissional": "uso profissional (informado na página do produto)",
    "home_care": "home care (uso em casa)",
    "nao_informado": "a página não informa se é profissional ou home care",
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


# o que vai pro modelo e sempre texto pronto (R$ 0,00): a Sofia so repete, nunca calcula

def _valor_frete(valor, gratis):
    return "GRÁTIS (R$ 0,00)" if gratis else formatar(valor)


def produto_para_modelo(loja, produto):
    estoque = loja.estoque[produto.id]
    dados = {
        "produto_id": produto.id,
        "nome": produto.nome_curto,
        "preco": formatar(produto.preco_vigente),
        "estoque": estoque,
        "maximo_por_pedido": quantidade_maxima(estoque),
    }
    if produto.em_promocao:
        dados["preco_cheio"] = formatar(produto.preco)
    return dados


def totais_para_modelo(totais, cep=None):
    """Resumo do carrinho (ou de uma simulacao) com os valores prontos."""
    dados = {
        "itens": [
            {
                "produto_id": linha.produto.id,
                "nome": linha.produto.nome_curto,
                "quantidade": linha.quantidade,
                "preco_unitario": formatar(linha.preco_unitario),
                "total_do_item": formatar(linha.total),
            }
            for linha in totais.linhas
        ],
        "subtotal": formatar(totais.subtotal),
    }
    if totais.cupom_aplicado:
        dados["cupom"] = f"{totais.cupom} aplicado: -{formatar(totais.desconto_cupom)}"
    elif totais.cupom:
        dados["cupom"] = (
            f"{totais.cupom} registrado, mas SEM VALER: o subtotal está abaixo de {formatar(MINIMO_CUPOM)} "
            f"(faltam {formatar(totais.falta_para_cupom)})"
        )
    else:
        dados["cupom"] = "nenhum"
    dados["base_dos_produtos_apos_cupom"] = formatar(totais.base)
    dados["desconto_pix_5_por_cento"] = f"-{formatar(totais.desconto_pix)}"
    dados["produtos_com_desconto_pix"] = formatar(totais.produtos_no_pix)

    cotacao = totais.cotacao
    if cotacao is None:
        dados["frete"] = "não calculado" if cep else "não calculado (falta o CEP)"
        dados["total_no_pix_sem_frete"] = formatar(totais.total_pix)
        return dados

    dados["cep"] = formatar_cep(cotacao.cep)
    dados["zona"] = f"{cotacao.zona} ({cotacao.regiao})"
    dados["opcoes_de_frete"] = [
        {
            "modalidade": opcao.nome,
            "valor": _valor_frete(opcao.valor, opcao.gratis),
            "prazo": opcao.prazo,
            "total_no_pix_com_esta_modalidade": formatar(totais.produtos_no_pix + opcao.valor),
        }
        for opcao in cotacao.opcoes.values()
    ]
    if cotacao.falta_para_frete_gratis > 0:
        dados["frete_gratis_na_economica"] = (
            f"faltam {formatar(cotacao.falta_para_frete_gratis)} em produtos para atingir "
            f"{formatar(cotacao.minimo_frete_gratis)}"
        )
    else:
        dados["frete_gratis_na_economica"] = "atingido"
    if totais.total_completo:
        escolhida = cotacao.opcoes[totais.modalidade]
        dados["frete_escolhido"] = {
            "modalidade": escolhida.nome,
            "valor": _valor_frete(escolhida.valor, escolhida.gratis),
            "prazo": escolhida.prazo,
        }
        dados["total_no_pix"] = formatar(totais.total_pix)
    else:
        dados["frete_escolhido"] = "nenhum (a cliente ainda precisa escolher Econômica ou Expressa)"
        dados["total_no_pix_sem_frete"] = formatar(totais.total_pix)
    return dados


def pedido_para_modelo(pedido, agora):
    dados = {
        "numero": pedido.numero,
        "status": ROTULOS_STATUS[pedido.status],
        "itens": [f"{item['quantidade']}x {item['nome']} ({formatar(item['total'])})" for item in pedido.itens],
        "subtotal": formatar(pedido.subtotal),
        "cupom": f"{pedido.cupom}: -{formatar(pedido.desconto_cupom)}" if pedido.cupom else "nenhum",
        "frete": f"{pedido.nome_modalidade}: {_valor_frete(pedido.frete, pedido.frete_gratis)}, prazo de {pedido.prazo}",
        "desconto_pix": f"-{formatar(pedido.desconto_pix)}",
        "total": formatar(pedido.total),
        "entrega": f"{pedido.cliente['endereco']}, {pedido.cliente['numero']} — CEP {formatar_cep(pedido.cep)}",
    }
    if pedido.status == AGUARDANDO:
        restante = pedido.segundos_restantes(agora)
        dados["pix_expira_em"] = f"{restante // 60} min {restante % 60:02d} s"
    if pedido.substituido_por:
        dados["substituido_por"] = pedido.substituido_por
    return dados


# textos que entram no prompt da Sofia

def _preco_do_catalogo(produto):
    if not produto.em_promocao:
        return formatar(produto.preco)
    economia = formatar(produto.preco - produto.preco_vigente)
    return f"de {formatar(produto.preco)} por {formatar(produto.preco_vigente)} (economia de {economia})"


def texto_catalogo(loja):
    blocos = []
    for produto in loja.catalogo.listar():
        estoque = loja.estoque[produto.id]
        uso = ROTULOS_USO.get(produto.uso, ROTULOS_USO["nao_informado"])
        blocos.append(
            "\n".join(
                [
                    f"## {produto.nome_curto}  [id: {produto.id}]",
                    f"- nome completo no site: {produto.nome}",
                    f"- categoria: {produto.categoria} | linha: {produto.linha} | é kit: {'sim' if produto.kit else 'não'}",
                    f"- uso: {uso}",
                    f"- preço: {_preco_do_catalogo(produto)}",
                    f"- conteúdo: {produto.conteudo}",
                    f"- estoque agora: {estoque} un. (máximo por pedido: {quantidade_maxima(estoque)})",
                    f"- indicação: {produto.indicacao}",
                    f"- benefícios: {'; '.join(produto.beneficios) or 'não informados na página'}",
                    f"- ativos citados na página: {'; '.join(produto.ativos) or 'a página não cita'}",
                    f"- modo de uso: {produto.modo_de_uso}",
                    f"- observações: {produto.observacoes}",
                ]
            )
        )
    return "\n\n".join(blocos)


def _linhas_do_carrinho(totais, cep):
    linhas = ["Carrinho:"]
    resumo = totais_para_modelo(totais, cep)
    for item in resumo.pop("itens"):
        linhas.append(
            f"- {item['quantidade']}x {item['nome']} [id: {item['produto_id']}] — "
            f"{item['preco_unitario']} cada — {item['total_do_item']}"
        )
    for chave, valor in resumo.items():
        if chave == "opcoes_de_frete":
            for opcao in valor:
                linhas.append(
                    f"- frete {opcao['modalidade']}: {opcao['valor']}, {opcao['prazo']} "
                    f"(total no PIX com ela: {opcao['total_no_pix_com_esta_modalidade']})"
                )
        elif chave == "frete_escolhido" and isinstance(valor, dict):
            linhas.append(f"- frete escolhido: {valor['modalidade']} — {valor['valor']} — {valor['prazo']}")
        else:
            linhas.append(f"- {chave.replace('_', ' ')}: {valor}")
    return linhas


def texto_estado(loja, sessao):
    """Bloco ESTADO ATUAL do prompt: a fonte de verdade sobre carrinho e pedidos."""
    totais = loja.totais(sessao)
    if totais.vazio:
        linhas = ["Carrinho: vazio."]
        if sessao.cep:
            linhas.append(f"CEP informado: {formatar_cep(sessao.cep)}.")
    else:
        linhas = _linhas_do_carrinho(totais, sessao.cep)

    if not totais.cupom:
        situacao = ""
        if not totais.vazio:
            if totais.subtotal >= MINIMO_CUPOM:
                situacao = " O subtotal atual já permite usar; ofereça à cliente."
            else:
                situacao = f" Faltam {formatar(MINIMO_CUPOM - totais.subtotal)} no subtotal para poder usar."
        linhas.append(f"Cupom disponível: {CUPOM} (10% com subtotal a partir de {formatar(MINIMO_CUPOM)}).{situacao}")

    if sessao.cliente:
        c = sessao.cliente
        complemento = f", {c['complemento']}" if c.get("complemento") else ""
        linhas.append(
            f"Dados já informados pela cliente: nome {c['nome']}; e-mail {c['email']}; "
            f"CEP {formatar_cep(c['cep'])}; endereço {c['endereco']}, nº {c['numero']}{complemento}."
        )

    if not sessao.pedidos:
        linhas.append("Pedidos desta conversa: nenhum ainda.")
        return "\n".join(linhas)

    linhas.append("Pedidos desta conversa (do mais antigo para o mais recente):")
    agora = loja.agora()
    for pedido in sessao.pedidos:
        dados = pedido_para_modelo(pedido, agora)
        extra = ""
        if "pix_expira_em" in dados:
            extra = f" — PIX expira em {dados['pix_expira_em']}"
        if pedido.substituido_por:
            extra += f" — substituído por {pedido.substituido_por}"
        linhas.append(
            f"- {pedido.numero}: {dados['status']} — total {dados['total']} — "
            f"{'; '.join(dados['itens'])} — frete {dados['frete']}{extra}"
        )
    linhas.append("(Avisos automáticos de pagamento confirmado e de PIX expirado já são enviados no chat pelo sistema.)")
    return "\n".join(linhas)


# exportacao da conversa (entregavel do teste)

AUTORES = {"sofia": "Sofia", "cliente": "Cliente", "sistema": "(sistema)"}


def exportar_conversa(loja, sessao):
    linhas = [
        "Conversa com a Sofia — vendedora virtual da Prohall (AMBIENTE DE TESTE)",
        f"Modelo: {MODELO_GEMINI}",
    ]
    if sessao.mensagens:
        inicio = datetime.fromisoformat(sessao.mensagens[0]["quando"])
        linhas.append(f"Início: {inicio.strftime('%d/%m/%Y %H:%M')}")
    linhas.append("=" * 72)

    for mensagem in sessao.mensagens:
        hora = datetime.fromisoformat(mensagem["quando"]).strftime("%H:%M:%S")
        autor = AUTORES.get(mensagem["autor"], mensagem["autor"])
        linhas.append("")
        if mensagem["autor"] == "sistema":
            linhas.append(f"[{hora}] {autor} {mensagem['texto']}")
            continue
        linhas += [f"[{hora}] {autor}:", mensagem["texto"]]
        produtos = (loja.catalogo.obter(produto_id) for produto_id in mensagem["produtos"])
        cartoes = [f"{p.nome_curto} ({formatar(p.preco_vigente)})" for p in produtos if p is not None]
        if cartoes:
            linhas.append("  [cards exibidos no chat: " + " | ".join(cartoes) + "]")

    if sessao.pedidos:
        linhas += ["", "=" * 72, "Pedidos desta conversa:"]
        for pedido in sessao.pedidos:
            linhas.append(
                f"- {pedido.numero} — {ROTULOS_STATUS[pedido.status]} — total {formatar(pedido.total)} — "
                f"{pedido.copia_e_cola}"
            )
    return "\n".join(linhas) + "\n"
