"""Acordos de pagamento das famílias (financeiro etapa 1, 07/11/2026)."""
import sqlite3
from datetime import date, timedelta

from db import query, query_one, execute, em_lote, log_auditoria
import ausencias_service
import cobranca_regras as regras
import pagamento_service

TIPOS = ("avulsa", "mensalidade", "pacote")
CICLOS = ("consulta", "quinzenal", "mensal")


class ConflitoAcordo(ValueError):
    """Já existe acordo ativo para a especialidade (vira 409 na rota)."""


def _data(valor):
    try:
        t = str(valor)
        if len(t) != 10:
            return None
        date.fromisoformat(t)
        return t
    except (ValueError, TypeError):
        return None


def _inteiro(valor, minimo, maximo):
    if isinstance(valor, bool) or not isinstance(valor, int):
        return None
    return valor if minimo <= valor <= maximo else None


def validar(corpo, hoje):
    """Devolve (dados_limpos, erro)."""
    corpo = corpo or {}
    tipo = corpo.get("tipo")
    if tipo not in TIPOS:
        return None, "Escolha o tipo do acordo."
    esp = corpo.get("especialidade")
    if esp is None or esp == "":
        esp = "Geral"
    if not isinstance(esp, str):
        return None, "Especialidade inválida."
    esp = esp.strip() or "Geral"
    if len(esp) > 60:
        return None, "Especialidade com mais de 60 caracteres."
    if corpo.get("inicio") not in (None, ""):
        inicio = _data(corpo["inicio"])
        if not inicio:
            return None, "Data de início inválida."
    else:
        inicio = hoje
    fim = None
    if corpo.get("fim") not in (None, ""):
        fim = _data(corpo["fim"])
        if not fim:
            return None, "Data de fim inválida."
        if fim < inicio:
            return None, "O fim não pode ser antes do início."
    d = {"tipo": tipo, "especialidade": esp, "inicio": inicio, "fim": fim, "ciclo": None,
         "vence_dias": 5, "valor_centavos": None, "dia_vencimento": None, "sessoes_total": None,
         "parcelas": None, "primeiro_vencimento": None}
    if corpo.get("vence_dias") is not None:
        v = _inteiro(corpo.get("vence_dias"), 0, 60)
        if v is None:
            return None, "Dias para vencer deve ficar entre 0 e 60."
        d["vence_dias"] = v
    if tipo == "avulsa":
        if corpo.get("ciclo") not in CICLOS:
            return None, "Escolha o ciclo da cobrança (por consulta, quinzenal ou mensal)."
        d["ciclo"] = corpo["ciclo"]
    elif tipo == "mensalidade":
        d["valor_centavos"] = _inteiro(corpo.get("valor_centavos"), 1, 100_000_000)
        if d["valor_centavos"] is None:
            return None, "Informe o valor da mensalidade."
        d["dia_vencimento"] = _inteiro(corpo.get("dia_vencimento"), 1, 28)
        if d["dia_vencimento"] is None:
            return None, "O dia de vencimento deve ficar entre 1 e 28."
    else:
        d["sessoes_total"] = _inteiro(corpo.get("sessoes_total"), 1, 200)
        if d["sessoes_total"] is None:
            return None, "Informe a quantidade de sessões (1 a 200)."
        d["valor_centavos"] = _inteiro(corpo.get("valor_centavos"), 1, 100_000_000)
        if d["valor_centavos"] is None:
            return None, "Informe o valor do pacote."
        d["parcelas"] = _inteiro(corpo.get("parcelas"), 1, 24)
        if d["parcelas"] is None:
            return None, "As parcelas devem ficar entre 1 e 24."
        d["primeiro_vencimento"] = _data(corpo.get("primeiro_vencimento"))
        if not d["primeiro_vencimento"]:
            return None, "Informe o primeiro vencimento."
    return d, None


# Uma sessão já cobrada (item) ou consumida do pacote continua valendo enquanto
# estiver nestes status; mudar a chave "cobrar falta" não desfaz o que já foi cobrado.
STATUS_COBRAVEIS = ("realizada", "faltou")


