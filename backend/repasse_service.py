"""Repasse aos profissionais (Financeiro, etapa 3 — 12/11/2026).

`relatorio` calcula, sem gravar nada, o relatório de atendimentos de cada
profissional (spec 2026-11-07, seções 6.2 e 6.3):
- entra só a sessão que a família pagou e que ainda não está num fechamento
  (`repasse_itens`), com `data_hora` até o fim do período — inclusive as de meses
  anteriores que só foram pagas agora;
- avulsa (sessão num item de cobrança): paga quando a cobrança está paga por
  inteiro; base = valor do item menos a parte dele no desconto da cobrança;
- pacote (sessão consumida): a sessão nº k entra quando o valor pago do pacote
  libera k sessões; base = valor do procedimento ou rateio do pacote;
- mensalidade (sessão coberta por uma mensalidade): entra quando a cobrança do mês
  está paga; base = valor do procedimento (limitada ao líquido do mês menos o que já foi
  repassado dele — 22/11/2026) ou rateio da mensalidade entre as sessões
  que contam do mês naquele acordo (no rateio, só depois que o mês termina, e dividindo
  o que ainda não foi repassado; sessão incluída antes do início vai para o 1º mês);
- falta só entra com `fin_repasse_falta` e se foi cobrada.
As sessões do período que ainda esperam o pagamento da família vão para
`aguardando`, só para informação.

Chamado fora de qualquer `em_lote` (roda `cobranca_service.sincronizar` e a conciliação antes).

`fechar` grava o fechamento ("Marcar repasse como pago", seção 6.4) com as linhas e os
valores do dia (mudar a regra depois não mexe nele); `desfazer` devolve tudo. Ajustes
manuais entram no próximo fechamento do profissional. `conciliar` (22/11/2026) mantém os
ajustes automáticos das sessões já repassadas: −valor do profissional quando a sessão
deixa de estar paga (`estorno`) ou de contar (`status`), apagado ou compensado por um
`recredito` quando o motivo acaba. Sessão repassada que deixou de contar não ocupa mais
a vaga do pacote nem a parte do mês da mensalidade.
Erros: `ValueError` = dado inválido (400), `Conflito` (subclasse) = 409, `LookupError` = 404.
"""
import calendar
from datetime import date, timedelta

import db
from db import query, query_one, execute, em_lote, log_auditoria, log_evento, criar_notificacao
import acordos_service
import ausencias_service
import caixa_service
import cobranca_regras as cregras
import cobranca_service
import repasse_regras as rregras

BASES = ("procedimento", "rateado")

MOTIVO_SEM_ACORDO = "Sessão sem acordo"
MOTIVO_SEM_VALOR = "Sessão sem valor"


def _mes_anterior(hoje):
    h = date.fromisoformat(str(hoje)[:10])
    fim = date(h.year, h.month, 1) - timedelta(days=1)
    return date(fim.year, fim.month, 1).isoformat(), fim.isoformat()


def validar_periodo(de, ate, hoje):
    """(de, ate) em ISO, ou a mensagem de erro. Os dois vazios = mês anterior inteiro."""
    hoje = str(hoje)[:10]
    if de in (None, "") and ate in (None, ""):
        de, ate = _mes_anterior(hoje)
    return caixa_service.validar_periodo(de, ate, hoje)


def _primeiro_do_mes_seguinte(dia):
    d = date.fromisoformat(str(dia)[:10])
    return (date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)).isoformat()


