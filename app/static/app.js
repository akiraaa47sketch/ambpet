/* Comportamentos da interface. Sem JS em linha (compatível com a CSP). */
(function () {
  "use strict";
  var $$ = function (sel, raiz) { return Array.prototype.slice.call((raiz || document).querySelectorAll(sel)); };

  // ---- Máscaras ----
  var mascaras = {
    cpf: function (d) {
      d = d.slice(0, 11);
      return d.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
    },
    telefone: function (d) {
      d = d.slice(0, 11);
      if (d.length <= 2) return d ? "(" + d : d;
      if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
      if (d.length <= 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
      return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
    },
    cep: function (d) { d = d.slice(0, 8); return d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d; }
  };
  $$("[data-mascara]").forEach(function (el) {
    var f = mascaras[el.dataset.mascara];
    var aplicar = function () { el.value = f(el.value.replace(/\D/g, "")); };
    el.addEventListener("input", aplicar);
    aplicar();
  });

  // ---- CEP -> endereço (ViaCEP), somente se habilitado ----
  if (document.body.dataset.viacep === "1") {
    $$("[data-cep]").forEach(function (el) {
      el.addEventListener("blur", function () {
        var cep = el.value.replace(/\D/g, "");
        if (cep.length !== 8) return;
        var f = el.form;
        fetch("https://viacep.com.br/ws/" + cep + "/json/", { referrerPolicy: "no-referrer", credentials: "omit" })
          .then(function (r) { return r.ok ? r.json() : {}; })
          .then(function (j) {
            if (!j || j.erro) return;
            var set = function (n, v) { var i = f.elements[n]; if (i && !i.value && v) i.value = v; };
            set("logradouro", j.logradouro); set("bairro", j.bairro); set("cidade", j.localidade); set("uf", j.uf);
            if (f.elements.numero && !f.elements.numero.value) f.elements.numero.focus();
          })
          .catch(function () {});
      });
    });
  }

  // ---- Espécie "Outra" ----
  $$("input[data-outra-alvo]").forEach(function (r) {
    var alvo = document.getElementById(r.dataset.outraAlvo);
    var atualizar = function () {
      var marcado = r.form.querySelector("input[name='" + r.name + "']:checked");
      var outra = marcado && marcado.value === "Outra";
      alvo.hidden = !outra;
      if (outra && document.activeElement === marcado) alvo.focus();
    };
    r.addEventListener("change", atualizar);
  });

  // ---- Envio automático ----
  $$("[data-enviar-ao-mudar]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });
  // Agendamento: ao mudar a data, recarrega mantendo o que já foi preenchido
  $$("[data-recarregar-form]").forEach(function (el) {
    el.addEventListener("change", function () {
      var d = new Date(el.value + "T12:00:00");
      if (d.getDay() === 0 || d.getDay() === 6) {
        window.alert("A clínica não atende aos sábados e domingos. Escolha um dia de segunda a sexta-feira.");
      }
      var h = el.form.querySelector("input[name=hora]:checked");
      if (h) h.checked = false;
      el.form.submit();
    });
  });

  // ---- Confirmações ----
  $$("form[data-confirmar]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!window.confirm(f.dataset.confirmar)) e.preventDefault(); });
  });

  // ---- Impressão ----
  $$("[data-imprimir]").forEach(function (b) { b.addEventListener("click", function () { window.print(); }); });

  // ---- Menu lateral no celular ----
  $$("[data-alternar-menu]").forEach(function (b) {
    b.addEventListener("click", function (e) { e.stopPropagation(); document.body.classList.toggle("menu-aberto"); });
  });
  document.addEventListener("click", function (e) {
    if (document.body.classList.contains("menu-aberto") && !e.target.closest(".lateral")) document.body.classList.remove("menu-aberto");
    // fecha menus <details> abertos ao clicar fora
    $$("details.menu-acoes[open], details.conta[open]").forEach(function (d) { if (!d.contains(e.target)) d.open = false; });
  });

  // ---- Atalho "/" para a busca ----
  var busca = document.querySelector("[data-atalho-busca]");
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && busca && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      e.preventDefault(); busca.focus();
    }
    if (e.key === "Escape") $$("details[open]").forEach(function (d) { d.open = false; });
  });

  // ---- Receita: itens dinâmicos ----
  var itens = document.getElementById("itens");
  var add = document.getElementById("add-item");
  if (itens && add) {
    var renumerar = function () { $$(".item-receita", itens).forEach(function (fs, i) { fs.querySelector("[data-num]").textContent = i + 1; }); };
    add.addEventListener("click", function () {
      var novo = itens.querySelector(".item-receita").cloneNode(true);
      $$("input", novo).forEach(function (i) { i.value = ""; });
      itens.appendChild(novo);
      renumerar();
      novo.querySelector("input").focus();
    });
    itens.addEventListener("click", function (e) {
      var b = e.target.closest("[data-remover-item]");
      if (!b) return;
      var todos = $$(".item-receita", itens);
      var fs = b.closest(".item-receita");
      if (todos.length > 1) fs.remove(); else $$("input", fs).forEach(function (i) { i.value = ""; });
      renumerar();
    });
  }

  // ---- Filtro de tabela ----
  $$("[data-filtra]").forEach(function (inp) {
    var tab = document.getElementById(inp.dataset.filtra);
    inp.addEventListener("input", function () {
      var t = inp.value.toLowerCase();
      $$("tbody tr", tab).forEach(function (tr) { tr.hidden = t && tr.textContent.toLowerCase().indexOf(t) === -1; });
    });
  });

  // ---- Abas ----
  var abas = document.querySelector("[data-abas]");
  if (abas) {
    var links = $$("a", abas);
    var paineis = links.map(function (l) { return document.getElementById(l.getAttribute("href").slice(1)); });
    var mostrar = function (id) {
      var achou = false;
      links.forEach(function (l, i) {
        var ativo = l.getAttribute("href") === "#" + id;
        achou = achou || ativo;
        l.classList.toggle("ativo", ativo);
        l.setAttribute("aria-selected", ativo ? "true" : "false");
        if (paineis[i]) paineis[i].hidden = !ativo;
      });
      return achou;
    };
    var inicial = function () {
      var h = location.hash.slice(1);
      if (h.indexOf("at-") === 0) h = "prontuario";
      if (!mostrar(h)) mostrar(links[0].getAttribute("href").slice(1));
    };
    inicial();
    window.addEventListener("hashchange", inicial);
    links.forEach(function (l) {
      l.addEventListener("click", function (e) {
        e.preventDefault();
        mostrar(l.getAttribute("href").slice(1));
        history.replaceState(null, "", l.getAttribute("href"));
      });
    });
    if (location.hash.indexOf("#at-") === 0) {
      var alvo = document.getElementById(location.hash.slice(1));
      if (alvo) alvo.scrollIntoView({ block: "start" });
    }
  }
})();