def _dia_seguinte(hoje):
    try:
        return (date.fromisoformat(str(hoje)[:10]) + timedelta(days=1)).isoformat()
    except (ValueError, OverflowError):
        return "9999-99-99"   # '9999-12-31' (sem limite): qualquer data passa


def chave_data_hora(data_hora, desempate=0):
    """Ordem cronológica mesmo com hora sem zero à esquerda ('9:00:00')."""
    _, minutos = ausencias_service.separar_data_hora(data_hora)
    return (str(data_hora or "")[:10], minutos if minutos is not None else -1, desempate)


def sessoes_que_contam(org_id, paciente_id, hoje):
    """A definição única de "sessão que conta" para a cobrança (financeiro, 07/11/2026):
    consulta da clínica com status que gera cobrança (realizada; faltou só com
    fin_cobrar_falta), na data de `hoje` ou antes, sem item de cobrança, sem decisão
    'nao_cobrar' e sem consumo de pacote. Em ordem cronológica.
    paciente_id None = a clínica toda."""
    org = query_one("SELECT fin_cobrar_falta FROM organizacoes WHERE id = ?", (org_id,))
    cobrar_falta = bool(org and org["fin_cobrar_falta"])
    sql = """SELECT c.id AS consulta_id, c.paciente_id, p.nome AS paciente_nome, c.data_hora,
                    prof.nome AS profissional_nome, c.especialidade, c.status,
                    pr.nome AS procedimento_nome, c.procedimento_valor_centavos,
                    d.valor_centavos AS decisao_valor_centavos,
                    v.acordo_id AS vinculo_acordo_id, v.incluida AS vinculo_incluida
             FROM consultas c
             JOIN pacientes p ON p.id = c.paciente_id
             JOIN usuarios prof ON prof.id = c.profissional_id
             LEFT JOIN procedimentos pr ON pr.id = c.procedimento_id
             LEFT JOIN consulta_decisao_cobranca d ON d.consulta_id = c.id AND d.decisao = 'valor'
             LEFT JOIN consulta_acordo_incluida v ON v.consulta_id = c.id
             WHERE p.organizacao_id = ?
               AND c.status IN ('realizada', 'faltou')
               AND c.data_hora < ?
               AND NOT EXISTS (SELECT 1 FROM cobranca_itens i WHERE i.consulta_id = c.id)
               AND NOT EXISTS (SELECT 1 FROM acordo_pacote_consumo pc WHERE pc.consulta_id = c.id)
               AND NOT EXISTS (SELECT 1 FROM consulta_decisao_cobranca dn
                               WHERE dn.consulta_id = c.id AND dn.decisao = 'nao_cobrar')"""
    params = [org_id, _dia_seguinte(hoje)]
    if paciente_id is not None:
        sql += " AND c.paciente_id = ?"
        params.append(paciente_id)
    saida = []
    for r in query(sql, tuple(params)):
        dia = str(r["data_hora"])[:10]
        if dia > hoje or not regras.status_gera_cobranca(r["status"], cobrar_falta):
            continue
        r = dict(r)
        r["dia"] = dia
        r["especialidade"] = regras.normalizar_especialidade(r["especialidade"])
        saida.append(r)
    saida.sort(key=lambda s: chave_data_hora(s["data_hora"], s["consulta_id"]))
    return saida


def acordos_por_paciente(org_id, paciente_id=None):
    """{paciente_id: [acordos]} — ativos e encerrados com fim (ver `acordo_da_sessao`)."""
    sql = "SELECT * FROM acordos_pagamento WHERE organizacao_id = ?"
    params = [org_id]
    if paciente_id is not None:
        sql += " AND paciente_id = ?"
        params.append(paciente_id)
    saida = {}
    for a in query(sql + " ORDER BY id", tuple(params)):
        saida.setdefault(a["paciente_id"], []).append(a)
    return saida