def _proporcional(valor, numerador, denominador):
    """valor × numerador / denominador, arredondado (meio para cima), nunca negativo."""
    valor = max(0, int(valor or 0))
    if denominador <= 0:
        return valor
    return max(0, (valor * max(0, numerador) * 2 + denominador) // (2 * denominador))


def _mm_aaaa(dia):
    d = str(dia)[:10]
    return f"{d[5:7]}/{d[:4]}"


def _regra_publica(r):
    if not r:
        return None
    return {k: r.get(k) for k in ("id", "procedimento_id", "tipo_acordo", "modo",
                                  "percentual_centesimos", "valor_centavos")}


# ------------------------------------------------------------------ leitura (uma vez por clínica)

def _consultas(org_id, limite):
    rows = query(
        """SELECT c.id AS consulta_id, c.paciente_id, c.profissional_id, c.data_hora, c.status,
                  c.especialidade, c.procedimento_id, c.procedimento_valor_centavos,
                  p.nome AS paciente_nome, pr.nome AS procedimento_nome,
                  v.acordo_id AS vinculo_acordo_id, v.incluida AS vinculo_incluida,
                  d.decisao, ri.repasse_id, ri.base_centavos AS repasse_base_centavos
           FROM consultas c
           JOIN pacientes p ON p.id = c.paciente_id
           LEFT JOIN procedimentos pr ON pr.id = c.procedimento_id
           LEFT JOIN consulta_acordo_incluida v ON v.consulta_id = c.id
           LEFT JOIN consulta_decisao_cobranca d ON d.consulta_id = c.id
           LEFT JOIN repasse_itens ri ON ri.consulta_id = c.id
           WHERE p.organizacao_id = ? AND c.status IN ('realizada', 'faltou')
             AND (c.data_hora < ? OR ri.consulta_id IS NOT NULL)""",
        (org_id, limite))
    saida = []
    for r in rows:
        r = dict(r)
        r["dia"] = str(r["data_hora"])[:10]
        r["especialidade"] = cregras.normalizar_especialidade(r["especialidade"])
        saida.append(r)
    saida.sort(key=lambda s: acordos_service.chave_data_hora(s["data_hora"], s["consulta_id"]))
    return saida


def _itens(org_id):
    """{consulta_id: item} com a base de cada item já calculada (desconto da cobrança rateado)."""
    rows = query(
        """SELECT i.id, i.cobranca_id, i.consulta_id, i.valor_centavos, i.status_origem, i.procedimento_nome,
                  cb.status AS cobranca_status, cb.desconto_centavos
           FROM cobranca_itens i JOIN cobrancas cb ON cb.id = i.cobranca_id
           WHERE cb.organizacao_id = ? ORDER BY i.id""", (org_id,))
    por_cobranca = {}
    for r in rows:
        por_cobranca.setdefault(r["cobranca_id"], []).append(dict(r))
    saida = {}
    for lista in por_cobranca.values():
        valores = [max(0, int(i["valor_centavos"] or 0)) for i in lista]
        desconto = max(0, int(lista[0]["desconto_centavos"] or 0))
        for item, base in zip(lista, rregras.bases_avulsa(valores, desconto)):
            item["base_centavos"] = max(0, base)
            saida[item["consulta_id"]] = item
    return saida


def _consumos(org_id):
    rows = query("""SELECT pc.consulta_id, pc.acordo_id, pc.numero, pc.status_origem,
                           a.sessoes_total, a.valor_centavos
                    FROM acordo_pacote_consumo pc JOIN acordos_pagamento a ON a.id = pc.acordo_id
                    WHERE a.organizacao_id = ?""", (org_id,))
    return {r["consulta_id"]: dict(r) for r in rows}


def _pacotes(org_id):
    """{acordo_id: (pago não estornado, descontos das parcelas não canceladas)}."""
    pagos = {r["acordo_id"]: int(r["total"] or 0) for r in query(
        """SELECT cb.acordo_id, SUM(pg.valor_centavos) AS total FROM pagamentos pg
           JOIN cobrancas cb ON cb.id = pg.cobranca_id
           WHERE cb.organizacao_id = ? AND cb.tipo = 'pacote' AND pg.estornado_em IS NULL
           GROUP BY cb.acordo_id""", (org_id,))}
    descontos = {r["acordo_id"]: int(r["total"] or 0) for r in query(
        """SELECT acordo_id, SUM(desconto_centavos) AS total FROM cobrancas
           WHERE organizacao_id = ? AND tipo = 'pacote' AND status <> 'cancelado'
           GROUP BY acordo_id""", (org_id,))}
    return pagos, descontos


def _mensalidades(org_id):
    """{(acordo_id, 1º dia do mês): cobrança}; havendo mais de uma, a não cancelada."""
    saida = {}
    for r in query("""SELECT id, acordo_id, periodo_inicio, status, valor_centavos, desconto_centavos
                      FROM cobrancas WHERE organizacao_id = ? AND tipo = 'mensalidade' ORDER BY id""", (org_id,)):
        chave = (r["acordo_id"], str(r["periodo_inicio"] or "")[:10])
        if chave not in saida or saida[chave]["status"] == "cancelado":
            saida[chave] = dict(r)
    return saida


def _regras(org_id):
    saida = {}
    for r in query("SELECT * FROM regras_repasse WHERE organizacao_id = ? ORDER BY id", (org_id,)):
        saida.setdefault(r["profissional_id"], []).append(dict(r))
    return saida


def _profissionais(org_id):
    saida = {}
    for u in query("SELECT id, nome, tipo_registro, numero_registro FROM usuarios WHERE organizacao_id = ?",
                   (org_id,)):
        registro = " ".join(x.strip() for x in (u["tipo_registro"] or "", u["numero_registro"] or "") if x.strip())
        saida[u["id"]] = {"nome": u["nome"] or "", "registro": registro}
    return saida


def _ajustes(org_id):
    saida = {}
    for a in query("""SELECT id, profissional_id, descricao, valor_centavos, origem FROM repasse_ajustes
                      WHERE organizacao_id = ? AND repasse_id IS NULL AND dispensado_em IS NULL
                      ORDER BY id""", (org_id,)):
        saida.setdefault(a["profissional_id"], []).append(
            {"id": a["id"], "descricao": a["descricao"], "valor_centavos": int(a["valor_centavos"]),
             "origem": a["origem"]})
    return saida


def _ja_pagas(org_id, de, ate, profissional_id, especialidade):
    rows = query("""SELECT ri.consulta_id, ri.repasse_id, ri.especialidade, r.pago_em, r.profissional_id,
                           COALESCE(c.data_hora, ri.data_hora) AS data_hora
                    FROM repasse_itens ri
                    JOIN repasses r ON r.id = ri.repasse_id
                    LEFT JOIN consultas c ON c.id = ri.consulta_id
                    WHERE r.organizacao_id = ?""", (org_id,))
    saida = []
    for r in sorted(rows, key=lambda x: acordos_service.chave_data_hora(x["data_hora"], x["consulta_id"])):
        if not (de <= str(r["data_hora"] or "")[:10] <= ate):
            continue
        if profissional_id is not None and r["profissional_id"] != profissional_id:
            continue
        if especialidade and not cregras.mesma_especialidade(
                cregras.normalizar_especialidade(r["especialidade"]), especialidade):
            continue
        saida.append({"consulta_id": r["consulta_id"], "pago_em": r["pago_em"], "repasse_id": r["repasse_id"]})
    return saida


# ------------------------------------------------------------------ cálculo

def _classificar(sessoes, itens, consumos, acordos, cobrar_falta, corte, hoje):
    """Marca em cada sessão `tipo` (avulsa, pacote, mensalidade, sem_acordo ou None = fora
    do financeiro) e, para as outras, o que as liga à cobrança. Devolve as sessões que
    contam de cada mensalidade/mês (ordem cronológica, inclusive as já repassadas), para o rateio."""
    contam_mes = {}
    for s in sessoes:
        s["tipo"] = None
        if s["consulta_id"] in itens:
            s["tipo"], s["item"] = "avulsa", itens[s["consulta_id"]]
            continue
        if s["consulta_id"] in consumos:
            s["tipo"], s["consumo"] = "pacote", consumos[s["consulta_id"]]
            continue
        # Mesmo critério de `acordos_service.sessoes_que_contam` para o que ainda não foi cobrado.
        if corte and s["dia"] < corte:
            continue
        if s["decisao"] == "nao_cobrar" or s["dia"] > hoje:
            continue
        if not cregras.status_gera_cobranca(s["status"], cobrar_falta):
            continue
        acordo = acordos_service.acordo_da_sessao(acordos.get(s["paciente_id"], []), s["especialidade"], s["dia"], s)
        if acordo and acordo["tipo"] == "mensalidade":
            s["tipo"], s["acordo"] = "mensalidade", acordo
            # Sessão incluída antes do início do acordo vai para o 1º mês dele (o único com cobrança).
            s["mes"] = max(s["dia"][:8] + "01", str(acordo["inicio"])[:8] + "01")
            contam_mes.setdefault((acordo["id"], s["mes"]), []).append(s)
        else:
            s["tipo"] = "sem_acordo"
            s["motivo"] = MOTIVO_SEM_VALOR if acordo and acordo["tipo"] == "avulsa" else MOTIVO_SEM_ACORDO
    return contam_mes


def _falta_cobrada(s):
    if s["tipo"] == "avulsa":
        return s["item"]["status_origem"] in (None, "faltou")
    if s["tipo"] == "pacote":
        return s["consumo"]["status_origem"] in (None, "faltou")
    return s["tipo"] in ("mensalidade", "sem_acordo")   # já filtradas por fin_cobrar_falta


def _mes_terminou(mes, hoje):
    d = date.fromisoformat(mes)
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1]).isoformat() < hoje


def _repassavel(s, repasse_falta):
    """A sessão paga entra no relatório? (falta só com `fin_repasse_falta` e se foi cobrada)."""
    return s["status"] != "faltou" or (repasse_falta and _falta_cobrada(s))


def _sessao_conta(s, repasse_falta):
    """Decisão 2 (22/11/2026): a sessão repassada ainda conta? `_repassavel` com o status atual
    (`s` None = a consulta não está mais realizada nem com falta: cancelada, desmarcada…)."""
    return s is not None and _repassavel(s, repasse_falta)


