"""Sincronização agenda → cobranças das famílias e pendências (financeiro etapa 1, 07/11/2026).

`sincronizar` é idempotente e roda inteiro num `db.em_lote()` (tudo ou nada). É
chamado ao abrir as telas do financeiro e pelo cron opcional
`gerar_cobrancas_clinicas.py` — nunca dependa só do cron.

Ordem (a do plano, com um ajuste): devolver ao pacote as sessões que deixaram de
contar → gerar das sessões → mensalidades → volta atrás dos itens → vencidas.
A devolução ao pacote vem antes para que a vaga liberada seja usada na mesma
rodada (senão a 2ª sincronização ainda mudaria algo). Os itens só voltam atrás
depois de gerar: assim uma sessão nova entra no rascunho do período antes de ele
ficar vazio e ser cancelado.
"""
import calendar
import sqlite3
import re
from datetime import date, timedelta

from db import query, query_one, execute, em_lote, log_auditoria
import acordos_service
import ausencias_service
import cobranca_regras as regras

STATUS_ABERTOS_SEM_PAGAMENTO = ("pendente", "vencido")
PRAZO_MINIMO_DIAS = 5   # cobrança nunca nasce vencida: vence no mínimo hoje + 5
_RE_MARCA_CONSULTA = re.compile(r"^\[consulta (\d+)\]")

ROTULO_STATUS = {
    "falta_justificada": "Falta justificada",
    "desmarcada_profissional": "Desmarcada pelo profissional",
    "cancelada": "Desmarcada",
    "agendada": "Agendada",
    "confirmada": "Confirmada",
}


def _hoje(hoje):
    return str(hoje or ausencias_service.hoje_brasilia().isoformat())[:10]


def _vencimento_minimo(venc, hoje):
    """Cobrança criada com atraso (sessão finalizada tarde, mês de mensalidade
    gerado depois do dia de vencimento) não nasce vencida: se a data calculada já
    passou, vence em hoje + 5; senão fica a data calculada."""
    if venc >= hoje:
        return venc
    return (date.fromisoformat(hoje) + timedelta(days=PRAZO_MINIMO_DIAS)).isoformat()


def _dd_mm(dia):
    d = str(dia)[:10]
    return f"{d[8:10]}/{d[5:7]}"


def _dd_mm_aaaa(dia):
    d = str(dia)[:10]
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}"


def _rotulo_especialidade(acordo, especialidade):
    if acordo["especialidade"] == "*":
        return especialidade or "Todas as especialidades"
    return acordo["especialidade"]


def _violacao_unica(e):
    if isinstance(e, sqlite3.IntegrityError):
        return "UNIQUE" in str(e).upper()
    return type(e).__name__ == "UniqueViolation"


