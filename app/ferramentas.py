import logging
from dataclasses import dataclass, field

from .apresentacao import pedido_para_modelo, produto_para_modelo, totais_para_modelo
from .frete import formatar_cep
from .regras import ErroRegra

log = logging.getLogger("sofia.ferramentas")

MAX_CARDS_POR_TURNO = 6


@dataclass
class EfeitosTurno:
    """O que as ferramentas pediram pra interface fazer neste turno."""

    produtos: list = field(default_factory=list)  # ids dos cards a exibir
    abrir_checkout: bool = False
    pedido: str | None = None  # pedido criado ou renovado: a interface abre o PIX


def _texto(descricao):
    return {"type": "STRING", "description": descricao}


ID_PRODUTO = _texto("Id do produto exatamente como aparece no catálogo (ex.: tonico-force-hair-120ml).")
QUANTIDADE = {"type": "INTEGER", "description": "Quantidade de unidades (inteiro, de 1 a 10)."}


def _ferramenta(nome, descricao, propriedades=None, obrigatorios=None):
    ferramenta = {"name": nome, "description": descricao}
    if propriedades:
        ferramenta["parameters"] = {"type": "OBJECT", "properties": propriedades}
        if obrigatorios:
            ferramenta["parameters"]["required"] = obrigatorios
    return ferramenta


DECLARACOES = [
    _ferramenta(
        "mostrar_produtos",
        "Exibe no chat os cards dos produtos (imagem, nome, preço e botão de adicionar ao carrinho). "
        "Use sempre que indicar, comparar ou citar produtos para a cliente.",
        {
            "produto_ids": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Ids dos produtos do catálogo a exibir (de 1 a 6).",
            }
        },
        ["produto_ids"],
    ),
    _ferramenta(
        "adicionar_ao_carrinho",
        "Adiciona unidades de um produto ao carrinho (soma ao que já estiver lá).",
        {"produto_id": ID_PRODUTO, "quantidade": QUANTIDADE},
        ["produto_id", "quantidade"],
    ),
    _ferramenta(
        "alterar_quantidade",
        "Define a quantidade total de um produto que já está no carrinho (0 remove o item).",
        {
            "produto_id": ID_PRODUTO,
            "quantidade": {"type": "INTEGER", "description": "Nova quantidade total (0 a 10)."},
        },
        ["produto_id", "quantidade"],
    ),
    _ferramenta("remover_do_carrinho", "Remove um produto do carrinho.", {"produto_id": ID_PRODUTO}, ["produto_id"]),
    _ferramenta(
        "ver_carrinho",
        "Devolve o carrinho atual com subtotal, cupom, frete, desconto PIX e total calculados.",
    ),
    _ferramenta(
        "aplicar_cupom",
        "Tenta aplicar um código de cupom ao carrinho. O sistema valida o código e o pedido mínimo.",
        {"codigo": _texto("Código do cupom exatamente como a cliente informou.")},
        ["codigo"],
    ),
    _ferramenta("remover_cupom", "Remove o cupom aplicado ao carrinho."),
    _ferramenta(
        "calcular_frete",
        "Valida o CEP de entrega, guarda-o no pedido e devolve as modalidades de frete (valor e prazo) "
        "para o carrinho atual. Aceita CEP com ou sem hífen.",
        {"cep": _texto("CEP informado pela cliente, com 8 dígitos (ex.: 01310-100).")},
        ["cep"],
    ),
    _ferramenta(
        "escolher_frete",
        "Registra a modalidade de frete escolhida pela cliente. Exige CEP já calculado.",
        {"modalidade": _texto("Modalidade escolhida: 'economica' ou 'expressa'.")},
        ["modalidade"],
    ),
    _ferramenta(
        "simular_pedido",
        "Calcula subtotal, cupom, frete e total para uma lista hipotética de produtos SEM alterar o carrinho. "
        "Use para responder 'quanto fica se eu levar X e Y?' ou estimar frete antes de adicionar.",
        {
            "itens": {
                "type": "ARRAY",
                "description": "Produtos e quantidades a simular.",
                "items": {
                    "type": "OBJECT",
                    "properties": {"produto_id": ID_PRODUTO, "quantidade": QUANTIDADE},
                    "required": ["produto_id", "quantidade"],
                },
            },
            "cep": _texto("CEP para simular o frete (opcional)."),
            "cupom": _texto("Código de cupom a considerar na simulação (opcional)."),
        },
        ["itens"],
    ),
    _ferramenta(
        "abrir_checkout",
        "Abre na tela da cliente o formulário de checkout (dados e endereço) com o resumo do pedido. "
        "Use quando ela preferir preencher o formulário em vez de informar os dados pelo chat.",
    ),
    _ferramenta(
        "finalizar_pedido",
        "Fecha o pedido com os dados que a cliente informou e gera o PIX de teste (número do pedido, "
        "QR Code e copia e cola aparecem na tela). Só chame depois de mostrar o resumo e a cliente confirmar.",
        {
            "nome": _texto("Nome completo informado pela cliente."),
            "email": _texto("E-mail informado pela cliente."),
            "cep": _texto("CEP de entrega."),
            "endereco": _texto("Rua/avenida do endereço de entrega."),
            "numero": _texto("Número do endereço (ou 's/n')."),
            "complemento": _texto("Complemento do endereço (opcional; vazio se não houver)."),
        },
        ["nome", "email", "cep", "endereco", "numero"],
    ),
    _ferramenta(
        "consultar_pedido",
        "Consulta o status atual de um pedido desta conversa (aguardando pagamento, pago ou expirado).",
        {"numero": _texto("Número do pedido (opcional; sem ele, usa o mais recente).")},
    ),
    _ferramenta(
        "gerar_novo_pix",
        "Gera um novo PIX de teste, com os mesmos itens, para um pedido cujo PIX expirou.",
        {"numero": _texto("Número do pedido expirado (opcional; sem ele, usa o último expirado).")},
    ),
]