def _repassados(org_id, sessoes, repasse_falta):
    """O que já foi repassado de cada acordo, pelos itens gravados (a base e o acordo do dia do
    fechamento): ({acordo_id do pacote: [(chave de data, consulta_id, base)] em ordem},
    {(acordo_id da mensalidade, mês): soma das bases}). Sessão repassada que não conta mais
    (decisão 3) fica de fora: libera a vaga do pacote e a parte do mês — o −valor dela vem da
    conciliação. Item gravado sem o acordo (antes da revisão final) usa a classificação atual."""
    por_id = {s["consulta_id"]: s for s in sessoes}
    pacotes, meses = {}, {}
    for r in query("""SELECT ri.consulta_id, ri.tipo_acordo, ri.base_centavos, ri.acordo_id, ri.mes,
                             COALESCE(c.data_hora, ri.data_hora) AS data_hora, c.id AS consulta_existe
                      FROM repasse_itens ri JOIN repasses rp ON rp.id = ri.repasse_id
                      LEFT JOIN consultas c ON c.id = ri.consulta_id
                      WHERE rp.organizacao_id = ?""", (org_id,)):
        acordo_id, mes, tipo = r["acordo_id"], r["mes"], r["tipo_acordo"]
        s = por_id.get(r["consulta_id"])
        if r["consulta_existe"] is not None and not _sessao_conta(s, repasse_falta):
            continue
        if acordo_id is None and s:
            if s["tipo"] == "pacote":
                acordo_id, tipo = s["consumo"]["acordo_id"], "pacote"
            elif s["tipo"] == "mensalidade":
                acordo_id, mes, tipo = s["acordo"]["id"], s["mes"], "mensalidade"
        if acordo_id is None:
            continue
        base = max(0, int(r["base_centavos"] or 0))
        if tipo == "pacote":
            pacotes.setdefault(acordo_id, []).append(
                (acordos_service.chave_data_hora(r["data_hora"], r["consulta_id"]), r["consulta_id"], base))
        elif tipo == "mensalidade" and mes:
            chave = (acordo_id, str(mes)[:10])
            meses[chave] = meses.get(chave, 0) + base
    for lista in pacotes.values():
        lista.sort()
    return pacotes, meses


def _alocar_pacotes(ctx):
    """{consulta_id: (paga, base, motivo)} de toda sessão consumida de pacote.

    O pago do pacote libera N sessões; as já repassadas (itens gravados) gastam as primeiras
    vagas, e as que sobram vão para as não repassadas em ordem de data — a renumeração do
    pacote (sessão registrada atrasada, finalizada que virou falta) nunca libera vaga a mais.
    A soma das bases do acordo nunca passa do valor líquido do pacote (as duas bases; vale
    também para desconto dado depois de um repasse). Já repassada perde o "pago" só quando o
    pago libera menos sessões do que as repassadas: as mais recentes primeiro."""
    pagos, descontos = ctx["pacotes"]
    repassados = ctx["repassados"][0]
    por_acordo = {}
    for s in ctx["sessoes"]:
        if s["tipo"] == "pacote":
            por_acordo.setdefault(s["consumo"]["acordo_id"], []).append(s)
    aloc = {}
    for acordo_id, lista in por_acordo.items():
        c = lista[0]["consumo"]
        total = int(c["sessoes_total"] or 0)
        valor = max(0, int(c["valor_centavos"] or 0))
        efetivo = max(0, valor - max(0, descontos.get(acordo_id, 0)))
        liberadas = rregras.pacote_liberadas(efetivo, total, pagos.get(acordo_id, 0)) if total > 0 else 0
        motivo = f"Pacote: pago até a sessão {liberadas}" if liberadas else "Pacote: nenhuma sessão paga"
        ja = repassados.get(acordo_id, [])
        perdem = {cid for _, cid, _ in ja[liberadas:]}
        livres = max(0, liberadas - len(ja))
        restante = max(0, efetivo - sum(b for _, _, b in ja))
        rateio = rregras.rateio_igual(efetivo, total) if total > 0 else []
        pos = 0
        for s in lista:
            cid = s["consulta_id"]
            if s["repasse_id"] is not None:
                paga = cid not in perdem
                aloc[cid] = (paga, 0, None if paga else motivo)
                continue
            vaga = len(ja) + pos
            pos += 1
            if pos > livres:
                aloc[cid] = (False, 0, motivo)
                continue
            if ctx["base_modo"] == "rateado":
                base = rateio[vaga] if vaga < len(rateio) else 0
            else:
                base = _proporcional(s["procedimento_valor_centavos"], efetivo, valor)
            base = min(max(0, base), restante)
            if _repassavel(s, ctx["repasse_falta"]):   # falta fora do repasse ocupa a vaga, sem base
                restante -= base
            aloc[cid] = (True, base, None)
    return aloc


def _bases_mensalidades(ctx):
    """{consulta_id: base} das sessões ainda não repassadas de cada mensalidade paga. O já
    repassado daquele acordo/mês vem dos itens gravados das sessões que ainda contam. No
    rateio, o líquido do mês menos o já repassado é dividido entre as que ainda não foram;
    no 'procedimento', cada uma leva o valor do procedimento, em ordem de data, até esgotar
    esse mesmo resto (falta fora do repasse não gasta o resto)."""
    meses = ctx["repassados"][1]
    saida = {}
    for (acordo_id, mes), lista in ctx["contam_mes"].items():
        cob = ctx["mensalidades"].get((acordo_id, mes))
        if not cob or cob["status"] != "pago":
            continue
        valor = max(0, int(cob["valor_centavos"] or 0))
        liquido = max(0, valor - max(0, int(cob["desconto_centavos"] or 0)))
        pendentes = [x for x in lista if x["repasse_id"] is None]
        if not pendentes:
            continue
        restante = max(0, liquido - meses.get((acordo_id, mes), 0))
        if ctx["base_modo"] == "rateado":
            for x, base in zip(pendentes, rregras.rateio_igual(restante, len(pendentes))):
                saida[x["consulta_id"]] = base
        else:
            for x in pendentes:
                base = min(_proporcional(x["procedimento_valor_centavos"], liquido, valor), restante)
                saida[x["consulta_id"]] = base
                if _repassavel(x, ctx["repasse_falta"]):
                    restante -= base
    return saida


