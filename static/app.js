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
  rascunho: { cupom: "", cep: "" }, // o que ela digitou e ainda nao aplicou
  erros: { cupom: "", cep: "" },
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

// --- Comunicacao com o backend ---

async function chamar(rota, corpo = {}, metodo = "POST") {
  let url = rota;
  const opcoes = { method: metodo, headers: {} };
  const base = { sessao_id: app.sessaoId || "", ultima_mensagem: app.ultimaMensagem };
  if (metodo === "GET") {
    url += "?" + new URLSearchParams({ ...base, ...corpo }).toString();
  } else {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify({ ...base, ...corpo });
  }

  let resposta;
  try {
    resposta = await fetch(url, opcoes);
  } catch (erro) {
    throw new ErroApi("rede", "Não consegui falar com o servidor. Confira se ele está rodando.");
  }
  let dados = null;
  try {
    dados = await resposta.json();
  } catch (erro) {
    dados = null;
  }
  if (resposta.status === 404 && dados && dados.erro === "sessao_inexistente") {
    await iniciarSessao(true);
    throw new ErroApi("sessao_inexistente", "A conversa anterior não existe mais no servidor; comecei uma nova.");
  }
  if (dados) aplicar(dados);
  if (!resposta.ok || !dados || dados.ok === false) {
    const mensagem = (dados && dados.mensagem) || "Algo deu errado. Tente de novo.";
    throw new ErroApi((dados && dados.erro) || "erro", mensagem, dados);
  }
  return dados;
}

// aplica na tela o que o servidor devolveu: mensagens novas, estado e acoes
function aplicar(dados) {
  for (const mensagem of dados.mensagens || []) {
    if (mensagem.id <= app.ultimaMensagem) continue;
    app.ultimaMensagem = mensagem.id;
    if (mensagem.autor === "cliente" && app.pendentes > 0) {
      app.pendentes -= 1; // essa ja foi desenhada na hora do envio
      continue;
    }
    desenharMensagem(mensagem);
  }
  if (dados.estado) {
    app.estado = dados.estado;
    sincronizarPix();
    desenharCarrinho();
    if (!$("modal-checkout").hidden) desenharCheckout();
    if (!$("modal-pix").hidden) desenharPix();
  }
  const acoes = dados.acoes || {};
  if (acoes.abrir_pix) {
    fecharModal("modal-checkout");
    abrirPix();
  } else if (acoes.abrir_checkout) {
    abrirCheckout();
  }
}

// roda uma chamada dos botoes; se falhar mostra o aviso (ou chama aoFalhar)
async function executar(rota, corpo, aoFalhar) {
  try {
    return await chamar(rota, corpo);
  } catch (erro) {
    if (aoFalhar) aoFalhar(erro);
    else avisar(erro.message);
    return null;
  }
}

// --- Chat ---

function mostrarSugestoes() {
  const area = $("sugestoes");
  area.replaceChildren();
  if (app.ultimaMensagem > 1) return; // so no comeco da conversa
  SUGESTOES.forEach((texto) => {
    const chip = el("button", "chip", texto);
    chip.type = "button";
    chip.addEventListener("click", () => enviarMensagem(texto));
    area.appendChild(chip);
  });
}

async function enviarMensagem(texto) {
  texto = String(texto || "").trim();
  if (!texto || app.aguardando) return;
  app.aguardando = true;
  $("btn-enviar").disabled = true;
  $("sugestoes").replaceChildren();
  const bolha = desenharMensagem({ autor: "cliente", texto, produtos: [] });
  app.pendentes += 1;
  const digitando = mostrarDigitando();
  try {
    await chamar("/api/chat", { mensagem: texto });
  } catch (erro) {
    if (app.pendentes > 0) {
      app.pendentes -= 1;
      bolha.classList.add("msg-falhou");
    }
    avisar(erro.message);
  } finally {
    digitando.remove();
    app.aguardando = false;
    $("btn-enviar").disabled = false;
    $("mensagens").scrollTop = $("mensagens").scrollHeight;
    $("campo-mensagem").focus();
  }
}

async function adicionarAoCarrinho(produto, botao) {
  botao.disabled = true;
  const dados = await executar("/api/carrinho/adicionar", { produto_id: produto.id, quantidade: 1 });
  botao.disabled = false;
  if (dados) {
    const original = botao.textContent;
    botao.textContent = "✓ Adicionado";
    setTimeout(() => (botao.textContent = original), 1600);
  }
}

// --- Carrinho ---