# cada executor recebe (loja, sessao, args, efeitos) e devolve um dict simples
# pro modelo. Erro de regra vira ErroRegra e e tratado em executar().

def _carrinho(loja, sessao):
    return totais_para_modelo(loja.totais(sessao), sessao.cep)


def _mostrar_produtos(loja, sessao, args, efeitos):
    encontrados, inexistentes = [], []
    for produto_id in args.get("produto_ids") or []:
        produto = loja.catalogo.obter(produto_id)
        if produto is None:
            inexistentes.append(str(produto_id))
            continue
        encontrados.append(produto_para_modelo(loja, produto))
        if produto.id not in efeitos.produtos and len(efeitos.produtos) < MAX_CARDS_POR_TURNO:
            efeitos.produtos.append(produto.id)
    resultado = {"ok": bool(encontrados), "cards_exibidos": encontrados}
    if inexistentes:
        resultado["ids_inexistentes"] = inexistentes
        resultado["aviso"] = "Esses ids não existem no catálogo; não cite esses produtos."
    return resultado


def _adicionar(loja, sessao, args, efeitos):
    produto = loja.adicionar_item(sessao, args.get("produto_id"), args.get("quantidade", 1))
    return {"ok": True, "adicionado": produto.nome_curto, "carrinho": _carrinho(loja, sessao)}


def _alterar(loja, sessao, args, efeitos):
    produto = loja.definir_quantidade(sessao, args.get("produto_id"), args.get("quantidade"))
    return {"ok": True, "alterado": produto.nome_curto, "carrinho": _carrinho(loja, sessao)}


def _remover(loja, sessao, args, efeitos):
    produto = loja.remover_item(sessao, args.get("produto_id"))
    return {"ok": True, "removido": produto.nome_curto, "carrinho": _carrinho(loja, sessao)}


def _ver_carrinho(loja, sessao, args, efeitos):
    return {"ok": True, "carrinho": _carrinho(loja, sessao) if sessao.itens else "vazio"}


def _aplicar_cupom(loja, sessao, args, efeitos):
    codigo = loja.aplicar_cupom(sessao, args.get("codigo"))
    return {"ok": True, "cupom_aplicado": codigo, "carrinho": _carrinho(loja, sessao)}


def _remover_cupom(loja, sessao, args, efeitos):
    loja.remover_cupom(sessao)
    return {"ok": True, "carrinho": _carrinho(loja, sessao) if sessao.itens else "vazio"}


def _calcular_frete(loja, sessao, args, efeitos):
    cep = loja.definir_cep(sessao, args.get("cep"))
    if not sessao.itens:
        return {
            "ok": True,
            "cep": formatar_cep(cep),
            "aviso": (
                "CEP válido e guardado, mas o carrinho está vazio: o valor do frete depende do peso dos "
                "produtos. Adicione itens ou use simular_pedido para estimar."
            ),
        }
    return {"ok": True, "carrinho": _carrinho(loja, sessao)}