def _avaliar(s, ctx, hoje, base_modo=None):
    """(paga, base, descricao, sessao_numero, sessao_total, motivo). `base_modo` diferente do
    da clínica só muda a espera do fim do mês no rateio (as bases vêm de `_carregar`)."""
    base_modo = base_modo or ctx["base_modo"]
    mensalidades = ctx["mensalidades"]
    if s["tipo"] == "avulsa":
        item = s["item"]
        descricao = item["procedimento_nome"] or s["procedimento_nome"] or "Sessão avulsa"
        status = item["cobranca_status"]
        if status == "pago":
            return True, item["base_centavos"], descricao, None, None, None
        motivo = {"parcial": "Pago em parte", "cancelado": "Cobrança cancelada"}.get(status, "Cobrança em aberto")
        return False, 0, descricao, None, None, motivo

    if s["tipo"] == "pacote":
        c = s["consumo"]
        total = int(c["sessoes_total"] or 0)
        valor = max(0, int(c["valor_centavos"] or 0))
        numero = int(c["numero"] or 0)
        descricao = f"Pacote de {total} sessões · {rregras._brl(valor)}"
        paga, base, motivo = ctx["aloc_pacotes"].get(s["consulta_id"], (False, 0, "Pacote: nenhuma sessão paga"))
        return paga, base, descricao, numero, total, motivo

    if s["tipo"] == "mensalidade":
        acordo, mes = s["acordo"], s["mes"]
        cob = mensalidades.get((acordo["id"], mes))
        descricao = f"Mensalidade {_mm_aaaa(mes)}"
        if base_modo == "rateado" and not _mes_terminou(mes, hoje):
            return False, 0, descricao, None, None, "Mensalidade do mês em andamento"
        if not cob:
            return False, 0, descricao, None, None, "Mensalidade do mês ainda não gerada"
        valor = max(0, int(cob["valor_centavos"] or 0))
        descricao += f" · {rregras._brl(valor)}"
        if cob["status"] != "pago":
            estado = "cancelada" if cob["status"] == "cancelado" else "em aberto"
            return False, 0, descricao, None, None, f"Mensalidade de {_mm_aaaa(mes)} {estado}"
        return True, max(0, ctx["bases_mes"].get(s["consulta_id"], 0)), descricao, None, None, None

    return False, 0, "", None, None, s.get("motivo") or MOTIVO_SEM_ACORDO


def _carregar(org_id, limite, hoje):
    """Sessões (com `data_hora` antes de `limite`, mais as já repassadas) já classificadas e o
    que é preciso para `_avaliar` — a mesma leitura serve ao relatório e à conciliação."""
    org = query_one("""SELECT fin_cobrar_falta, fin_repasse_falta, fin_cobrar_desde, fin_repasse_base
                       FROM organizacoes WHERE id = ?""", (org_id,)) or {}
    cobrar_falta = bool(org.get("fin_cobrar_falta"))
    corte = str(org["fin_cobrar_desde"])[:10] if org.get("fin_cobrar_desde") else None
    sessoes = _consultas(org_id, limite)
    contam_mes = _classificar(sessoes, _itens(org_id), _consumos(org_id),
                              acordos_service.acordos_por_paciente(org_id), cobrar_falta, corte, hoje)
    ctx = {
        "repasse_falta": bool(org.get("fin_repasse_falta")),
        "base_modo": org.get("fin_repasse_base") if org.get("fin_repasse_base") in BASES else "procedimento",
        "sessoes": sessoes, "contam_mes": contam_mes,
        "pacotes": _pacotes(org_id), "mensalidades": _mensalidades(org_id),
        "repassados": _repassados(org_id, sessoes, bool(org.get("fin_repasse_falta"))),
    }
    ctx["aloc_pacotes"] = _alocar_pacotes(ctx)
    ctx["bases_mes"] = _bases_mensalidades(ctx)
    return ctx


def relatorio(org_id, de, ate, profissional_id=None, especialidade=None, hoje=None):
    """Relatório de atendimentos do repasse (ver o docstring do módulo). Só grava a conciliação
    das sessões já repassadas, para a tela sempre refletir o estado."""
    hoje = str(hoje or ausencias_service.hoje_brasilia().isoformat())[:10]
    cobranca_service.sincronizar(org_id, hoje)   # fora de em_lote, como as outras telas
    conciliar(org_id, origem_evento="relatório do repasse", hoje=hoje)   # nunca levanta exceção

    filtro_esp = (especialidade or "").strip() or None
    # Até o fim do mês de `ate`: o rateio da mensalidade conta as sessões do mês inteiro.
    ctx = _carregar(org_id, _primeiro_do_mes_seguinte(ate), hoje)
    sessoes, repasse_falta, base_modo = ctx["sessoes"], ctx["repasse_falta"], ctx["base_modo"]
    regras_por_prof, pessoas, ajustes = _regras(org_id), _profissionais(org_id), _ajustes(org_id)

    por_prof, aguardando = {}, []
    for s in sessoes:
        if s["tipo"] is None or s["repasse_id"] is not None or s["dia"] > ate:
            continue
        if not _repassavel(s, repasse_falta):
            continue
        if profissional_id is not None and s["profissional_id"] != profissional_id:
            continue
        if filtro_esp and not cregras.mesma_especialidade(s["especialidade"], filtro_esp):
            continue
        paga, base, descricao, numero, total, motivo = _avaliar(s, ctx, hoje)
        if not paga:
            if s["dia"] >= de:
                aguardando.append({"consulta_id": s["consulta_id"], "data_hora": s["data_hora"],
                                   "paciente_nome": s["paciente_nome"],
                                   "profissional_nome": pessoas.get(s["profissional_id"], {}).get("nome", ""),
                                   "motivo": motivo})
            continue
        tipo_acordo = "avulsa" if s["tipo"] == "avulsa" else s["tipo"]
        regra = rregras.escolher_regra(regras_por_prof.get(s["profissional_id"], []),
                                       s["procedimento_id"], tipo_acordo)
        prof_c = rregras.valor_profissional(regra, base) if regra else None
        por_prof.setdefault(s["profissional_id"], []).append({
            "consulta_id": s["consulta_id"], "data_hora": s["data_hora"], "paciente_nome": s["paciente_nome"],
            "especialidade": s["especialidade"], "descricao": descricao,
            "sessao_numero": numero, "sessao_total": total, "tipo_acordo": tipo_acordo,
            "base_centavos": base, "regra": _regra_publica(regra), "regra_rotulo": rregras.rotulo_regra(regra),
            "profissional_centavos": prof_c, "clinica_centavos": None if prof_c is None else base - prof_c,
            # gravados no item do fechamento: o que já foi repassado de cada acordo/mês
            "acordo_id": (s["consumo"]["acordo_id"] if s["tipo"] == "pacote"
                          else s["acordo"]["id"] if s["tipo"] == "mensalidade" else None),
            "mes": s["mes"] if s["tipo"] == "mensalidade" else None,
        })

    ids = set(por_prof)
    if not filtro_esp:   # ajuste não tem especialidade: com o filtro, só de quem tem sessão
        ids |= {pid for pid in ajustes if profissional_id is None or pid == profissional_id}
    profissionais = []
    for pid in ids:
        lista = por_prof.get(pid, [])
        grupos = {}
        for linha in lista:
            g = grupos.setdefault(linha["especialidade"].lower(), {
                "especialidade": linha["especialidade"], "quantidade": 0,
                "base_centavos": 0, "profissional_centavos": 0})
            g["quantidade"] += 1
            g["base_centavos"] += linha["base_centavos"]
            g["profissional_centavos"] += linha["profissional_centavos"] or 0
        aj = ajustes.get(pid, [])
        total_prof = sum(linha["profissional_centavos"] or 0 for linha in lista)
        total_aj = sum(a["valor_centavos"] for a in aj)
        pessoa = pessoas.get(pid, {"nome": "", "registro": ""})
        profissionais.append({
            "profissional_id": pid, "nome": pessoa["nome"], "registro": pessoa["registro"],
            "sessoes": lista,
            "por_especialidade": sorted(grupos.values(), key=lambda g: g["especialidade"].lower()),
            "ajustes": aj,
            "total_sessoes_centavos": sum(linha["base_centavos"] for linha in lista),
            "total_profissional_centavos": total_prof,
            "total_ajustes_centavos": total_aj,
            "a_pagar_centavos": total_prof + total_aj,
            "sem_regra": any(linha["regra"] is None for linha in lista),
        })
    profissionais.sort(key=lambda p: (p["nome"].lower(), p["profissional_id"]))

    return {"de": de, "ate": ate, "base": base_modo, "profissionais": profissionais,
            "aguardando": aguardando,
            "ja_pagas": _ja_pagas(org_id, de, ate, profissional_id, filtro_esp)}


