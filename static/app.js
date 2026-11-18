"use strict";

// O navegador so fala com o backend deste projeto (/api/...). Nao existe
// chave nem chamada ao Gemini neste arquivo.

const CHAVE_SESSAO = "prohall_sofia_sessao";
const SUGESTOES = [
  "Meu cabelo está com muito frizz",
  "Estou com queda e quebra",
  "Tenho cachos e quero definição",
  "Quero ver os kits",
];

const app = {
  sessaoId: null,
  ultimaMensagem: 0,
  estado: null, // ultimo estado recebido do servidor
  aguardando: false, // esperando a resposta da Sofia
  pendentes: 0, // mensagens da cliente ja desenhadas antes da resposta do servidor
};

const $ = (id) => document.getElementById(id);

function el(tag, classe, texto) {
  const no = document.createElement(tag);
  if (classe) no.className = classe;
  if (texto !== undefined && texto !== null) no.textContent = texto;
  return no;
}

class ErroApi extends Error {
  constructor(codigo, mensagem, dados) {
    super(mensagem);
    this.codigo = codigo;
    this.dados = dados || {};
  }
}

// --- Mensagens ---

// o texto da Sofia pode ter **negrito**
function inline(texto, destino) {
  texto.split(/\*\*(.+?)\*\*/g).forEach((parte, indice) => {
    if (!parte) return;
    if (indice % 2 === 1) destino.appendChild(el("strong", "", parte));
    else destino.appendChild(document.createTextNode(parte));
  });
}

// converte o texto em paragrafos e listas com "-", sem usar innerHTML
function formatarTexto(texto) {
  const fragmento = document.createDocumentFragment();
  let lista = null;
  let paragrafo = null;
  for (const bruta of String(texto || "").split("\n")) {
    const linha = bruta.trimEnd();
    const item = linha.match(/^\s*[-*•]\s+(.*)$/);
    if (item) {
      if (!lista) {
        lista = el("ul");
        fragmento.appendChild(lista);
      }
      paragrafo = null;
      const li = el("li");
      inline(item[1], li);
      lista.appendChild(li);
      continue;
    }
    lista = null;
    if (!linha.trim()) {
      paragrafo = null;
      continue;
    }
    if (paragrafo) {
      paragrafo.appendChild(el("br"));
    } else {
      paragrafo = el("p");
      fragmento.appendChild(paragrafo);
    }
    inline(linha, paragrafo);
  }
  return fragmento;
}

function semImagem() {
  const vazio = el("div", "sem-imagem", "🧴");
  vazio.setAttribute("aria-hidden", "true");
  return vazio;
}

function criarImagem(src, alt) {
  if (!src) return semImagem();
  const imagem = el("img");
  imagem.alt = alt || "";
  imagem.loading = "lazy";
  imagem.referrerPolicy = "no-referrer";
  // se a imagem do site nao carregar, mostra um marcador no lugar
  imagem.addEventListener("error", () => imagem.replaceWith(semImagem()));
  imagem.src = src;
  return imagem;
}

function criarCard(produto) {
  const card = el("div", "card-produto");
  card.appendChild(criarImagem(produto.imagem, produto.nome_curto));
  const info = el("div", "card-info");
  info.appendChild(el("div", "card-nome", produto.nome));
  if (produto.conteudo) info.appendChild(el("div", "card-detalhe", produto.conteudo));
  const preco = el("div", "card-preco");
  if (produto.em_promocao) preco.appendChild(el("s", "", produto.preco));
  preco.appendChild(el("strong", "", produto.preco_vigente));
  info.appendChild(preco);
  if (produto.maximo > 0 && produto.estoque <= 3) {
    info.appendChild(el("div", "card-estoque", `Últimas ${produto.estoque} unidade(s) em estoque`));
  }
  const botao = el("button", "btn-primario", produto.maximo > 0 ? "Adicionar ao carrinho" : "Sem estoque");
  botao.type = "button";
  botao.disabled = produto.maximo <= 0;
  botao.addEventListener("click", () => adicionarAoCarrinho(produto, botao));
  info.appendChild(botao);
  card.appendChild(info);
  return card;
}

function desenharMensagem(mensagem) {
  const lista = $("mensagens");
  let no;
  if (mensagem.autor === "sistema") {
    no = el("div", "msg-sistema", mensagem.texto);
  } else {
    no = el("div", `msg msg-${mensagem.autor === "cliente" ? "cliente" : "sofia"}`);
    const balao = el("div", "balao");
    balao.appendChild(formatarTexto(mensagem.texto));
    no.appendChild(balao);
    if (mensagem.produtos && mensagem.produtos.length) {
      const cards = el("div", "cards");
      mensagem.produtos.forEach((produto) => cards.appendChild(criarCard(produto)));
      no.appendChild(cards);
    }
  }
  const digitando = $("digitando");
  if (digitando) lista.insertBefore(no, digitando);
  else lista.appendChild(no);
  lista.scrollTop = lista.scrollHeight;
  return no;
}

function mostrarDigitando() {
  const no = el("div", "msg msg-sofia");
  no.id = "digitando";
  const balao = el("div", "balao");
  const pontos = el("span", "digitando");
  pontos.setAttribute("aria-label", "Sofia está digitando");
  pontos.append(el("i"), el("i"), el("i"));
  balao.appendChild(pontos);
  no.appendChild(balao);
  $("mensagens").appendChild(no);
  $("mensagens").scrollTop = $("mensagens").scrollHeight;
  return no;
}

let temporizadorAviso = null;
function avisar(texto) {
  const aviso = $("aviso");
  aviso.textContent = texto;
  aviso.hidden = false;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => (aviso.hidden = true), 4500);
}