def _nova_cobranca(org_id, acordo, tipo, descricao, vencimento, status, valor=0, periodo=(None, None)):
    cid = execute(
        """INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status, organizacao_id,
                                  acordo_id, tipo, periodo_inicio, periodo_fim)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (acordo["paciente_id"], descricao, valor, vencimento, status, org_id, acordo["id"], tipo,
         periodo[0], periodo[1]))
    log_auditoria(org_id, None, "criar", "cobranca", cid, f"automática · {tipo} · {descricao}")
    return cid


def _renumerar_pacote(acordo_id):
    """Sessão N de M sempre na ordem das datas."""
    rows = query("""SELECT pc.consulta_id, pc.numero, c.data_hora FROM acordo_pacote_consumo pc
                    LEFT JOIN consultas c ON c.id = pc.consulta_id WHERE pc.acordo_id = ?""", (acordo_id,))
    rows = sorted(rows, key=lambda r: acordos_service.chave_data_hora(r["data_hora"], r["consulta_id"]))
    for n, r in enumerate(rows, start=1):
        if r["numero"] != n:
            execute("UPDATE acordo_pacote_consumo SET numero = ? WHERE consulta_id = ?", (n, r["consulta_id"]))


def _devolver_ao_pacote(org_id):
    """Consumo de sessão que deixou de contar (status ou consulta excluída) volta ao saldo."""
    rows = query(
        """SELECT pc.consulta_id, pc.acordo_id FROM acordo_pacote_consumo pc
            JOIN acordos_pagamento a ON a.id = pc.acordo_id
            LEFT JOIN consultas c ON c.id = pc.consulta_id
            WHERE a.organizacao_id = ?
              AND (c.id IS NULL OR c.status NOT IN ('realizada', 'faltou'))""", (org_id,))
    for r in rows:
        execute("DELETE FROM acordo_pacote_consumo WHERE consulta_id = ?", (r["consulta_id"],))
    for acordo_id in {r["acordo_id"] for r in rows}:
        _renumerar_pacote(acordo_id)


def _cobranca_do_periodo(org_id, acordo, sessao, periodos, res):
    """Rascunho do período da sessão; se o período já foi liberado, o próximo
    período aberto do acordo (criando o rascunho se preciso)."""
    ciclo = acordo["ciclo"]
    inicio, fim = regras.periodo_da_data(sessao["dia"], ciclo)
    while True:
        lista = periodos.setdefault((acordo["id"], inicio), [])
        for c in lista:
            if c["status"] == "rascunho":
                return c["id"]
        liberado = any(c["liberada_em"] or c["status"] != "cancelado" for c in lista)
        if not liberado:
            esp = _rotulo_especialidade(acordo, sessao["especialidade"])
            descricao = f"Sessões de {_dd_mm(inicio)} a {_dd_mm_aaaa(fim)} · {esp}"
            venc = regras.vencimento_do_periodo(fim, acordo["vence_dias"] if acordo["vence_dias"] is not None else 5)
            cid = _nova_cobranca(org_id, acordo, "periodo", descricao, venc, "rascunho", periodo=(inicio, fim))
            lista.append({"id": cid, "status": "rascunho", "liberada_em": None})
            res["criadas"] += 1
            return cid
        proximo = (date.fromisoformat(fim) + timedelta(days=1)).isoformat()
        inicio, fim = regras.periodo_da_data(proximo, ciclo)


def _recalcular(cobranca_id):
    """valor = soma dos itens; sem itens, a cobrança é cancelada."""
    soma = query_one("SELECT COUNT(*) AS n, COALESCE(SUM(valor_centavos), 0) AS total FROM cobranca_itens WHERE cobranca_id = ?",
                     (cobranca_id,))
    if soma["n"] == 0:
        execute("UPDATE cobrancas SET status = 'cancelado', valor_centavos = 0, desconto_centavos = 0 WHERE id = ?",
                (cobranca_id,))
        return
    execute("""UPDATE cobrancas SET valor_centavos = ?,
                   desconto_centavos = CASE WHEN desconto_centavos > ? THEN ? ELSE desconto_centavos END
               WHERE id = ?""", (soma["total"], soma["total"], soma["total"], cobranca_id))


def _gerar_das_sessoes(org_id, hoje, res):
    sessoes = acordos_service.sessoes_que_contam(org_id, None, hoje)
    if not sessoes:
        return
    acordos = acordos_service.acordos_por_paciente(org_id)
    usados = acordos_service.pacote_usados(org_id)
    periodos = {}
    for c in query("""SELECT id, acordo_id, periodo_inicio, status, liberada_em FROM cobrancas
                      WHERE organizacao_id = ? AND tipo = 'periodo' AND acordo_id IS NOT NULL ORDER BY id""", (org_id,)):
        periodos.setdefault((c["acordo_id"], c["periodo_inicio"]), []).append(dict(c))
    pacotes_tocados, cobrancas_tocadas = set(), set()
    for s in sessoes:
        acordo = acordos_service.acordo_da_sessao(acordos.get(s["paciente_id"], []), s["especialidade"], s["dia"])
        if not acordo or acordo["tipo"] == "mensalidade":
            continue   # sem acordo = pendência; mensalidade cobre a sessão
        if acordo["tipo"] == "pacote":
            if acordos_service.pacote_esgotado(acordo, usados):
                continue   # pacote acabou: vira pendência "sem acordo"
            usados[acordo["id"]] = usados.get(acordo["id"], 0) + 1
            execute("INSERT INTO acordo_pacote_consumo (consulta_id, acordo_id, numero) VALUES (?, ?, ?)",
                    (s["consulta_id"], acordo["id"], usados[acordo["id"]]))
            pacotes_tocados.add(acordo["id"])
            continue
        valor = s["decisao_valor_centavos"] or s["procedimento_valor_centavos"]
        if not valor or valor <= 0:
            continue   # pendência "sem valor"
        if acordo["ciclo"] == "consulta":
            esp = _rotulo_especialidade(acordo, s["especialidade"])
            venc = regras.vencimento_do_periodo(s["dia"], acordo["vence_dias"] if acordo["vence_dias"] is not None else 5)
            venc = _vencimento_minimo(venc, hoje)
            cobranca_id = _nova_cobranca(org_id, acordo, "avulsa", f"Sessão de {_dd_mm_aaaa(s['dia'])} · {esp}",
                                         venc, "pendente", periodo=(s["dia"], s["dia"]))
            res["criadas"] += 1
        else:
            cobranca_id = _cobranca_do_periodo(org_id, acordo, s, periodos, res)
        execute("""INSERT INTO cobranca_itens (cobranca_id, consulta_id, data_hora, procedimento_nome, valor_centavos)
                   VALUES (?, ?, ?, ?, ?)""",
                (cobranca_id, s["consulta_id"], s["data_hora"], s["procedimento_nome"], valor))
        res["itens"] += 1
        cobrancas_tocadas.add(cobranca_id)
    for acordo_id in pacotes_tocados:
        _renumerar_pacote(acordo_id)
    for cobranca_id in cobrancas_tocadas:
        _recalcular(cobranca_id)


def _gerar_mensalidades(org_id, hoje, res):
    acordos = query("""SELECT * FROM acordos_pagamento WHERE organizacao_id = ? AND tipo = 'mensalidade'
                       AND status = 'ativo' ORDER BY id""", (org_id,))
    if not acordos:
        return
    existentes = {(r["acordo_id"], r["periodo_inicio"]) for r in query(
        "SELECT acordo_id, periodo_inicio FROM cobrancas WHERE organizacao_id = ? AND tipo = 'mensalidade'", (org_id,))}
    h = date.fromisoformat(hoje)
    for a in acordos:
        inicio = date.fromisoformat(str(a["inicio"])[:10])
        ultimo = (h.year, h.month)
        if a["fim"]:
            f = date.fromisoformat(str(a["fim"])[:10])
            ultimo = min(ultimo, (f.year, f.month))
        ano, mes = inicio.year, inicio.month
        while (ano, mes) <= ultimo:
            primeiro = date(ano, mes, 1).isoformat()
            if (a["id"], primeiro) not in existentes:
                valor = regras.mensalidade_do_mes(a["valor_centavos"] or 0, ano, mes, a["inicio"], a["fim"])
                if valor > 0:
                    dias = calendar.monthrange(ano, mes)[1]
                    venc = _vencimento_minimo(date(ano, mes, min(a["dia_vencimento"] or 1, dias)).isoformat(), hoje)
                    esp = _rotulo_especialidade(a, None)
                    _nova_cobranca(org_id, a, "mensalidade", f"Mensalidade {mes:02d}/{ano} · {esp}", venc, "pendente",
                                   valor=valor, periodo=(primeiro, date(ano, mes, dias).isoformat()))
                    existentes.add((a["id"], primeiro))
                    res["criadas"] += 1
            ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def _pode_tirar_item(r):
    """Sai da cobrança só o item de um rascunho ou de uma avulsa (por consulta) ainda
    não paga. Cobrança de período já liberada nunca reabre (spec 4.3): ganha o aviso."""
    if r["cobranca_status"] == "rascunho" and not r["liberada_em"]:
        return True
    return (r["cobranca_tipo"] == "avulsa" and r["cobranca_status"] in STATUS_ABERTOS_SEM_PAGAMENTO
            and not r["tem_pagamento"])


def _ja_avisadas(org_id):
    """{(cobranca_id, consulta_id)} que já geraram o aviso "revisar" (pela auditoria),
    para não avisar de novo — nem depois de o gestor resolver."""
    saida = set()
    for a in query("""SELECT entidade_id, detalhes FROM auditoria
                      WHERE organizacao_id = ? AND entidade = 'cobranca' AND acao = 'revisar'""", (org_id,)):
        m = _RE_MARCA_CONSULTA.match(a["detalhes"] or "")
        if m:
            saida.add((a["entidade_id"], int(m.group(1))))
    return saida


def _voltar_atras(org_id, res):
    """Item cuja consulta deixou de contar: sai do rascunho ou da avulsa ainda não
    paga; nas demais (período liberado, paga, parcial) fica e a cobrança ganha o
    aviso "revisar" (o valor não muda)."""
    rows = query(
        """SELECT i.id AS item_id, i.cobranca_id, i.consulta_id, i.data_hora AS item_data_hora,
                   c.id AS existe, c.status AS consulta_status, c.data_hora,
                   cb.status AS cobranca_status, cb.tipo AS cobranca_tipo, cb.liberada_em, cb.revisar_motivo,
                   EXISTS (SELECT 1 FROM pagamentos pg WHERE pg.cobranca_id = cb.id
                           AND pg.estornado_em IS NULL) AS tem_pagamento
            FROM cobranca_itens i
            JOIN cobrancas cb ON cb.id = i.cobranca_id
            LEFT JOIN consultas c ON c.id = i.consulta_id
            WHERE cb.organizacao_id = ? AND cb.status != 'cancelado'
              AND (c.id IS NULL OR c.status NOT IN ('realizada', 'faltou'))
            ORDER BY i.id""", (org_id,))
    tocadas = set()
    motivos = {}
    avisadas = _ja_avisadas(org_id) if rows else set()
    for r in rows:
        if _pode_tirar_item(r):
            execute("DELETE FROM cobranca_itens WHERE id = ?", (r["item_id"],))
            tocadas.add(r["cobranca_id"])
            log_auditoria(org_id, None, "remover_item", "cobranca", r["cobranca_id"],
                          f"sessão {r['consulta_id']} deixou de contar")
            continue
        dia = _dd_mm(r["data_hora"] or r["item_data_hora"])
        if r["existe"] is None:
            texto = f"Sessão de {dia} foi excluída"
        else:
            texto = f"Sessão de {dia} virou {ROTULO_STATUS.get(r['consulta_status'], r['consulta_status'])}"
        chave = (r["cobranca_id"], r["consulta_id"])
        if chave in avisadas:
            continue   # já avisado por esta sessão (também depois de o gestor resolver)
        avisadas.add(chave)
        atual = motivos.get(r["cobranca_id"], r["revisar_motivo"] or "")
        motivos[r["cobranca_id"]] = f"{atual}; {texto}" if atual else texto
        execute("UPDATE cobrancas SET revisar = 1, revisar_motivo = ? WHERE id = ?",
                (motivos[r["cobranca_id"]], r["cobranca_id"]))
        log_auditoria(org_id, None, "revisar", "cobranca", r["cobranca_id"], f"[consulta {r['consulta_id']}] {texto}")
        res["revisar"] += 1
    for cobranca_id in tocadas:
        _recalcular(cobranca_id)


def _marcar_vencidas(org_id, hoje):
    execute("""UPDATE cobrancas SET status = 'vencido'
               WHERE organizacao_id = ? AND status IN ('pendente', 'parcial') AND vencimento < ?""", (org_id, hoje))


def sincronizar(org_id, hoje=None):
    """Agenda → cobranças da clínica. Idempotente; devolve o que mudou nesta rodada."""
    hoje = _hoje(hoje)
    res = {"criadas": 0, "itens": 0, "revisar": 0}
    try:
        with em_lote():
            _devolver_ao_pacote(org_id)
            _gerar_das_sessoes(org_id, hoje, res)
            _gerar_mensalidades(org_id, hoje, res)
            _voltar_atras(org_id, res)
            _marcar_vencidas(org_id, hoje)
    except Exception as e:
        # Outra sincronização simultânea gravou primeiro (índice único dos itens /
        # PK do consumo): esta foi desfeita inteira e a outra já fez o trabalho.
        if _violacao_unica(e):
            return {"criadas": 0, "itens": 0, "revisar": 0}
        raise
    return res


# ------------------------------------------------------------------ pendências

def _sessao_publica(s):
    return {k: s[k] for k in ("consulta_id", "paciente_id", "paciente_nome", "data_hora", "profissional_nome",
                              "especialidade", "procedimento_nome", "procedimento_valor_centavos")}


def pendencias(org_id, hoje=None):
    hoje = _hoje(hoje)
    sem_acordo = acordos_service.sessoes_sem_acordo(org_id, None, None, hoje)

    acordos = acordos_service.acordos_por_paciente(org_id)
    sem_valor = []
    for s in acordos_service.sessoes_que_contam(org_id, None, hoje):
        a = acordos_service.acordo_da_sessao(acordos.get(s["paciente_id"], []), s["especialidade"], s["dia"])
        if a and a["tipo"] == "avulsa" and not ((s["decisao_valor_centavos"] or s["procedimento_valor_centavos"] or 0) > 0):
            sem_valor.append(_sessao_publica(s))

    usados = acordos_service.pacote_usados(org_id)
    pacotes = []
    for a in query("""SELECT a.*, p.nome AS paciente_nome FROM acordos_pagamento a
                      JOIN pacientes p ON p.id = a.paciente_id
                      WHERE a.organizacao_id = ? AND a.tipo = 'pacote' AND a.status = 'ativo' ORDER BY a.id""", (org_id,)):
        n = usados.get(a["id"], 0)
        restantes = (a["sessoes_total"] or 0) - n
        if restantes <= 2:
            pacotes.append({"acordo_id": a["id"], "paciente_id": a["paciente_id"], "paciente_nome": a["paciente_nome"],
                            "especialidade": a["especialidade"], "sessoes_total": a["sessoes_total"],
                            "sessoes_usadas": n, "restantes": max(restantes, 0)})

    terminando = [
        {"acordo_id": a["id"], "paciente_id": a["paciente_id"], "paciente_nome": a["paciente_nome"],
         "especialidade": a["especialidade"], "valor_centavos": a["valor_centavos"], "fim": a["fim"]}
        for a in query("""SELECT a.*, p.nome AS paciente_nome FROM acordos_pagamento a
                          JOIN pacientes p ON p.id = a.paciente_id
                          WHERE a.organizacao_id = ? AND a.tipo = 'mensalidade' AND a.status = 'ativo'
                            AND a.fim IS NOT NULL ORDER BY a.fim, a.id""", (org_id,))
        if str(a["fim"])[:7] == hoje[:7]
    ]

    def _cobrancas(where):
        return query(
            f"""SELECT cb.id, cb.paciente_id, p.nome AS paciente_nome, cb.tipo, cb.descricao, cb.vencimento,
                       cb.status, cb.valor_centavos, cb.desconto_centavos, cb.revisar_motivo,
                       (SELECT COALESCE(SUM(pg.valor_centavos), 0) FROM pagamentos pg
                        WHERE pg.cobranca_id = cb.id AND pg.estornado_em IS NULL) AS pago_centavos
                FROM cobrancas cb JOIN pacientes p ON p.id = cb.paciente_id
                WHERE cb.organizacao_id = ? AND {where} ORDER BY cb.vencimento, cb.id""", (org_id,))

    vencidas = []
    for c in _cobrancas("cb.status = 'vencido'"):
        c = dict(c)
        c["saldo_centavos"] = c["valor_centavos"] - (c["desconto_centavos"] or 0) - c["pago_centavos"]
        vencidas.append(c)
    revisar = [dict(c) for c in _cobrancas("cb.revisar = 1")]

    return {"sem_acordo": sem_acordo, "sem_valor": sem_valor, "pacotes_acabando": pacotes,
            "mensalidades_terminando": terminando, "vencidas": vencidas, "revisar": revisar}


def sessao_do_pacote(consulta_id):
    """{"numero": 3, "total": 10} para a sessão consumida de um pacote; senão None."""
    r = query_one("""SELECT pc.numero, a.sessoes_total FROM acordo_pacote_consumo pc
                     JOIN acordos_pagamento a ON a.id = pc.acordo_id WHERE pc.consulta_id = ?""", (consulta_id,))
    return {"numero": r["numero"], "total": r["sessoes_total"]} if r else None