def acordo_da_sessao(acordos, especialidade, dia, sessao=None):
    """Acordo que cobre a sessão. Quem foi marcada ao criar um acordo fica nele, mesmo
    antes do início (`consulta_acordo_incluida`); quem foi deixada de fora não entra nele
    nem nos acordos anteriores a ele (a tabela guarda só a última decisão: ao criar um acordo,
    a sessão de fora já não estava em nenhum dos anteriores), mesmo dentro da vigência. Só um
    acordo mais novo pode cobri-la. Depois, os ativos (o específico vence o '*'); um acordo
    encerrado ainda cobre as sessões da sua vigência (início–fim), para que encerrar uma
    mensalidade não transforme as sessões já cobertas em "sem acordo".
    `sessao` é a linha de `sessoes_que_contam` (traz o vínculo)."""
    vinculo = (sessao or {}).get("vinculo_acordo_id")
    ultimo_de_fora = 0
    if vinculo:
        if (sessao or {}).get("vinculo_incluida"):
            for a in acordos:
                if a["id"] == vinculo:
                    return a
        else:
            ultimo_de_fora = vinculo
    ativos = [a for a in acordos if a["status"] == "ativo" and a["id"] > ultimo_de_fora]
    encerrados = [dict(a, status="ativo") for a in acordos
                  if a["status"] == "encerrado" and a.get("fim") and a["id"] > ultimo_de_fora]
    return regras.escolher_acordo(ativos + encerrados, especialidade, dia)


def pacote_usados(org_id):
    """{acordo_id: sessões consumidas} dos pacotes da clínica."""
    rows = query("""SELECT pc.acordo_id, COUNT(*) AS n FROM acordo_pacote_consumo pc
                    JOIN acordos_pagamento a ON a.id = pc.acordo_id
                    WHERE a.organizacao_id = ? GROUP BY pc.acordo_id""", (org_id,))
    return {r["acordo_id"]: r["n"] for r in rows}


def pacote_esgotado(acordo, usados):
    return acordo["tipo"] == "pacote" and usados.get(acordo["id"], 0) >= (acordo["sessoes_total"] or 0)


def sessoes_sem_acordo(org_id, paciente_id, especialidade, hoje):
    """Sessões que contam (`sessoes_que_contam`) sem acordo aplicável — inclusive
    as de um pacote que já acabou (a sessão não foi consumida e não cabe mais).
    paciente_id None = a clínica toda."""
    filtro = regras.normalizar_especialidade(especialidade) if especialidade else None
    acordos = acordos_por_paciente(org_id, paciente_id)
    usados = pacote_usados(org_id)
    saida = []
    for r in sessoes_que_contam(org_id, paciente_id, hoje):
        esp = r["especialidade"]
        if filtro and not regras.mesma_especialidade(esp, filtro):
            continue
        a = acordo_da_sessao(acordos.get(r["paciente_id"], []), esp, r["dia"], r)
        if a and not pacote_esgotado(a, usados):
            continue
        saida.append({
            "consulta_id": r["consulta_id"], "paciente_id": r["paciente_id"], "paciente_nome": r["paciente_nome"],
            "data_hora": r["data_hora"], "profissional_nome": r["profissional_nome"],
            "especialidade": esp, "procedimento_nome": r["procedimento_nome"],
            "procedimento_valor_centavos": r["procedimento_valor_centavos"], "status": r["status"],
            "valor_centavos": r["decisao_valor_centavos"] or r["procedimento_valor_centavos"] or 0,
        })
    return saida


def _conflito():
    return ConflitoAcordo("Já existe um acordo ativo para essa especialidade. "
                          "Encerre-o na ficha do paciente antes de criar outro.")


def _hoje():
    return ausencias_service.hoje_brasilia().isoformat()


