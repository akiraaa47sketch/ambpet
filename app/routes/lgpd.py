"""LGPD: aviso de privacidade, direitos do titular (acesso/portabilidade e eliminação)."""
import json
import secrets

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import db
from ..audit import registrar
from ..crypto import chaveiro
from ..models import Agendamento, IndiceBusca, Responsavel
from ..permissoes import requer_perfil
from ..utils import agora

bp = Blueprint("lgpd", __name__)


@bp.route("/privacidade")
def aviso():
    """Aviso de privacidade apresentado ao tutor (pode ser impresso ou exibido na recepção)."""
    return render_template("lgpd/aviso.html")


@bp.route("/tutores/<int:rid>/dados-pessoais")
@requer_perfil("admin")
def exportar(rid):
    """Direito de acesso e portabilidade (art. 18, II e V): todos os dados do titular em JSON."""
    r = db.get_or_404(Responsavel, rid)
    if r.anonimizado_em:
        flash("Este cadastro foi anonimizado.", "aviso")
        return redirect(url_for("admin.lgpd"))
    dados = {
        "gerado_em": agora().isoformat(),
        "controlador": request.host,
        "titular": {c: getattr(r, c) for c in Responsavel.CAMPOS},
        "aviso_privacidade": {"versao": r.aviso_privacidade_versao,
                              "apresentado_em": r.aviso_privacidade_em.isoformat()},
        "cadastrado_em": r.criado_em.isoformat(),
        "animais": [{
            "nome": a.nome, "especie": a.especie, "raca": a.raca, "sexo": a.sexo_nome,
            "castrado": a.castrado,
            "atendimentos": [{
                "data": c.data_hora.isoformat(), "veterinario": c.veterinario.nome,
                "queixa": c.queixa, "anamnese": c.anamnese, "exame_fisico": c.exame_fisico,
                "diagnostico": c.diagnostico, "conduta": c.conduta,
                "complementos": [ad.texto for ad in c.adendos]} for c in a.consultas],
            "receitas": [{
                "data": rec.emitida_em.isoformat(), "tipo": rec.tipo_nome,
                "itens": [{k: getattr(i, k) for k in ("medicamento", "concentracao", "via",
                                                      "posologia", "duracao")} for i in rec.itens],
                "orientacoes": rec.orientacoes} for rec in a.receitas],
        } for a in r.animais],
        "agendamentos": [{"data_hora": ag.data_hora.isoformat(), "tipo": ag.tipo,
                          "situacao": ag.status_nome, "paciente": ag.animal.nome}
                         for ag in Agendamento.query.filter_by(responsavel_id=r.id)],
    }
    registrar("exportar_dados_titular", "tutor", r.id)
    db.session.commit()
    return Response(json.dumps(dados, ensure_ascii=False, indent=2, default=str),
                    mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=titular-{r.id}.json"})


@bp.route("/tutores/<int:rid>/anonimizar", methods=["POST"])
@requer_perfil("admin")
def anonimizar(rid):
    """Eliminação (art. 18, VI) respeitando a guarda legal do prontuário (art. 16, I):
    os dados pessoais do tutor são apagados de forma irreversível; o prontuário
    clínico do animal é mantido sem vínculo identificável."""
    r = db.get_or_404(Responsavel, rid)
    if r.anonimizado_em:
        return redirect(url_for("admin.lgpd"))
    if request.form.get("confirmacao", "").strip().upper() != "ANONIMIZAR":
        flash('Digite ANONIMIZAR para confirmar.', "erro")
        return redirect(url_for("admin.lgpd"))
    if not current_user.verificar_senha(request.form.get("senha") or ""):
        flash("Senha incorreta.", "erro")
        return redirect(url_for("admin.lgpd"))
    marca = "anonimizado-" + secrets.token_hex(8)
    r.nome = "Titular anonimizado"
    r.cpf = r.telefone = r.cep = r.numero = r.ano_cadunico = "0"
    r.logradouro = r.bairro = r.cidade = r.uf = "—"
    r.complemento = None
    r.cpf_hash = chaveiro.hash(marca, "cpf")
    r.telefone_hash = chaveiro.hash(marca, "telefone")
    r.anonimizado_em = agora()
    IndiceBusca.query.filter_by(tutor_id=r.id).delete()
    for ag in Agendamento.query.filter_by(responsavel_id=r.id):
        ag.observacao = None
        if ag.ativo:
            ag.status = "cancelado"
    registrar("anonimizar_titular", "tutor", r.id, {"motivo": (request.form.get("motivo") or "")[:300]})
    db.session.commit()
    flash("Dados pessoais do tutor eliminados. O prontuário do animal foi mantido sem identificação.", "ok")
    return redirect(url_for("admin.lgpd"))


@bp.route("/conta/meus-acessos")
@login_required
def meus_acessos():
    from ..models import Auditoria
    logs = (Auditoria.query.filter_by(usuario_id=current_user.id)
            .filter(Auditoria.acao.in_(["login", "login_falhou", "login_bloqueado", "2fa_falhou",
                                        "alterar_senha", "2fa_ativado", "logout"]))
            .order_by(Auditoria.id.desc()).limit(30).all())
    return render_template("lgpd/meus_acessos.html", logs=logs)
