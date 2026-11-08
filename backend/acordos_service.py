"""Acordos de pagamento das famílias (financeiro etapa 1, 07/11/2026)."""
import sqlite3
from datetime import date

from db import query, query_one, execute, em_lote, log_auditoria
import cobranca_regras as regras

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


def sessoes_sem_acordo(org_id, paciente_id, especialidade, hoje):
    """Sessões que contam (realizada, ou faltou com fin_cobrar_falta) até `hoje`,
    sem item de cobrança, sem decisão 'nao_cobrar' e sem acordo ativo aplicável.
    paciente_id None = a clínica toda."""
    org = query_one("SELECT fin_cobrar_falta FROM organizacoes WHERE id = ?", (org_id,))
    cobrar_falta = bool(org and org["fin_cobrar_falta"])
    sql = """SELECT c.id AS consulta_id, c.paciente_id, p.nome AS paciente_nome, c.data_hora,
                    prof.nome AS profissional_nome, c.especialidade, c.status,
                    pr.nome AS procedimento_nome, c.procedimento_valor_centavos
             FROM consultas c
             JOIN pacientes p ON p.id = c.paciente_id
             JOIN usuarios prof ON prof.id = c.profissional_id
             LEFT JOIN procedimentos pr ON pr.id = c.procedimento_id
             WHERE p.organizacao_id = ?
               AND c.status IN ('realizada', 'faltou')
               AND NOT EXISTS (SELECT 1 FROM cobranca_itens i WHERE i.consulta_id = c.id)
               AND NOT EXISTS (SELECT 1 FROM consulta_decisao_cobranca d
                               WHERE d.consulta_id = c.id AND d.decisao = 'nao_cobrar')"""
    params = [org_id]
    if paciente_id is not None:
        sql += " AND c.paciente_id = ?"
        params.append(paciente_id)
    sql += " ORDER BY c.data_hora, c.id"
    filtro = regras.normalizar_especialidade(especialidade) if especialidade else None
    acordos_por_paciente = {}
    saida = []
    for r in query(sql, tuple(params)):
        dia = str(r["data_hora"])[:10]
        if dia > hoje or not regras.status_gera_cobranca(r["status"], cobrar_falta):
            continue
        esp = regras.normalizar_especialidade(r["especialidade"])
        if filtro and not regras.mesma_especialidade(esp, filtro):
            continue
        pid = r["paciente_id"]
        if pid not in acordos_por_paciente:
            acordos_por_paciente[pid] = query(
                "SELECT * FROM acordos_pagamento WHERE paciente_id = ? AND status = 'ativo'", (pid,))
        if regras.escolher_acordo(acordos_por_paciente[pid], esp, dia):
            continue
        saida.append({
            "consulta_id": r["consulta_id"], "paciente_id": pid, "paciente_nome": r["paciente_nome"],
            "data_hora": r["data_hora"], "profissional_nome": r["profissional_nome"],
            "especialidade": esp, "procedimento_nome": r["procedimento_nome"],
            "procedimento_valor_centavos": r["procedimento_valor_centavos"],
        })
    return saida


def _conflito():
    return ConflitoAcordo("Já existe um acordo ativo para essa especialidade.")


def criar(org_id, paciente_id, dados, usuario, incluir_consultas):
    esp = dados["especialidade"]
    ativos = query("SELECT especialidade FROM acordos_pagamento WHERE paciente_id = ? AND status = 'ativo'",
                   (paciente_id,))
    if any(regras.mesma_especialidade(a["especialidade"], esp) for a in ativos):
        raise _conflito()
    inicio = dados["inicio"]
    if incluir_consultas:
        # só sessões que contam e não têm acordo (inclui as de antes do início do acordo novo)
        validas = {s["consulta_id"]: s for s in sessoes_sem_acordo(org_id, paciente_id, None, "9999-12-31")}
        for cid in incluir_consultas:
            s = validas.get(cid)
            if not s or (esp != "*" and not regras.mesma_especialidade(s["especialidade"], esp)):
                raise ValueError("Uma das sessões escolhidas não pode entrar neste acordo.")
            inicio = min(inicio, str(s["data_hora"])[:10])
    fim = dados.get("fim")
    if fim and fim < inicio:
        raise ValueError("O fim não pode ser antes do início.")
    try:
        with em_lote():
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
            log_auditoria(org_id, usuario["id"], "criar", "acordo_pagamento", acordo_id,
                          f"{dados['tipo']} · {esp}")
    except sqlite3.IntegrityError:
        raise _conflito()
    except Exception as e:  # no Postgres a violação única é outra classe (IntegrityError do psycopg2)
        if type(e).__name__ in ("UniqueViolation", "IntegrityError"):
            raise _conflito()
        raise
    return acordo_id


def encerrar(acordo_id, data_fim, usuario):
    a = query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (acordo_id,))
    if not a:
        raise LookupError("Acordo não encontrado.")
    if a["status"] != "ativo":
        raise ConflitoAcordo("Este acordo já foi encerrado.")
    fim = _data(data_fim)
    if not fim:
        raise ValueError("Data de fim inválida.")
    if fim < str(a["inicio"])[:10]:
        raise ValueError("O fim não pode ser antes do início.")
    execute("UPDATE acordos_pagamento SET status = 'encerrado', fim = ?, encerrado_em = CURRENT_TIMESTAMP WHERE id = ?",
            (fim, acordo_id))
    log_auditoria(a["organizacao_id"], usuario["id"], "encerrar", "acordo_pagamento", acordo_id, f"fim {fim}")


def atualizar(acordo_id, corpo, usuario):
    """Só fim, vence_dias, dia_vencimento e valor da mensalidade."""
    a = query_one("SELECT * FROM acordos_pagamento WHERE id = ?", (acordo_id,))
    if not a:
        raise LookupError("Acordo não encontrado.")
    if a["status"] != "ativo":
        raise ConflitoAcordo("Este acordo já foi encerrado.")
    campos, params = [], []
    if "fim" in corpo:
        fim = None
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
    execute(f"UPDATE acordos_pagamento SET {', '.join(c + ' = ?' for c in campos)} WHERE id = ?", tuple(params))
    log_auditoria(a["organizacao_id"], usuario["id"], "atualizar", "acordo_pagamento", acordo_id, ", ".join(campos))
