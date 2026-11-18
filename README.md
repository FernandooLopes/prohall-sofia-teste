# Sofia, vendedora virtual da Prohall

Um chat de vendas com a **Sofia**, uma consultora de beleza feita com IA (Gemini). Ela entende o que a cliente precisa, indica produtos, calcula o frete, monta o carrinho e leva até o pagamento por **PIX de teste**.

A Sofia só conversa. Preço, cupom, frete, estoque e pedido são calculados pelo código, e ela apenas repete os valores certos.

> **Ambiente de teste:** nenhum pagamento é real. O QR Code e o "copia e cola" são fictícios.

## Como rodar

Você precisa do **Python 3.10 ou mais novo** e da chave do Gemini que veio com o teste.

No PowerShell (Windows):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Abra o arquivo `.env` e coloque a chave depois de `GEMINI_API_KEY=`. Depois:

```powershell
python -m uvicorn app.main:app --port 8000
```

Abra **http://localhost:8000** no navegador.

No Mac ou Linux, troque os comandos do começo por:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Se o PowerShell não deixar ativar o ambiente, rode `Set-ExecutionPolicy -Scope Process RemoteSigned` e tente de novo.

## Testes

```bash
python -m pytest
```

Os testes não usam internet nem a chave: o Gemini é substituído por uma versão falsa.

## A chave do Gemini

- Fica só no arquivo `.env`, que **não vai para o git** (está no `.gitignore`).
- O repositório traz apenas o `.env.example`, sem chave.
- Só o servidor fala com o Gemini. O navegador fala só com as rotas `/api/...` do próprio projeto.
- A chave nunca aparece em URL, log, mensagem de erro nem resposta da API. Há testes que conferem isso.

Também dá para ajustar (opcional, no `.env`):

| Variável | Para que serve |
|---|---|
| `GEMINI_THINKING_LEVEL` | Nível de raciocínio: `low` (padrão), `medium` ou `high`. |
| `PIX_VALIDADE_SEGUNDOS` | Validade do PIX. Padrão 900 (15 minutos). Use `60` para testar a expiração rápido. |

## Como o projeto é organizado

| Arquivo | O que faz |
|---|---|
| `data/catalogo.json` | Os 15 produtos. |
| `app/frete.py` | Zona pelo CEP, faixas de peso, tabela de frete e frete grátis. |
| `app/regras.py` | Subtotal, cupom, desconto PIX, total e limites de quantidade. |
| `app/loja.py` | Carrinho, estoque, pedido e PIX falso. |
| `app/ferramentas.py` | As ações que a Sofia pode pedir (adicionar ao carrinho, calcular frete...). |
| `app/sofia.py` | A conversa com o Gemini. |
| `app/prompts.py` | As instruções da Sofia. |
| `app/gemini.py` | A chamada à API do Gemini. |
| `app/apresentacao.py` | Prepara os dados para a tela e para a Sofia. |
| `app/main.py` | As rotas do servidor. |
| `static/` | A tela: HTML, CSS e JavaScript. |
| `tests/` | Os testes. |

## Como a Sofia não inventa valores

- Ela não faz conta. Quando precisa de um total, chama uma ferramenta e repete o valor que veio dela.
- A cada resposta ela recebe de novo o catálogo e a situação atual do carrinho e dos pedidos.
- Antes de enviar, o sistema confere se todo valor em reais da resposta veio do catálogo, das ferramentas ou da própria cliente. Se aparecer um valor desconhecido, a resposta é descartada e refeita uma vez.

## Pedido pela conversa ou pelo formulário

Os dois caminhos usam a mesma função (`criar_pedido`), com as mesmas regras. Por isso o pedido sai igual nos dois.

## Decisões que tomei junto com a IA

1. **Arredondamento:** meio para cima, em 2 casas, ao fim de cada etapa.
2. **Centavo do PIX:** o total segue a fórmula do enunciado (`base × 0,95 + frete`), e o desconto mostrado é a diferença. Assim a conta fecha no centavo. Exemplo: base 79,90 → produtos no PIX 75,91 e desconto 3,99.
3. **Cupom:** aceita maiúsculas e minúsculas. Se o subtotal cair abaixo de R$ 150, o cupom deixa de valer e volta a valer se o subtotal subir de novo.
4. **CEP:** 8 dígitos, com ou sem hífen. De `00000-000` a `00999-999` o CEP é inválido, porque a tabela do enunciado não cobre essa faixa.
5. **CEP diferente na hora de fechar:** se o CEP do formulário for diferente do CEP do frete calculado, o frete é recalculado e a cliente confirma antes de gerar o PIX.
6. **Frete no total:** só entra depois que há CEP e modalidade escolhida. O frete grátis considera os produtos depois do cupom e antes do desconto PIX.
7. **Estoque:** fictício e guardado em memória. O máximo por item é o menor entre o estoque e 10. O estoque é reservado ao criar o pedido, devolvido se o PIX expirar e mantido baixado se for pago.
8. **Pedido:** ao gerar o PIX o carrinho esvazia. Os números são `PH-TESTE-000001`, `000002`... Se o PIX expira, "Gerar novo PIX" cria outro pedido com os mesmos itens.
9. **Checkout:** nome com 3 letras ou mais, e-mail válido, CEP válido, endereço e número preenchidos. O complemento é opcional.
10. **Modelo:** fixo em `gemini-3.8-flash` no código. A chamada é feita direto pela API.
11. **Dados em memória:** se o servidor reiniciar, as conversas, pedidos e estoque voltam ao começo.

## Catálogo

Os 15 produtos foram copiados de [lojaprohall.com.br](https://lojaprohall.com.br). **Os preços foram copiados em 16/11/2026**, e nessa data todos estavam em promoção.

- Nome, preços, imagem, peso e descrição vêm da página de cada produto.
- O peso é o cadastrado no site. Nenhum precisou ser estimado.
- A categoria é o "tipo de produto" do site. Só o Shampoo Absolut One não tinha, e a categoria dele foi deduzida pelo nome.
- Uso profissional ou home care só está marcado quando a página diz.
- O **estoque é fictício**.

Produtos: Tônico Force Hair, Select One, Fluido PRO.R, Leave-in Secar sem Frizz, Óleo Absolut Oil, Kit Equalize, Shampoo Force Hair, Máscara Force Hair, Kit Cachos Raízes & Vibes, Gelatina de Cachos, Shampoo Absolut One, Kit Extreme Repair Home Care, Btx Blend Repair, Kit Encorpax e Finalizador Absolut One.

## Conversas de exemplo

A pasta `conversas/` traz 3 conversas exportadas com perfis diferentes:

- `01-indecisa.txt`: cliente que não sabe o que comprar, até o PIX pago.
- `02-objetiva.txt`: cliente que já sabe o que quer, com cupom e frete grátis.
- `03-teste-limites.txt`: cliente que tenta quebrar a Sofia (cupom falso, desconto inventado, preço errado, CEP inválido, pedido fora do escopo).

## O que ficou de fora

- Banco de dados (tudo fica em memória).
- Cancelar ou editar um pedido depois do PIX.
- Buscar o endereço pelo CEP.
- Limite de uso e proteção contra abuso.
- Login, painel de administração e controle real de estoque.