def _vinculos_da_criacao(org_id, paciente_id, dados, incluir_consultas):
    """{consulta_id: incluida} das sessões sem acordo na criação. Só as marcadas entram
    (sem mexer no início do acordo). As desmarcadas dentro da vigência ficam registradas como
    "de fora": sem isso, a vigência as cobraria mesmo desmarcadas. Sem a lista (None), nada
    foi decidido e vale só a vigência."""
    if incluir_consultas is None:
        return {}
    esp = dados["especialidade"]
    # só sessões que contam e não têm acordo (inclui as de antes do início do acordo novo)
    validas = {s["consulta_id"]: s for s in sessoes_sem_acordo(org_id, paciente_id, None, "9999-12-31")}
    vinculos = {}
    for cid in incluir_consultas:
        s = validas.get(cid)
        if not s or (esp != "*" and not regras.mesma_especialidade(s["especialidade"], esp)):
            raise ValueError("Uma das sessões escolhidas não pode entrar neste acordo.")
        vinculos[cid] = 1
    fim = dados.get("fim")
    for cid, s in validas.items():
        dia = str(s["data_hora"])[:10]
        if (cid not in vinculos and dia >= dados["inicio"] and (not fim or dia <= fim)
                and (esp == "*" or regras.mesma_especialidade(s["especialidade"], esp))):
            vinculos[cid] = 0
    return vinculos


def criar(org_id, paciente_id, dados, usuario, incluir_consultas):
    esp = dados["especialidade"]
    conflitantes = [a for a in query("SELECT * FROM acordos_pagamento WHERE paciente_id = ? AND status = 'ativo'",
                                     (paciente_id,))
                    if regras.mesma_especialidade(a["especialidade"], esp)]
    usados = pacote_usados(org_id) if conflitantes else {}
    if any(not pacote_esgotado(a, usados) for a in conflitantes):
        raise _conflito()
    inicio = dados["inicio"]
    fim = dados.get("fim")
    if fim and fim < inicio:
        raise ValueError("O fim não pode ser antes do início.")
    vinculos = _vinculos_da_criacao(org_id, paciente_id, dados, incluir_consultas)
    hoje = _hoje()
    try:
        with em_lote():
            for a in conflitantes:   # pacote que acabou não trava o acordo novo
                fim_velho = min(str(a["fim"])[:10], hoje) if a["fim"] else hoje
                execute("""UPDATE acordos_pagamento SET status = 'encerrado', fim = ?, encerrado_em = CURRENT_TIMESTAMP
                           WHERE id = ?""", (fim_velho, a["id"]))
                log_auditoria(org_id, usuario["id"], "encerrar", "acordo_pagamento", a["id"],
                              f"pacote esgotado · fim {fim_velho}")
            acordo_id = execute(
                """INSERT INTO acordos_pagamento (organizacao_id, paciente_id, especialidade, tipo, ciclo,
                       vence_dias, valor_centavos, dia_vencimento, sessoes_total, parcelas,
                       primeiro_vencimento, inicio, fim, status, criado_por)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ativo', ?)""",
                (org_id, paciente_id, esp, dados["tipo"], dados.get("ciclo"), dados.get("vence_dias", 5),
                 dados.get("valor_centavos"), dados.get("dia_vencimento"), dados.get("sessoes_total"),
                 dados.get("parcelas"), dados.get("primeiro_vencimento"), inicio, fim, usuario["id"]))
            if dados["tipo"] == "pacote":
                lista = regras.parcelas_do_pacote(dados["valor_centavos"], dados["parcelas"],
                                                  dados["primeiro_vencimento"])
                n = len(lista)
                for i, (venc, valor) in enumerate(lista, start=1):
                    execute(
                        """INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status,
                               organizacao_id, acordo_id, tipo)
                           VALUES (?, ?, ?, ?, 'pendente', ?, ?, 'pacote')""",
                        (paciente_id, f"Pacote de {dados['sessoes_total']} sessões ({i}/{n})", valor, venc,
                         org_id, acordo_id))
            for cid, incluida in vinculos.items():
                execute("DELETE FROM consulta_acordo_incluida WHERE consulta_id = ?", (cid,))
                execute("INSERT INTO consulta_acordo_incluida (consulta_id, acordo_id, incluida) VALUES (?, ?, ?)",
                        (cid, acordo_id, incluida))
            log_auditoria(org_id, usuario["id"], "criar", "acordo_pagamento", acordo_id,
                          f"{dados['tipo']} · {esp}"
                          + (f" · {sum(vinculos.values())} sessão(ões) incluída(s)" if vinculos else ""))
    except sqlite3.IntegrityError:
        raise _conflito()
    except Exception as e:  # no Postgres a violação única é outra classe (IntegrityError do psycopg2)
        if type(e).__name__ in ("UniqueViolation", "IntegrityError"):
            raise _conflito()
        raise
    return acordo_id


