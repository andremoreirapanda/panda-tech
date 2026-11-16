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
  está paga; base = valor do procedimento ou rateio da mensalidade entre as sessões
  que contam do mês naquele acordo (no rateio, só depois que o mês termina, e dividindo
  o que ainda não foi repassado; sessão incluída antes do início vai para o 1º mês);
- falta só entra com `fin_repasse_falta` e se foi cobrada.
As sessões do período que ainda esperam o pagamento da família vão para
`aguardando`, só para informação.

Chamado fora de qualquer `em_lote` (roda `cobranca_service.sincronizar` antes).

`fechar` grava o fechamento ("Marcar repasse como pago", seção 6.4) com as linhas e os
valores do dia (mudar a regra depois não mexe nele); `desfazer` devolve tudo. Ajustes
manuais entram no próximo fechamento do profissional. `avisar_estorno` transforma o
estorno de uma sessão já repassada num ajuste negativo (seção 6.3, último parágrafo).
Erros: `ValueError` = dado inválido (400), `Conflito` (subclasse) = 409, `LookupError` = 404.
"""
import calendar
from datetime import date, timedelta

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
           WHERE p.organizacao_id = ? AND c.status IN ('realizada', 'faltou') AND c.data_hora < ?""",
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
                      WHERE organizacao_id = ? AND repasse_id IS NULL ORDER BY id""", (org_id,)):
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


def _base_rateada_mensalidade(s, liquido, lista):
    """Rateio do que sobrou do mês: líquido menos o que já foi repassado dessas sessões,
    dividido entre as que ainda não foram. Assim a soma nunca passa do que foi cobrado,
    mesmo com sessão finalizada depois de um fechamento."""
    ja = sum(max(0, int(x["repasse_base_centavos"] or 0)) for x in lista if x["repasse_id"] is not None)
    pendentes = [x["consulta_id"] for x in lista if x["repasse_id"] is None]
    if s["consulta_id"] not in pendentes:
        return 0
    return rregras.rateio_igual(max(0, liquido - ja), len(pendentes))[pendentes.index(s["consulta_id"])]


def _avaliar(s, base_modo, pacotes, mensalidades, contam_mes, hoje):
    """(paga, base, descricao, sessao_numero, sessao_total, motivo)."""
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
        pago, descontos = pacotes[0].get(c["acordo_id"], 0), pacotes[1].get(c["acordo_id"], 0)
        efetivo = max(0, valor - max(0, descontos))
        numero = int(c["numero"] or 0)
        descricao = f"Pacote de {total} sessões · {rregras._brl(valor)}"
        liberadas = rregras.pacote_liberadas(efetivo, total, pago) if total > 0 else 0
        if numero < 1 or numero > liberadas:
            motivo = (f"Pacote: pago até a sessão {liberadas}" if liberadas else "Pacote: nenhuma sessão paga")
            return False, 0, descricao, numero, total, motivo
        if base_modo == "rateado":
            base = rregras.rateio_igual(efetivo, total)[numero - 1]
        else:
            base = _proporcional(s["procedimento_valor_centavos"], efetivo, valor)
        return True, max(0, base), descricao, numero, total, None

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
        liquido = max(0, valor - max(0, int(cob["desconto_centavos"] or 0)))
        if base_modo == "rateado":
            base = _base_rateada_mensalidade(s, liquido, contam_mes.get((acordo["id"], mes), []))
        else:
            base = _proporcional(s["procedimento_valor_centavos"], liquido, valor)
        return True, max(0, base), descricao, None, None, None

    return False, 0, "", None, None, s.get("motivo") or MOTIVO_SEM_ACORDO


def _carregar(org_id, limite, hoje):
    """Sessões (com `data_hora` antes de `limite`) já classificadas e o que é preciso para
    `_avaliar` — a mesma leitura serve ao relatório e ao aviso de estorno."""
    org = query_one("""SELECT fin_cobrar_falta, fin_repasse_falta, fin_cobrar_desde, fin_repasse_base
                       FROM organizacoes WHERE id = ?""", (org_id,)) or {}
    cobrar_falta = bool(org.get("fin_cobrar_falta"))
    corte = str(org["fin_cobrar_desde"])[:10] if org.get("fin_cobrar_desde") else None
    sessoes = _consultas(org_id, limite)
    contam_mes = _classificar(sessoes, _itens(org_id), _consumos(org_id),
                              acordos_service.acordos_por_paciente(org_id), cobrar_falta, corte, hoje)
    return {
        "repasse_falta": bool(org.get("fin_repasse_falta")),
        "base_modo": org.get("fin_repasse_base") if org.get("fin_repasse_base") in BASES else "procedimento",
        "sessoes": sessoes, "contam_mes": contam_mes,
        "pacotes": _pacotes(org_id), "mensalidades": _mensalidades(org_id),
    }


def relatorio(org_id, de, ate, profissional_id=None, especialidade=None, hoje=None):
    """Relatório de atendimentos do repasse (só leitura; ver o docstring do módulo)."""
    hoje = str(hoje or ausencias_service.hoje_brasilia().isoformat())[:10]
    cobranca_service.sincronizar(org_id, hoje)   # fora de em_lote, como as outras telas

    filtro_esp = (especialidade or "").strip() or None
    # Até o fim do mês de `ate`: o rateio da mensalidade conta as sessões do mês inteiro.
    ctx = _carregar(org_id, _primeiro_do_mes_seguinte(ate), hoje)
    sessoes, contam_mes, repasse_falta, base_modo = (ctx["sessoes"], ctx["contam_mes"],
                                                     ctx["repasse_falta"], ctx["base_modo"])
    pacotes, mensalidades = ctx["pacotes"], ctx["mensalidades"]
    regras_por_prof, pessoas, ajustes = _regras(org_id), _profissionais(org_id), _ajustes(org_id)

    por_prof, aguardando = {}, []
    for s in sessoes:
        if s["tipo"] is None or s["repasse_id"] is not None or s["dia"] > ate:
            continue
        if s["status"] == "faltou" and not (repasse_falta and _falta_cobrada(s)):
            continue
        if profissional_id is not None and s["profissional_id"] != profissional_id:
            continue
        if filtro_esp and not cregras.mesma_especialidade(s["especialidade"], filtro_esp):
            continue
        paga, base, descricao, numero, total, motivo = _avaliar(s, base_modo, pacotes, mensalidades, contam_mes, hoje)
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


def fechar(org_id, profissional_id, de, ate, consulta_ids, usuario, hoje=None):
    """Grava o fechamento do profissional no período: as sessões enviadas têm de ser
    exatamente as liberadas no relatório de agora; liga todos os ajustes pendentes dele."""
    hoje = str(hoje or ausencias_service.hoje_brasilia().isoformat())[:10]
    periodo = validar_periodo(de, ate, hoje)
    if isinstance(periodo, str):
        raise ValueError(periodo)
    de, ate = periodo
    pessoa = _profissional_da_clinica(org_id, profissional_id)
    if not isinstance(consulta_ids, (list, tuple)) or any(
            isinstance(i, bool) or not isinstance(i, int) for i in consulta_ids):
        raise ValueError("Envie a lista de sessões.")

    rel = relatorio(org_id, de, ate, profissional_id=profissional_id, hoje=hoje)   # fora do em_lote
    p = next((x for x in rel["profissionais"] if x["profissional_id"] == profissional_id), None)
    sessoes, ajustes = (p["sessoes"], p["ajustes"]) if p else ([], [])
    if len(consulta_ids) != len(set(consulta_ids)) or set(consulta_ids) != {s["consulta_id"] for s in sessoes}:
        raise Conflito(MSG_RELATORIO_MUDOU)
    if not sessoes and not ajustes:
        raise Conflito("Não há sessões nem ajustes para marcar como pago.")
    if any(s["regra"] is None for s in sessoes):
        raise ValueError(f"Defina a regra de repasse de {pessoa['nome']} antes de marcar como pago.")

    total_sessoes = sum(s["base_centavos"] for s in sessoes)
    total_prof = sum(s["profissional_centavos"] for s in sessoes)
    total_aj = sum(a["valor_centavos"] for a in ajustes)
    a_pagar = total_prof + total_aj
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
                                                  profissional_centavos, clinica_centavos)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (rid, s["consulta_id"], str(s["data_hora"]), s["paciente_nome"], s["especialidade"],
                     s["descricao"], s["sessao_numero"], s["sessao_total"], s["tipo_acordo"], s["base_centavos"],
                     regra["modo"], regra["percentual_centesimos"], regra["valor_centavos"],
                     s["profissional_centavos"], s["clinica_centavos"]))
            for a in ajustes:
                atual = query_one("SELECT repasse_id FROM repasse_ajustes WHERE id = ?", (a["id"],))
                if not atual or atual["repasse_id"] is not None:
                    raise Conflito(MSG_RELATORIO_MUDOU)
                execute("UPDATE repasse_ajustes SET repasse_id = ? WHERE id = ?", (rid, a["id"]))
            log_auditoria(org_id, usuario["id"], "repasse_pago", "repasse", rid,
                          f"{pessoa['nome']} · {de} a {ate} · {len(sessoes)} sessões · "
                          f"{len(ajustes)} ajustes · {a_pagar} centavos")
    except Conflito:
        raise
    except Exception as erro:
        if _violacao_integridade(erro):
            raise Conflito(MSG_JA_INCLUIDA) from erro
        raise
    return detalhe_fechamento(org_id, rid)


def desfazer(org_id, repasse_id, motivo, usuario):
    """Apaga o fechamento e as linhas dele; os ajustes voltam a ficar pendentes e as sessões
    voltam ao relatório. Aviso de estorno ainda pendente de uma sessão deste fechamento
    deixa de fazer sentido (o valor não foi repassado) e é apagado."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Informe o motivo.")
    motivo = motivo.strip()
    if len(motivo) > LIMITE_MOTIVO:
        raise ValueError(f"O motivo pode ter até {LIMITE_MOTIVO} caracteres.")
    r = query_one("SELECT * FROM repasses WHERE id = ? AND organizacao_id = ?", (repasse_id, org_id))
    if not r:
        raise LookupError("Fechamento não encontrado.")
    pessoa = query_one("SELECT nome FROM usuarios WHERE id = ?", (r["profissional_id"],)) or {"nome": ""}
    with em_lote():
        for item in query("SELECT consulta_id FROM repasse_itens WHERE repasse_id = ?", (repasse_id,)):
            execute("""DELETE FROM repasse_ajustes WHERE organizacao_id = ? AND origem = 'estorno'
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
    """Só o ajuste ainda pendente (fora de fechamento)."""
    a = query_one("SELECT * FROM repasse_ajustes WHERE id = ? AND organizacao_id = ?", (ajuste_id, org_id))
    if not a:
        raise LookupError("Ajuste não encontrado.")
    if a["repasse_id"] is not None:
        raise Conflito("Este ajuste já está num repasse pago. Desfaça o fechamento para mexer nele.")
    with em_lote():
        execute("DELETE FROM repasse_ajustes WHERE id = ? AND repasse_id IS NULL", (ajuste_id,))
        log_auditoria(org_id, usuario["id"], "excluir", "repasse_ajuste", ajuste_id,
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


# ------------------------------------------------------------------ estorno depois do repasse

def _sessoes_repassadas_da_cobranca(cob):
    """[(sessão, paga)] das sessões já repassadas que dependem desta cobrança. "Paga" pela
    mesma regra do relatório (`_avaliar`), com a base 'procedimento': estar paga não depende
    da base, e assim a espera do fim do mês (só do rateio) não parece estorno."""
    org_id = cob["organizacao_id"]
    if not query_one("SELECT 1 FROM repasses WHERE organizacao_id = ? LIMIT 1", (org_id,)):
        return []
    hoje = ausencias_service.hoje_brasilia().isoformat()
    ctx = _carregar(org_id, "9999-12-31", hoje)
    mes = str(cob["periodo_inicio"] or "")[:10]
    saida = []
    for s in ctx["sessoes"]:
        if s["repasse_id"] is None:
            continue
        if s["tipo"] == "avulsa":
            ligada = s["item"]["cobranca_id"] == cob["id"]
        elif s["tipo"] == "pacote":
            ligada = cob["tipo"] == "pacote" and s["consumo"]["acordo_id"] == cob["acordo_id"]
        elif s["tipo"] == "mensalidade":
            ligada = (cob["tipo"] == "mensalidade" and s["acordo"]["id"] == cob["acordo_id"]
                      and s["mes"] == mes)
        else:
            ligada = False
        if ligada:
            paga = _avaliar(s, "procedimento", ctx["pacotes"], ctx["mensalidades"], ctx["contam_mes"], hoje)[0]
            saida.append((s, paga))
    return saida


def _registrar_falha(cob, cobranca_id, exc):
    try:
        log_evento(cob["organizacao_id"] if cob else None, "aviso_repasse_falhou", "cobranca", cobranca_id,
                   cob["paciente_id"] if cob else None, {"erro": exc.__class__.__name__})
    except Exception:   # o aviso nunca derruba quem estornou
        pass


def avisar_estorno(cobranca_id):
    """Depois do commit de um estorno: cada sessão desta cobrança que já foi repassada e deixou
    de estar paga vira um ajuste negativo (o valor do profissional) no próximo fechamento, uma
    vez por sessão, e os gestores são avisados. Nunca levanta exceção; devolve quantos criou."""
    cob = None
    criados = []
    try:
        cob = query_one("SELECT * FROM cobrancas WHERE id = ?", (cobranca_id,))
        if not cob:
            return 0
        perdidas = [s for s, paga in _sessoes_repassadas_da_cobranca(cob) if not paga]
        if not perdidas:
            return 0
        with em_lote():
            for s in perdidas:
                if query_one("SELECT 1 FROM repasse_ajustes WHERE origem = 'estorno' AND consulta_id = ?",
                             (s["consulta_id"],)):
                    continue
                item = query_one("""SELECT ri.profissional_centavos, ri.data_hora, ri.paciente_nome,
                                           r.profissional_id, r.pago_em
                                    FROM repasse_itens ri JOIN repasses r ON r.id = ri.repasse_id
                                    WHERE ri.consulta_id = ?""", (s["consulta_id"],))
                valor = int(item["profissional_centavos"] or 0) if item else 0
                if valor <= 0:
                    continue
                descricao = (f"Estorno: {item['paciente_nome'] or s['paciente_nome']} em "
                             f"{_dd_mm(item['data_hora'] or s['data_hora'])} — já repassado em "
                             f"{_dd_mm(item['pago_em'])}")
                aid = execute("""INSERT INTO repasse_ajustes (organizacao_id, profissional_id, descricao,
                                                              valor_centavos, origem, consulta_id)
                                 VALUES (?, ?, ?, ?, 'estorno', ?)""",
                              (cob["organizacao_id"], item["profissional_id"], descricao, -valor, s["consulta_id"]))
                log_auditoria(cob["organizacao_id"], None, "criar", "repasse_ajuste", aid,
                              f"estorno da cobrança {cobranca_id} · {descricao} · {-valor} centavos")
                criados.append((item["profissional_id"], descricao, valor))
    except Exception as exc:
        if not _violacao_integridade(exc):   # duplicata = outra rodada já avisou
            _registrar_falha(cob, cobranca_id, exc)
        return 0
    if not criados:
        return 0

    try:
        org_id = cob["organizacao_id"]
        if len(criados) == 1:
            pid, descricao, valor = criados[0]
            nome = (query_one("SELECT nome FROM usuarios WHERE id = ?", (pid,)) or {}).get("nome") or "o profissional"
            texto = f"{descricao}. {rregras._brl(valor)} entra como desconto no próximo repasse de {nome}."
        else:
            total = sum(c[2] for c in criados)
            texto = (f"{len(criados)} sessões já repassadas tiveram o pagamento estornado ({cob['descricao']}). "
                     f"{rregras._brl(total)} entra como desconto nos próximos repasses.")
        with em_lote():
            for gestor in query("SELECT id FROM usuarios WHERE organizacao_id = ? AND papel = 'gestor' AND ativo = 1",
                                (org_id,)):
                criar_notificacao(gestor["id"], "Confira o repasse no Financeiro", texto,
                                  tipo="cobranca_familia", entidade="cobranca", entidade_id=cobranca_id)
    except Exception as exc:   # o ajuste fica; só o sino falhou
        _registrar_falha(cob, cobranca_id, exc)
    return len(criados)
