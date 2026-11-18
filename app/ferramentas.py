from dataclasses import dataclass, field

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