def _escolher_frete(loja, sessao, args, efeitos):
    loja.escolher_modalidade(sessao, args.get("modalidade"))
    if not sessao.itens:
        return {"ok": True, "aviso": "Modalidade registrada, mas o carrinho está vazio."}
    return {"ok": True, "carrinho": _carrinho(loja, sessao)}


def _simular(loja, sessao, args, efeitos):
    cep = args.get("cep") or sessao.cep
    totais = loja.simular(args.get("itens") or [], cep, args.get("cupom"))
    return {
        "ok": True,
        "aviso": "Simulação: o carrinho da cliente NÃO foi alterado.",
        "simulacao": totais_para_modelo(totais, cep),
    }


def _abrir_checkout(loja, sessao, args, efeitos):
    if not sessao.itens:
        raise ErroRegra("carrinho_vazio", "O carrinho está vazio: adicione produtos antes de abrir o checkout.")
    efeitos.abrir_checkout = True
    return {
        "ok": True,
        "mensagem": (
            "O formulário de checkout abriu na tela da cliente, com o resumo do pedido. Ela preenche os dados "
            "(fictícios), escolhe o frete e clica em gerar o PIX de teste."
        ),
    }


def _finalizar(loja, sessao, args, efeitos):
    pedido = loja.criar_pedido(sessao, args, origem="conversa")
    efeitos.pedido = pedido.numero
    return {
        "ok": True,
        "pedido": pedido_para_modelo(pedido, loja.agora()),
        "mensagem": (
            "Pedido criado. O QR Code e o copia e cola de TESTE apareceram na tela da cliente, com o botão "
            "'Simular pagamento'. Não escreva código PIX no chat."
        ),
    }


def _consultar_pedido(loja, sessao, args, efeitos):
    loja.atualizar_pedidos(sessao)
    numero = args.get("numero")
    pedido = sessao.pedido(numero) if numero else sessao.ultimo_pedido()
    if pedido is None:
        raise ErroRegra("pedido_nao_encontrado", "Não há pedido com esse número nesta conversa.")
    return {"ok": True, "pedido": pedido_para_modelo(pedido, loja.agora())}


def _novo_pix(loja, sessao, args, efeitos):
    pedido = loja.gerar_novo_pix(sessao, args.get("numero"), origem="conversa")
    efeitos.pedido = pedido.numero
    return {
        "ok": True,
        "pedido": pedido_para_modelo(pedido, loja.agora()),
        "mensagem": "Novo PIX de teste gerado; o painel do PIX reabriu na tela da cliente.",
    }


EXECUTORES = {
    "mostrar_produtos": _mostrar_produtos,
    "adicionar_ao_carrinho": _adicionar,
    "alterar_quantidade": _alterar,
    "remover_do_carrinho": _remover,
    "ver_carrinho": _ver_carrinho,
    "aplicar_cupom": _aplicar_cupom,
    "remover_cupom": _remover_cupom,
    "calcular_frete": _calcular_frete,
    "escolher_frete": _escolher_frete,
    "simular_pedido": _simular,
    "abrir_checkout": _abrir_checkout,
    "finalizar_pedido": _finalizar,
    "consultar_pedido": _consultar_pedido,
    "gerar_novo_pix": _novo_pix,
}


def executar(loja, sessao, nome, args, efeitos):
    """Roda a ferramenta pedida pelo modelo e devolve um dict pronto pra voltar a ele."""
    executor = EXECUTORES.get(nome)
    if executor is None:
        return {"ok": False, "erro": "ferramenta_inexistente", "mensagem": f"A ferramenta '{nome}' não existe."}
    if not isinstance(args, dict):
        args = {}
    try:
        return executor(loja, sessao, args, efeitos)
    except ErroRegra as erro:
        resultado = erro.como_dict()
        if sessao.itens:
            resultado["carrinho"] = _carrinho(loja, sessao)
        return resultado
    except Exception:  # falha inesperada nao pode derrubar a conversa
        log.exception("Erro inesperado na ferramenta %s", nome)
        return {
            "ok": False,
            "erro": "erro_interno",
            "mensagem": "A operação falhou por um erro interno. Peça desculpas e tente novamente.",
        }
