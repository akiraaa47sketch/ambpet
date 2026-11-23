(function () {
  "use strict";

  // ---- Máscaras (CPF, telefone, CEP) ----
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
    cep: function (d) {
      d = d.slice(0, 8);
      return d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d;
    }
  };
  document.querySelectorAll("[data-mascara]").forEach(function (el) {
    var f = mascaras[el.dataset.mascara];
    var aplicar = function () { el.value = f(el.value.replace(/\D/g, "")); };
    el.addEventListener("input", aplicar);
    aplicar();
  });

  // ---- CEP -> endereço (ViaCEP) ----
  document.querySelectorAll("[data-viacep]").forEach(function (el) {
    el.addEventListener("blur", function () {
      var cep = el.value.replace(/\D/g, "");
      if (cep.length !== 8) return;
      var form = el.form;
      fetch("https://viacep.com.br/ws/" + cep + "/json/")
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.erro) return;
          var set = function (n, v) { var i = form.elements[n]; if (i && !i.value && v) i.value = v; };
          set("logradouro", j.logradouro); set("bairro", j.bairro); set("cidade", j.localidade); set("uf", j.uf);
          if (form.elements.numero && !form.elements.numero.value) form.elements.numero.focus();
        })
        .catch(function () {});
    });
  });

  // ---- Espécie "Outra" ----
  document.querySelectorAll("select[data-outra]").forEach(function (sel) {
    var outro = sel.form.elements[sel.dataset.outra];
    var atualizar = function () { outro.hidden = sel.value !== "Outra"; if (!outro.hidden) outro.required = true; else outro.required = false; };
    sel.addEventListener("change", atualizar);
    atualizar();
  });

  // ---- Agendamento: ao trocar a data, recarrega para mostrar horários ocupados ----
  document.querySelectorAll("[data-recarregar]").forEach(function (el) {
    el.addEventListener("change", function () {
      var f = el.form, p = new URLSearchParams();
      ["responsavel_id", "data", "hora", "observacao"].forEach(function (n) {
        if (f.elements[n] && f.elements[n].value) p.set(n, f.elements[n].value);
      });
      var a = f.querySelector("[name=animal_id]:checked");
      if (a) p.set("animal_id", a.value);
      var d = new Date(el.value + "T12:00:00");
      if (d.getDay() === 0 || d.getDay() === 6) {
        alert("Não há agendamento aos sábados e domingos. Escolha um dia de segunda a sexta-feira.");
      }
      location.search = p.toString();
    });
  });

  // ---- Receita: adicionar/remover medicamentos ----
  var itens = document.getElementById("itens");
  var add = document.getElementById("add-item");
  function renumerar() {
    itens.querySelectorAll(".item-receita").forEach(function (fs, i) { fs.querySelector(".num").textContent = i + 1; });
  }
  if (itens && add) {
    add.addEventListener("click", function () {
      var modelo = itens.querySelector(".item-receita");
      var novo = modelo.cloneNode(true);
      novo.querySelectorAll("input").forEach(function (i) { i.value = ""; });
      itens.appendChild(novo);
      renumerar();
      novo.querySelector("input").focus();
    });
    itens.addEventListener("click", function (e) {
      if (!e.target.matches("[data-remover-item]")) return;
      var todos = itens.querySelectorAll(".item-receita");
      var fs = e.target.closest(".item-receita");
      if (todos.length > 1) fs.remove();
      else fs.querySelectorAll("input").forEach(function (i) { i.value = ""; });
      renumerar();
    });
  }

  // ---- Filtro simples em tabelas ----
  document.querySelectorAll("[data-filtra]").forEach(function (inp) {
    var tab = document.getElementById(inp.dataset.filtra);
    inp.addEventListener("input", function () {
      var t = inp.value.toLowerCase();
      tab.querySelectorAll("tbody tr, tr:not(:first-child)").forEach(function (tr) {
        if (tr.querySelector("th")) return;
        tr.hidden = t && tr.textContent.toLowerCase().indexOf(t) === -1;
      });
    });
  });

  // ---- Abas na ficha do animal ----
  var abas = document.querySelector("[data-abas]");
  if (abas) {
    var links = abas.querySelectorAll("a");
    var mostrar = function (id) {
      var ok = false;
      links.forEach(function (l) {
        var ativo = l.getAttribute("href") === "#" + id;
        ok = ok || ativo;
        l.classList.toggle("ativo", ativo);
        document.getElementById(l.getAttribute("href").slice(1)).hidden = !ativo;
      });
      return ok;
    };
    var alvo = location.hash.slice(1);
    if (alvo.indexOf("consulta-") === 0) alvo = "consultas";
    if (!mostrar(alvo)) mostrar("consultas");
    links.forEach(function (l) {
      l.addEventListener("click", function (e) {
        e.preventDefault();
        mostrar(l.getAttribute("href").slice(1));
        history.replaceState(null, "", l.getAttribute("href"));
      });
    });
    window.addEventListener("hashchange", function () {
      var h = location.hash.slice(1);
      mostrar(h.indexOf("consulta-") === 0 ? "consultas" : h);
    });
    if (location.hash.indexOf("#consulta-") === 0) {
      var el = document.querySelector(location.hash);
      if (el) el.scrollIntoView();
    }
  }
})();