def _reais(centavos):
    return f"R$ {centavos / 100:.2f}".replace(".", ",")


def _ajustar_mensalidades(a, fim_novo, usuario, hoje):
    """O fim da mensalidade mudou: a cobrança de cada mês afetado acompanha
    (`mensalidade_do_mes`). Sem pagamento, recalcula; valor 0 cancela (e volta, se o fim for
    estendido de novo: o índice só deixa uma cobrança por mês). Com pagamento, o valor não
    muda: fica o aviso "revisar". Cobrança cancelada pelo gestor nunca volta. A conta usa o preço
    com que o mês foi gerado (`mensalidade_preco_centavos`): o preço atual do acordo só vale para
    os meses seguintes.
    Chame dentro de um `em_lote`."""
    if a["tipo"] != "mensalidade" or str(a["fim"] or "")[:10] == str(fim_novo or "")[:10]:
        return
    org_id = a["organizacao_id"]
    # trava as linhas: baixa ou webhook simultâneos se enfileiram
    execute("UPDATE cobrancas SET status = status WHERE acordo_id = ? AND tipo = 'mensalidade'", (a["id"],))
    fim_txt = f"{fim_novo[8:10]}/{fim_novo[5:7]}/{fim_novo[:4]}" if fim_novo else "sem fim"
    for c in query("SELECT * FROM cobrancas WHERE acordo_id = ? AND tipo = 'mensalidade' ORDER BY periodo_inicio", (a["id"],)):
        ano, mes = int(c["periodo_inicio"][:4]), int(c["periodo_inicio"][5:7])
        preco = c["mensalidade_preco_centavos"] or a["valor_centavos"] or 0
        antes = regras.mensalidade_do_mes(preco, ano, mes, a["inicio"], a["fim"])
        depois = regras.mensalidade_do_mes(preco, ano, mes, a["inicio"], fim_novo)
        if antes == depois:
            continue
        rotulo = f"Mensalidade {mes:02d}/{ano}"
        if c["status"] == "cancelado":
            if c["valor_centavos"] != 0 or depois <= 0:
                continue   # cancelada à mão (o valor fica) ou continua sem valor
            execute("UPDATE cobrancas SET status = 'pendente', valor_centavos = ?, vencimento = ? WHERE id = ?",
                    (depois, regras.vencimento_minimo(c["vencimento"], hoje), c["id"]))
            pagamento_service.recalcular_status(c["id"], hoje)
            log_auditoria(org_id, usuario["id"], "recalcular", "cobranca", c["id"],
                          f"{rotulo}: fim do acordo {fim_txt}: voltou com {depois} centavos")
            continue
        if pagamento_service.pago_centavos(c["id"]) > 0:
            texto = f"{rotulo}: o fim do acordo mudou ({fim_txt}) e o valor seria {_reais(depois)}"
            pagamento_service.marcar_revisar(c["id"], texto)
            log_auditoria(org_id, usuario["id"], "revisar", "cobranca", c["id"], texto)
            continue
        if depois <= 0:
            execute("UPDATE cobrancas SET status = 'cancelado', valor_centavos = 0, desconto_centavos = 0 WHERE id = ?",
                    (c["id"],))
        else:
            execute("UPDATE cobrancas SET valor_centavos = ?, desconto_centavos = ? WHERE id = ?",
                    (depois, min(c["desconto_centavos"] or 0, depois), c["id"]))
            pagamento_service.recalcular_status(c["id"], hoje)
        log_auditoria(org_id, usuario["id"], "recalcular", "cobranca", c["id"],
                      f"{rotulo}: fim do acordo {fim_txt}: {c['valor_centavos']} → {depois} centavos")