function linhaItem(item) {
  const linha = el("div", "item");
  linha.appendChild(criarImagem(item.imagem, ""));
  const meio = el("div");
  meio.appendChild(el("div", "item-nome", item.nome));
  meio.appendChild(el("div", "item-preco", `${item.preco_unitario} cada`));
  linha.appendChild(meio);

  const mudar = (quantidade) => executar("/api/carrinho/quantidade", { produto_id: item.produto_id, quantidade });
  const direita = el("div", "item-direita");
  direita.appendChild(el("div", "item-total", item.total));
  const quantidade = el("div", "quantidade");
  const menos = el("button", "", "−");
  menos.type = "button";
  menos.setAttribute("aria-label", `Diminuir ${item.nome}`);
  menos.addEventListener("click", () => mudar(item.quantidade - 1));
  const mais = el("button", "", "+");
  mais.type = "button";
  mais.setAttribute("aria-label", `Aumentar ${item.nome}`);
  mais.disabled = item.quantidade >= item.maximo;
  mais.title = mais.disabled ? `Máximo de ${item.maximo} unidade(s)` : "";
  mais.addEventListener("click", () => mudar(item.quantidade + 1));
  quantidade.append(menos, el("span", "", String(item.quantidade)), mais);
  direita.appendChild(quantidade);
  const remover = el("button", "btn-link", "remover");
  remover.type = "button";
  remover.addEventListener("click", () => executar("/api/carrinho/remover", { produto_id: item.produto_id }));
  direita.appendChild(remover);
  linha.appendChild(direita);
  return linha;
}

// campo de texto com botao ao lado (usado no cupom e no CEP)
function formularioCurto(placeholder, rotulo, botaoTexto, rascunho) {
  const formulario = el("form", "linha-form");
  const campo = el("input");
  campo.type = "text";
  campo.placeholder = placeholder;
  campo.setAttribute("aria-label", rotulo);
  campo.value = app.rascunho[rascunho] || "";
  campo.addEventListener("input", () => (app.rascunho[rascunho] = campo.value));
  const botao = el("button", "btn-leve", botaoTexto);
  botao.type = "submit";
  formulario.append(campo, botao);
  return { formulario, campo };
}

function blocoCupom(carrinho) {
  const bloco = el("div");
  bloco.appendChild(el("h3", "", "Cupom"));
  const cupom = carrinho.cupom;
  if (cupom) {
    const etiqueta = el("div", cupom.aplicado ? "etiqueta" : "etiqueta suspenso");
    const texto = cupom.aplicado
      ? `${cupom.codigo} aplicado (−${cupom.desconto})`
      : `${cupom.codigo} sem valer: faltam ${cupom.falta} no subtotal`;
    etiqueta.appendChild(el("span", "", texto));
    const remover = el("button", "btn-link", "remover");
    remover.type = "button";
    remover.addEventListener("click", () => executar("/api/cupom/remover", {}));
    etiqueta.appendChild(remover);
    bloco.appendChild(etiqueta);
    return bloco;
  }
  const { formulario, campo } = formularioCurto("Código do cupom", "Código do cupom", "Aplicar", "cupom");
  campo.maxLength = 30;
  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!campo.value.trim()) return;
    app.erros.cupom = "";
    const dados = await executar("/api/cupom", { codigo: campo.value }, (erro) => {
      app.erros.cupom = erro.message;
      desenharCarrinho();
    });
    if (dados) app.rascunho.cupom = "";
  });
  bloco.appendChild(formulario);
  if (app.erros.cupom) bloco.appendChild(el("p", "erro-inline", app.erros.cupom));
  return bloco;
}

function opcoesDeFrete(frete, nomeDoGrupo) {
  const grupo = el("div", "opcoes-frete");
  frete.opcoes.forEach((opcao) => {
    const rotulo = el("label", "opcao-frete");
    const radio = el("input");
    radio.type = "radio";
    radio.name = nomeDoGrupo;
    radio.value = opcao.modalidade;
    radio.checked = frete.modalidade === opcao.modalidade;
    radio.addEventListener("change", () => executar("/api/frete/modalidade", { modalidade: opcao.modalidade }));
    const texto = el("span");
    texto.appendChild(document.createTextNode(opcao.nome));
    texto.appendChild(el("small", "", opcao.prazo));
    const valor = el("span", opcao.gratis ? "valor gratis" : "valor", opcao.gratis ? "Grátis" : opcao.valor);
    rotulo.append(radio, texto, valor);
    grupo.appendChild(rotulo);
  });
  return grupo;
}