# ------------------------------------------------------------------ fechamento ("Marcar repasse como pago")

class Conflito(ValueError):
    """Erro que a rota devolve como 409 (o resto do `ValueError` é 400)."""


MSG_RELATORIO_MUDOU = "O relatório mudou. Atualize a página e confira de novo."
MSG_JA_INCLUIDA = "Uma das sessões já foi incluída em outro repasse. Atualize a página e confira de novo."
LIMITE_AJUSTE_CENTAVOS = 10_000_000   # R$ 100.000,00, para mais ou para menos
LIMITE_DESCRICAO = 200
LIMITE_MOTIVO = 300


def _violacao_integridade(erro):
    # No Postgres chega como UniqueViolation (subclasse de IntegrityError).
    return any(c.__name__ == "IntegrityError" for c in type(erro).__mro__)


def _dd_mm(texto):
    t = str(texto or "")
    return f"{t[8:10]}/{t[5:7]}" if len(t) >= 10 else ""


def _profissional_da_clinica(org_id, profissional_id):
    u = query_one("""SELECT id, nome FROM usuarios WHERE id = ? AND organizacao_id = ?
                     AND papel IN ('profissional', 'gestor')""", (profissional_id, org_id))
    if not u:
        raise LookupError("Profissional não encontrado.")
    return u


def _lista_de_ids(valor):
    return isinstance(valor, (list, tuple)) and not any(isinstance(i, bool) or not isinstance(i, int) for i in valor)