def encerrar(acordo_id, data_fim, usuario):
    """Encerra numa data de hoje para trás e nunca depois do fim atual (data_fim None = hoje
    ou o fim que já passou). Fim futuro é com Editar: o acordo segue ativo até lá."""
    a = query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (acordo_id,))
    if not a:
        raise LookupError("Acordo não encontrado.")
    if a["status"] != "ativo":
        raise ConflitoAcordo("Este acordo já foi encerrado.")
    hoje = _hoje()
    fim_atual = str(a["fim"])[:10] if a["fim"] else None
    fim = _data(data_fim) if data_fim is not None else min(hoje, fim_atual or hoje)
    if not fim:
        raise ValueError("Data de fim inválida.")
    if fim < str(a["inicio"])[:10]:
        raise ValueError("O fim não pode ser antes do início.")
    if fim > hoje:
        raise ValueError("O encerramento não aceita data futura. Para marcar um fim futuro, use Editar.")
    if fim_atual and fim > fim_atual:
        raise ValueError("A data é depois do fim atual do acordo. Para mudar o fim, use Editar.")
    with em_lote():
        execute("UPDATE acordos_pagamento SET status = 'encerrado', fim = ?, encerrado_em = CURRENT_TIMESTAMP WHERE id = ?",
                (fim, acordo_id))
        _ajustar_mensalidades(a, fim, usuario, hoje)
        log_auditoria(a["organizacao_id"], usuario["id"], "encerrar", "acordo_pagamento", acordo_id, f"fim {fim}")


def atualizar(acordo_id, corpo, usuario):
    """Só fim, vence_dias, dia_vencimento e valor da mensalidade."""
    a = query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (acordo_id,))
    if not a:
        raise LookupError("Acordo não encontrado.")
    if a["status"] != "ativo":
        raise ConflitoAcordo("Este acordo já foi encerrado.")
    campos, params = [], []
    mudar_fim = "fim" in corpo
    fim = None
    if mudar_fim:
        if corpo["fim"] not in (None, ""):
            fim = _data(corpo["fim"])
            if not fim:
                raise ValueError("Data de fim inválida.")
            if fim < str(a["inicio"])[:10]:
                raise ValueError("O fim não pode ser antes do início.")
        campos.append("fim")
        params.append(fim)
    if "vence_dias" in corpo:
        v = _inteiro(corpo["vence_dias"], 0, 60)
        if v is None:
            raise ValueError("Dias para vencer deve ficar entre 0 e 60.")
        campos.append("vence_dias")
        params.append(v)
    if a["tipo"] == "mensalidade":
        if "dia_vencimento" in corpo:
            v = _inteiro(corpo["dia_vencimento"], 1, 28)
            if v is None:
                raise ValueError("O dia de vencimento deve ficar entre 1 e 28.")
            campos.append("dia_vencimento")
            params.append(v)
        if "valor_centavos" in corpo:
            v = _inteiro(corpo["valor_centavos"], 1, 100_000_000)
            if v is None:
                raise ValueError("Informe o valor da mensalidade.")
            campos.append("valor_centavos")
            params.append(v)
    if not campos:
        raise ValueError("Nada para alterar.")
    params.append(acordo_id)
    with em_lote():
        execute(f"UPDATE acordos_pagamento SET {', '.join(c + ' = ?' for c in campos)} WHERE id = ?", tuple(params))
        if mudar_fim:
            _ajustar_mensalidades(a, fim, usuario, _hoje())
        log_auditoria(a["organizacao_id"], usuario["id"], "atualizar", "acordo_pagamento", acordo_id, ", ".join(campos))