function blocoFrete(carrinho) {
  const bloco = el("div");
  bloco.appendChild(el("h3", "", "Frete"));
  app.rascunho.cep = app.rascunho.cep || carrinho.cep || "";
  const { formulario, campo } = formularioCurto("CEP (00000-000)", "CEP de entrega", "Calcular", "cep");
  campo.inputMode = "numeric";
  campo.maxLength = 9;
  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    app.erros.cep = "";
    const dados = await executar("/api/frete", { cep: campo.value }, (erro) => {
      app.erros.cep = erro.message;
      desenharCarrinho();
    });
    if (dados) app.rascunho.cep = "";
  });
  bloco.appendChild(formulario);
  if (app.erros.cep) bloco.appendChild(el("p", "erro-inline", app.erros.cep));

  const frete = carrinho.frete;
  if (frete) {
    bloco.appendChild(el("p", "dica", `Entrega para ${carrinho.cep} · zona ${frete.zona} (${frete.regiao})`));
    bloco.appendChild(opcoesDeFrete(frete, "frete-carrinho"));
    if (frete.falta_para_gratis) {
      bloco.appendChild(el("p", "dica", `Faltam ${frete.falta_para_gratis} em produtos para o frete grátis na Econômica.`));
    } else {
      bloco.appendChild(el("p", "dica destaque", "Você ganhou frete grátis na Econômica 🎉"));
    }
  }
  return bloco;
}

function linhaTotal(rotulo, valor, classe) {
  const linha = el("div", classe || "");
  linha.append(el("span", "", rotulo), el("span", "", valor));
  return linha;
}

function blocoTotais(carrinho) {
  const totais = el("div", "totais");
  totais.appendChild(linhaTotal("Subtotal", carrinho.subtotal));
  if (carrinho.cupom && carrinho.cupom.aplicado) {
    totais.appendChild(linhaTotal(`Cupom ${carrinho.cupom.codigo}`, `−${carrinho.cupom.desconto}`, "desconto"));
  }

  const frete = carrinho.frete;
  const escolhida = frete && frete.opcoes.find((o) => o.modalidade === frete.modalidade);
  let valorFrete = "informe o CEP";
  if (frete) valorFrete = !escolhida ? "escolha a modalidade" : frete.gratis ? "Grátis" : frete.valor;
  totais.appendChild(linhaTotal(escolhida ? `Frete (${escolhida.nome})` : "Frete", valorFrete));

  totais.appendChild(linhaTotal("Desconto PIX (5%)", `−${carrinho.desconto_pix}`, "desconto"));
  const rotuloTotal = carrinho.total_completo ? "Total no PIX" : "Total no PIX (sem frete)";
  totais.appendChild(linhaTotal(rotuloTotal, carrinho.total_pix, "total"));
  return totais;
}

function pedidoMini(pedido) {
  const aguardando = pedido.status === "aguardando_pagamento";
  const bloco = el("div", "pedido-mini");
  const titulo = el("div");
  titulo.appendChild(el("strong", "", `Pedido ${pedido.numero} `));
  titulo.appendChild(el("span", `selo selo-${pedido.status}`, pedido.status_rotulo));
  bloco.appendChild(titulo);
  const detalhe = el("div", "", `Total ${pedido.total}`);
  if (aguardando) {
    detalhe.appendChild(document.createTextNode(" · expira em "));
    const contador = el("strong", "", "--:--");
    contador.dataset.contador = "1";
    detalhe.appendChild(contador);
  }
  bloco.appendChild(detalhe);
  const ver = el("button", "btn-leve", aguardando ? "Ver PIX de teste" : "Ver pedido");
  ver.type = "button";
  ver.addEventListener("click", abrirPix);
  bloco.appendChild(ver);
  return bloco;
}

function desenharCarrinho() {
  if (!app.estado) return;
  const carrinho = app.estado.carrinho;
  const quantidade = carrinho.quantidade_itens;
  $("barra-itens").textContent = carrinho.vazio
    ? "Carrinho vazio"
    : `Carrinho · ${quantidade} ${quantidade === 1 ? "item" : "itens"}`;
  $("barra-total").textContent = carrinho.vazio ? "" : carrinho.total_pix;

  const filhos = [];
  if (carrinho.vazio) {
    filhos.push(el("p", "carrinho-vazio", "Seu carrinho está vazio. Peça uma indicação para a Sofia 💜"));
  } else {
    carrinho.itens.forEach((item) => filhos.push(linhaItem(item)));
    filhos.push(blocoCupom(carrinho), blocoFrete(carrinho), blocoTotais(carrinho));
    const finalizar = el("button", "btn-primario btn-largo", "Finalizar compra");
    finalizar.type = "button";
    finalizar.addEventListener("click", abrirCheckout);
    filhos.push(finalizar, el("p", "nota", "Pagamento somente por PIX (ambiente de teste)."));
  }
  if (app.estado.pedido) filhos.push(pedidoMini(app.estado.pedido));
  $("carrinho-corpo").replaceChildren(...filhos);
  atualizarContadores();
}