def fechar(org_id, profissional_id, de, ate, consulta_ids, usuario, a_pagar_centavos, ajuste_ids, hoje=None):
    """Grava o fechamento do profissional no período. O que o gestor confirmou na tela (as
    sessões, o valor a pagar e os ajustes pendentes) tem de ser exatamente o do relatório de
    agora — regra mudada ou ajuste novo no meio = 409; liga todos os ajustes pendentes dele."""
    hoje = str(hoje or ausencias_service.hoje_brasilia().isoformat())[:10]
    periodo = validar_periodo(de, ate, hoje)
    if isinstance(periodo, str):
        raise ValueError(periodo)
    de, ate = periodo
    pessoa = _profissional_da_clinica(org_id, profissional_id)
    if not _lista_de_ids(consulta_ids):
        raise ValueError("Envie a lista de sessões.")
    if isinstance(a_pagar_centavos, bool) or not isinstance(a_pagar_centavos, int):
        raise ValueError("Envie o valor a pagar confirmado.")
    if not _lista_de_ids(ajuste_ids):
        raise ValueError("Envie a lista de ajustes confirmados.")

    # fora do em_lote; o relatório concilia antes (a tela e o fechamento veem os mesmos ajustes)
    rel = relatorio(org_id, de, ate, profissional_id=profissional_id, hoje=hoje)
    p = next((x for x in rel["profissionais"] if x["profissional_id"] == profissional_id), None)
    sessoes, ajustes = (p["sessoes"], p["ajustes"]) if p else ([], [])
    if len(consulta_ids) != len(set(consulta_ids)) or set(consulta_ids) != {s["consulta_id"] for s in sessoes}:
        raise Conflito(MSG_RELATORIO_MUDOU)
    if len(ajuste_ids) != len(set(ajuste_ids)) or set(ajuste_ids) != {a["id"] for a in ajustes}:
        raise Conflito(MSG_RELATORIO_MUDOU)
    if not sessoes and not ajustes:
        raise Conflito("Não há sessões nem ajustes para marcar como pago.")
    if any(s["regra"] is None for s in sessoes):
        raise ValueError(f"Defina a regra de repasse de {pessoa['nome']} antes de marcar como pago.")

    total_sessoes = sum(s["base_centavos"] for s in sessoes)
    total_prof = sum(s["profissional_centavos"] for s in sessoes)
    total_aj = sum(a["valor_centavos"] for a in ajustes)
    a_pagar = total_prof + total_aj
    if a_pagar != a_pagar_centavos:
        raise Conflito(MSG_RELATORIO_MUDOU)
    try:
        with em_lote():
            rid = execute(
                """INSERT INTO repasses (organizacao_id, profissional_id, periodo_de, periodo_ate,
                                         total_sessoes_centavos, total_profissional_centavos, total_ajustes_centavos,
                                         a_pagar_centavos, quantidade, pago_em, pago_por)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (org_id, profissional_id, de, ate, total_sessoes, total_prof, total_aj, a_pagar, len(sessoes),
                 ausencias_service.agora_brasilia_iso(), usuario["id"]))
            for s in sessoes:
                regra = s["regra"]
                execute(
                    """INSERT INTO repasse_itens (repasse_id, consulta_id, data_hora, paciente_nome, especialidade,
                                                  descricao, sessao_numero, sessao_total, tipo_acordo, base_centavos,
                                                  regra_modo, regra_percentual_centesimos, regra_valor_centavos,
                                                  profissional_centavos, clinica_centavos, acordo_id, mes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (rid, s["consulta_id"], str(s["data_hora"]), s["paciente_nome"], s["especialidade"],
                     s["descricao"], s["sessao_numero"], s["sessao_total"], s["tipo_acordo"], s["base_centavos"],
                     regra["modo"], regra["percentual_centesimos"], regra["valor_centavos"],
                     s["profissional_centavos"], s["clinica_centavos"], s["acordo_id"], s["mes"]))
            for a in ajustes:
                # UPDATE condicional (a linha fica travada até o commit) e releitura: dois
                # fechamentos ao mesmo tempo não pagam o mesmo ajuste; quem chega depois volta tudo.
                execute("""UPDATE repasse_ajustes SET repasse_id = ?
                           WHERE id = ? AND repasse_id IS NULL AND dispensado_em IS NULL""", (rid, a["id"]))
                atual = query_one("SELECT repasse_id FROM repasse_ajustes WHERE id = ?", (a["id"],))
                if not atual or atual["repasse_id"] != rid:
                    raise Conflito(MSG_RELATORIO_MUDOU)
            log_auditoria(org_id, usuario["id"], "repasse_pago", "repasse", rid,
                          f"{pessoa['nome']} · {de} a {ate} · {len(sessoes)} sessões · "
                          f"{len(ajustes)} ajustes · {a_pagar} centavos")
    except Conflito:
        raise
    except Exception as erro:
        if _violacao_integridade(erro):
            raise Conflito(MSG_JA_INCLUIDA) from erro
        raise
    # Estorno ou mudança de status gravados entre o cálculo do relatório e este commit não
    # teriam visto estas sessões como repassadas: concilia de novo, agora que estão nos itens.
    avisar_estorno_das_sessoes(org_id, [s["consulta_id"] for s in sessoes], rid)
    return detalhe_fechamento(org_id, rid)


def desfazer(org_id, repasse_id, motivo, usuario):
    """Apaga o fechamento e as linhas dele; os ajustes voltam a ficar pendentes e as sessões
    voltam ao relatório. Ajuste automático (estorno, status, recrédito) ainda pendente — ou
    dispensado — de uma sessão deste fechamento deixa de fazer sentido (o valor não foi
    repassado) e é apagado."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Informe o motivo.")
    motivo = motivo.strip()
    if len(motivo) > LIMITE_MOTIVO:
        raise ValueError(f"O motivo pode ter até {LIMITE_MOTIVO} caracteres.")
    r = query_one("SELECT * FROM repasses WHERE id = ? AND organizacao_id = ?", (repasse_id, org_id))
    if not r:
        raise LookupError("Fechamento não encontrado.")
    # O ajuste automático de uma sessão deste fechamento já foi pago noutro: desfazer este
    # devolveria a sessão ao relatório com o ajuste já aplicado. O outro sai antes.
    usado = query_one(f"""SELECT r2.pago_em FROM repasse_ajustes a
                          JOIN repasse_itens ri ON ri.consulta_id = a.consulta_id
                          JOIN repasses r2 ON r2.id = a.repasse_id
                          WHERE ri.repasse_id = ? AND a.origem IN {_SQL_AUTOMATICAS} AND a.repasse_id <> ?
                          ORDER BY r2.pago_em DESC, r2.id DESC LIMIT 1""", (repasse_id, repasse_id))
    if usado:
        p = str(usado["pago_em"] or "")
        raise Conflito(f"Desfaça primeiro o fechamento de {p[8:10]}/{p[5:7]}/{p[:4]} (ele usou um ajuste deste).")
    pessoa = query_one("SELECT nome FROM usuarios WHERE id = ?", (r["profissional_id"],)) or {"nome": ""}
    with em_lote():
        for item in query("SELECT consulta_id FROM repasse_itens WHERE repasse_id = ?", (repasse_id,)):
            execute(f"""DELETE FROM repasse_ajustes WHERE organizacao_id = ? AND origem IN {_SQL_AUTOMATICAS}
                        AND consulta_id = ? AND repasse_id IS NULL""", (org_id, item["consulta_id"]))
        execute("UPDATE repasse_ajustes SET repasse_id = NULL WHERE repasse_id = ?", (repasse_id,))
        execute("DELETE FROM repasse_itens WHERE repasse_id = ?", (repasse_id,))
        execute("DELETE FROM repasses WHERE id = ?", (repasse_id,))
        log_auditoria(org_id, usuario["id"], "repasse_desfeito", "repasse", repasse_id,
                      f"{pessoa['nome']} · {r['periodo_de']} a {r['periodo_ate']} · {r['quantidade']} sessões · "
                      f"{r['a_pagar_centavos']} centavos · motivo: {motivo}")


def criar_ajuste(org_id, profissional_id, descricao, valor_centavos, usuario):
    """Desconto (valor negativo) ou acréscimo que entra no próximo fechamento do profissional."""
    if not isinstance(descricao, str) or not descricao.strip() or len(descricao.strip()) > LIMITE_DESCRICAO:
        raise ValueError(f"Informe a descrição do ajuste (até {LIMITE_DESCRICAO} caracteres).")
    descricao = descricao.strip()
    if (isinstance(valor_centavos, bool) or not isinstance(valor_centavos, int) or valor_centavos == 0
            or abs(valor_centavos) > LIMITE_AJUSTE_CENTAVOS):
        raise ValueError("Informe um valor diferente de zero, até R$ 100.000,00 (negativo para desconto).")
    pessoa = _profissional_da_clinica(org_id, profissional_id)
    with em_lote():
        aid = execute("""INSERT INTO repasse_ajustes (organizacao_id, profissional_id, descricao, valor_centavos,
                                                      origem, criado_por)
                         VALUES (?, ?, ?, ?, 'manual', ?)""",
                      (org_id, profissional_id, descricao, valor_centavos, usuario["id"]))
        log_auditoria(org_id, usuario["id"], "criar", "repasse_ajuste", aid,
                      f"{pessoa['nome']} · {descricao} · {valor_centavos} centavos")
    return dict(query_one("SELECT * FROM repasse_ajustes WHERE id = ?", (aid,)))


def excluir_ajuste(org_id, ajuste_id, usuario):
    """Só o ajuste ainda pendente (fora de fechamento). O manual é apagado; o automático
    (estorno, status, recrédito) é dispensado (`dispensado_em`): sai do próximo fechamento,
    mas a linha fica e continua contando na conciliação (decisão 4), que assim não o cria
    nem notifica de novo — e o apaga se o motivo acabar."""
    a = query_one("SELECT * FROM repasse_ajustes WHERE id = ? AND organizacao_id = ?", (ajuste_id, org_id))
    if not a or a["dispensado_em"]:
        raise LookupError("Ajuste não encontrado.")
    if a["repasse_id"] is not None:
        raise Conflito("Este ajuste já está num repasse pago. Desfaça o fechamento para mexer nele.")
    with em_lote():
        if a["origem"] in AUTOMATICAS:
            execute("UPDATE repasse_ajustes SET dispensado_em = ? WHERE id = ? AND repasse_id IS NULL",
                    (ausencias_service.agora_brasilia_iso(), ajuste_id))
            acao = "dispensar"
        else:
            execute("DELETE FROM repasse_ajustes WHERE id = ? AND repasse_id IS NULL", (ajuste_id,))
            acao = "excluir"
        log_auditoria(org_id, usuario["id"], acao, "repasse_ajuste", ajuste_id,
                      f"{a['descricao']} · {a['valor_centavos']} centavos")


def listar_fechamentos(org_id, profissional_id=None):
    sql = """SELECT r.*, u.nome AS profissional_nome FROM repasses r
             LEFT JOIN usuarios u ON u.id = r.profissional_id WHERE r.organizacao_id = ?"""
    params = [org_id]
    if profissional_id is not None:
        sql += " AND r.profissional_id = ?"
        params.append(profissional_id)
    return [dict(r) for r in query(sql + " ORDER BY r.pago_em DESC, r.id DESC", tuple(params))]


def detalhe_fechamento(org_id, repasse_id):
    """O fechamento com as linhas e os ajustes como foram gravados; None se não for da clínica."""
    r = query_one("""SELECT r.*, u.nome AS profissional_nome FROM repasses r
                     LEFT JOIN usuarios u ON u.id = r.profissional_id
                     WHERE r.id = ? AND r.organizacao_id = ?""", (repasse_id, org_id))
    if not r:
        return None
    saida = dict(r)
    itens = [dict(i) for i in query("SELECT * FROM repasse_itens WHERE repasse_id = ?", (repasse_id,))]
    saida["itens"] = sorted(itens, key=lambda i: acordos_service.chave_data_hora(i["data_hora"], i["consulta_id"]))
    saida["ajustes"] = [dict(a) for a in query("SELECT * FROM repasse_ajustes WHERE repasse_id = ? ORDER BY id",
                                               (repasse_id,))]
    return saida


# ------------------------------------------------------------------ conciliação das sessões já repassadas

AUTOMATICAS = ("estorno", "status", "recredito")
_SQL_AUTOMATICAS = "('estorno', 'status', 'recredito')"

_ROTULO_STATUS = {"cancelada": "cancelada", "desmarcada_profissional": "desmarcada",
                  "falta_justificada": "com falta justificada", "faltou": "com falta",
                  "agendada": "reaberta", "confirmada": "reaberta"}


def _travar_sessao(consulta_id):
    """Primeira instrução da conciliação de uma sessão: trava a linha do item do fechamento
    (Postgres) ou a base (SQLite) até o commit — duas conciliações da mesma sessão se enfileiram."""
    if db.USANDO_POSTGRES:
        query("SELECT id FROM repasse_itens WHERE consulta_id = ? FOR UPDATE", (consulta_id,))
    else:
        execute("UPDATE repasse_itens SET consulta_id = consulta_id WHERE consulta_id = ?", (consulta_id,))


def _itens_repassados(org_id, consulta_ids=None):
    """Os itens gravados nos fechamentos da clínica (todos, ou só os destas sessões), com o
    status atual da consulta. Vem de `repasse_itens`, não de `_consultas`: a sessão desmarcada
    ou cancelada depois do fechamento também é conciliada."""
    sql = """SELECT ri.consulta_id, ri.profissional_centavos, ri.data_hora, ri.paciente_nome, ri.tipo_acordo,
                    ri.acordo_id, ri.mes, r.profissional_id, r.pago_em,
                    c.id AS consulta_existe, c.status AS consulta_status
             FROM repasse_itens ri JOIN repasses r ON r.id = ri.repasse_id
             LEFT JOIN consultas c ON c.id = ri.consulta_id
             WHERE r.organizacao_id = ?"""
    params = [org_id]
    if consulta_ids is not None:
        sql += f" AND ri.consulta_id IN ({', '.join('?' for _ in consulta_ids)})"
        params += list(consulta_ids)
    return [dict(r) for r in query(sql + " ORDER BY ri.consulta_id", tuple(params))]


def _somas_automaticas(org_id):
    """{consulta_id: soma dos ajustes automáticos} — inclusive os dispensados (decisão 4) e os
    já usados num fechamento. Leitura sem trava, só para pular as sessões que já batem."""
    return {r["consulta_id"]: int(r["total"] or 0) for r in query(
        f"""SELECT consulta_id, SUM(valor_centavos) AS total FROM repasse_ajustes
            WHERE organizacao_id = ? AND consulta_id IS NOT NULL AND origem IN {_SQL_AUTOMATICAS}
            GROUP BY consulta_id""", (org_id,))}


def _alvo(item, s, ctx, hoje):
    """(alvo, origem do negativo): 0 se a sessão conta (decisão 2: `_repassavel` com o status
    atual) e está paga (a regra do relatório, com a base 'procedimento' para a espera do fim
    do mês do rateio não parecer estorno); senão −valor do profissional gravado no item."""
    valor = max(0, int(item["profissional_centavos"] or 0))
    conta = _sessao_conta(s, ctx["repasse_falta"])
    if conta and _avaliar(s, ctx, hoje, "procedimento")[0]:
        return 0, None
    return -valor, ("estorno" if conta else "status")


def _descricao_automatica(origem, item, s):
    paciente = item["paciente_nome"] or (s or {}).get("paciente_nome") or ""
    quando = _dd_mm(item["data_hora"] or (s or {}).get("data_hora"))
    pago = _dd_mm(item["pago_em"])
    if origem == "recredito":
        return f"Recrédito: {paciente} em {quando} — o repasse de {pago} volta a valer"
    if origem == "status":
        rotulo = _ROTULO_STATUS.get(item["consulta_status"], "fora do repasse")
        return f"Sessão {rotulo}: {paciente} em {quando} — já repassado em {pago}"
    return f"Estorno: {paciente} em {quando} — já repassado em {pago}"


def _conciliar_sessao(org_id, item, s, alvo, origem_neg, origem_evento):
    """Uma transação por sessão: trava, relê os ajustes automáticos dela e chega ao alvo —
    primeiro apagando os pendentes (não usados em fechamento, dispensados inclusive) cuja
    remoção aproxima do alvo; o que faltar vira um ajuste novo pendente. Devolve
    ((profissional_id, descrição, valor, origem) do criado ou None, quantos apagou)."""
    cid = item["consulta_id"]
    with em_lote():
        _travar_sessao(cid)
        ajustes = query(f"""SELECT id, valor_centavos, repasse_id, descricao FROM repasse_ajustes
                            WHERE organizacao_id = ? AND consulta_id = ? AND origem IN {_SQL_AUTOMATICAS}
                            ORDER BY id DESC""", (org_id, cid))
        atual = sum(int(a["valor_centavos"]) for a in ajustes)
        apagados = 0
        for a in ajustes:
            if atual == alvo:
                break
            valor = int(a["valor_centavos"])
            if a["repasse_id"] is not None or abs(alvo - (atual - valor)) >= abs(alvo - atual):
                continue
            execute("DELETE FROM repasse_ajustes WHERE id = ? AND repasse_id IS NULL", (a["id"],))
            if query_one("SELECT 1 FROM repasse_ajustes WHERE id = ?", (a["id"],)):
                continue   # um fechamento o usou no meio: fica e continua contando
            log_auditoria(org_id, None, "excluir", "repasse_ajuste", a["id"],
                          f"{origem_evento} · conciliação · {a['descricao']} · {valor} centavos")
            atual -= valor
            apagados += 1
        falta = alvo - atual
        if falta == 0:
            return None, apagados
        origem = "recredito" if falta > 0 else (origem_neg or "estorno")
        descricao = _descricao_automatica(origem, item, s)
        aid = execute("""INSERT INTO repasse_ajustes (organizacao_id, profissional_id, descricao,
                                                      valor_centavos, origem, consulta_id)
                         VALUES (?, ?, ?, ?, ?, ?)""",
                      (org_id, item["profissional_id"], descricao, falta, origem, cid))
        log_auditoria(org_id, None, "criar", "repasse_ajuste", aid,
                      f"{origem_evento} · {descricao} · {falta} centavos")
    return (item["profissional_id"], descricao, falta, origem), apagados


def _registrar_falha(org_id, entidade, entidade_id, paciente_id, exc):
    try:
        if not db._em_lote_ativo():
            # No Postgres, a instrução que falhou fora de em_lote deixa a transação abortada:
            # sem o rollback, nem o evento nem o resto da requisição gravariam.
            db.get_db().rollback()
        log_evento(org_id, "aviso_repasse_falhou", entidade or "repasse", entidade_id, paciente_id,
                   {"erro": exc.__class__.__name__})
    except Exception:   # o aviso nunca derruba quem chamou
        pass


def _notificar(org_id, criados, resumo, entidade, entidade_id, paciente_id):
    """Uma notificação aos gestores por chamada que criou ajuste, com o total."""
    brl = rregras._brl
    try:
        if len(criados) == 1:
            pid, descricao, valor, _ = criados[0]
            nome = (query_one("SELECT nome FROM usuarios WHERE id = ?", (pid,)) or {}).get("nome") or "o profissional"
            como = "como Recrédito" if valor > 0 else "como desconto"
            texto = f"{descricao}. {brl(abs(valor))} entra {como} no próximo repasse de {nome}."
        else:
            de_onde = f" ({resumo})" if resumo else ""
            descontos = -sum(c[2] for c in criados if c[2] < 0)
            recreditos = sum(c[2] for c in criados if c[2] > 0)
            if all(c[3] == "estorno" for c in criados):
                texto = (f"{len(criados)} sessões já repassadas tiveram o pagamento estornado{de_onde}. "
                         f"{brl(descontos)} entra como desconto nos próximos repasses.")
            else:
                partes = ([f"{brl(descontos)} entra como desconto"] if descontos else []) + \
                         ([f"{brl(recreditos)} entra como Recrédito"] if recreditos else [])
                texto = (f"{len(criados)} sessões já repassadas mudaram{de_onde}: "
                         f"{' e '.join(partes)} nos próximos repasses.")
        with em_lote():
            for gestor in query("SELECT id FROM usuarios WHERE organizacao_id = ? AND papel = 'gestor' AND ativo = 1",
                                (org_id,)):
                criar_notificacao(gestor["id"], "Confira o repasse no Financeiro", texto,
                                  tipo="cobranca_familia", entidade=entidade or "repasse", entidade_id=entidade_id)
    except Exception as exc:   # os ajustes ficam; só o sino falhou
        _registrar_falha(org_id, entidade, entidade_id, paciente_id, exc)


def _conciliar(org_id, consulta_ids, ligada, origem_evento, entidade, entidade_id,
               paciente_id=None, resumo=None, hoje=None):
    try:
        itens = _itens_repassados(org_id, consulta_ids)
        if not itens:
            return 0
        hoje = str(hoje or ausencias_service.hoje_brasilia().isoformat())[:10]
        ctx = _carregar(org_id, "9999-12-31", hoje)
        por_id = {s["consulta_id"]: s for s in ctx["sessoes"]}
        somas = _somas_automaticas(org_id)
        pendencias = []
        for item in itens:
            if item["consulta_existe"] is None:   # consulta apagada (antes do bloqueio): fica como está
                continue
            s = por_id.get(item["consulta_id"])
            if ligada is not None and not ligada(item, s):
                continue
            alvo, origem_neg = _alvo(item, s, ctx, hoje)
            if somas.get(item["consulta_id"], 0) != alvo:
                pendencias.append((item, s, alvo, origem_neg))
    except Exception as exc:
        _registrar_falha(org_id, entidade, entidade_id, paciente_id, exc)
        return 0

    criados, mudancas = [], 0
    for item, s, alvo, origem_neg in pendencias:
        try:   # uma transação por sessão: a falha de uma não desfaz as outras
            criado, apagados = _conciliar_sessao(org_id, item, s, alvo, origem_neg, origem_evento)
        except Exception as exc:
            _registrar_falha(org_id, entidade, entidade_id, paciente_id, exc)
            continue
        mudancas += apagados + (1 if criado else 0)
        if criado:
            criados.append(criado)
    if criados:
        _notificar(org_id, criados, resumo, entidade, entidade_id, paciente_id)
    return mudancas


def conciliar(org_id, consulta_ids=None, origem_evento="", entidade=None, entidade_id=None, hoje=None):
    """Concilia as sessões já repassadas da clínica (todas, ou só as dadas): para cada uma, o
    alvo é 0 se ela conta e está paga, senão −valor do profissional; o atual é a soma dos
    ajustes automáticos dela (`estorno`, `status`, `recredito`, inclusive dispensados).
    Apaga os pendentes que aproximam do alvo e cria o que faltar (`recredito` se positivo;
    `estorno`/`status` se negativo). Chamar fora de `em_lote`, depois do commit de quem mudou
    a sessão. Nunca levanta exceção (falha vira `aviso_repasse_falhou`); devolve quantos
    ajustes criou ou apagou."""
    if consulta_ids is not None:
        consulta_ids = sorted(set(consulta_ids))
        if not consulta_ids:
            return 0
    return _conciliar(org_id, consulta_ids, None, origem_evento or "conciliação", entidade, entidade_id, hoje=hoje)


def conciliar_cobranca(cobranca_id, origem_evento=None):
    """Concilia as sessões já repassadas que dependem desta cobrança (depois de estorno, baixa
    ou webhook): avulsa = item dela; pacote = mesmo acordo (o pago libera as sessões em ordem);
    mensalidade = mesmo acordo e mês. Nunca levanta exceção."""
    try:
        cob = query_one("SELECT * FROM cobrancas WHERE id = ?", (cobranca_id,))
    except Exception as exc:
        _registrar_falha(None, "cobranca", cobranca_id, None, exc)
        return 0
    if not cob:
        return 0
    mes = str(cob["periodo_inicio"] or "")[:10]

    def ligada(item, s):
        if s is not None and s["tipo"] == "avulsa":
            return s["item"]["cobranca_id"] == cob["id"]
        acordo_id, tipo, item_mes = item["acordo_id"], item["tipo_acordo"], item["mes"]
        if s is not None and s["tipo"] == "pacote":
            acordo_id, tipo = s["consumo"]["acordo_id"], "pacote"
        elif s is not None and s["tipo"] == "mensalidade":
            acordo_id, tipo, item_mes = s["acordo"]["id"], "mensalidade", s["mes"]
        if cob["acordo_id"] is None or acordo_id != cob["acordo_id"] or tipo != cob["tipo"]:
            return False
        return tipo == "pacote" or str(item_mes or "")[:10] == mes
    return _conciliar(cob["organizacao_id"], None, ligada, origem_evento or f"cobrança {cobranca_id}",
                      "cobranca", cobranca_id, cob["paciente_id"], cob["descricao"])


def avisar_estorno(cobranca_id):
    """Atalho (nome antigo): concilia as sessões já repassadas desta cobrança."""
    return conciliar_cobranca(cobranca_id, f"estorno da cobrança {cobranca_id}")


def avisar_estorno_das_sessoes(org_id, consulta_ids, repasse_id):
    """Atalho (nome antigo), logo depois de um fechamento: sessão que mudou entre o cálculo do
    relatório e o commit (estorno ou status no meio) é conciliada. Nunca levanta exceção."""
    return conciliar(org_id, consulta_ids, f"conferência do fechamento {repasse_id}", "repasse", repasse_id)
