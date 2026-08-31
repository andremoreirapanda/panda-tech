"""
Popula o banco de dados com uma clínica de demonstração completa,
para que todas as telas ("wow moments" do Documento 11) tenham dados reais.

Rode: python seed.py
"""
import os
import sqlite3
import json
from datetime import datetime, timedelta

from db import DB_PATH, dict_factory
from auth import hash_senha

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def resetar_banco():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = conectar()
    with open(os.path.join(BASE_DIR, "schema.sql")) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def usuario(conn, org_id, nome, email, papel, especialidade=None, avatar="🙂", senha="mudar123", cor_agenda=None):
    senha_hash, salt = hash_senha(senha)
    cur = conn.execute(
        """INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel, especialidade, avatar_emoji, cor_agenda)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, nome, email, senha_hash, salt, papel, especialidade, avatar, cor_agenda or "#5B4FE9"),
    )
    conn.commit()
    return cur.lastrowid


# ------------------------------------------------------------------ MÓDULO 07 — Diário Terapêutico
# Exemplo literal do documento de especificação, usado para o paciente João Pedro.
DIARIOS_POR_PACIENTE = {
    "João Pedro": [
        {
            "evolucao": "João apresentou melhora significativa na produção dos fonemas /P/ e /B/. Ainda demonstra "
                        "dificuldade para iniciar frases espontaneamente, porém já responde com mais segurança "
                        "quando estimulado.",
            "positivos": ["Participou bem da sessão.", "Demonstrou interesse pelas atividades.", "Melhor interação visual."],
            "atencao": ["Continuar estimulando frases completas.", "Reforçar os exercícios de nomeação."],
            "objetivo": "Incentivar João a formar frases com três palavras durante as atividades em casa.",
            "mensagem": "João está evoluindo muito bem. O apoio de vocês em casa está fazendo diferença. Continuem "
                        "realizando as atividades diariamente, mesmo que por poucos minutos.",
        },
        {
            "evolucao": "Nesta sessão, João iniciou duas frases espontaneamente sem estímulo direto — um avanço "
                        "importante em relação à semana anterior. A articulação dos fonemas /P/ e /B/ segue consistente.",
            "positivos": ["Iniciou frases espontâneas.", "Manteve atenção por toda a sessão.", "Comemorou os próprios acertos."],
            "atencao": ["Ainda troca /T/ por /D/ em algumas palavras."],
            "objetivo": "Praticar nomeação de objetos da casa, incentivando frases com sujeito + verbo + objeto.",
            "mensagem": "Semana de conquistas! João começou a puxar assunto sozinho durante a atividade. Continuem "
                        "comemorando cada tentativa dele.",
        },
    ],
}


def DIARIOS_PADRAO(nome):
    primeiro_nome = nome.split(" ")[0]
    return [
        {
            "evolucao": f"{primeiro_nome} participou ativamente da sessão, respondendo bem às propostas terapêuticas "
                        f"e mantendo bom vínculo com o profissional ao longo de todo o atendimento.",
            "positivos": ["Boa disposição para as atividades.", "Manteve o foco na maior parte da sessão."],
            "atencao": ["Precisa de mais tempo para se adaptar a atividades novas."],
            "objetivo": f"Reforçar em casa as atividades sugeridas, com sessões curtas e frequentes.",
            "mensagem": f"{primeiro_nome} teve uma boa semana! Continuem incentivando a prática em casa, mesmo que "
                        f"por poucos minutos por dia — isso faz toda diferença.",
        },
        {
            "evolucao": f"{primeiro_nome} apresentou avanços perceptíveis em relação à sessão anterior, "
                        f"especialmente na iniciativa para participar das atividades propostas.",
            "positivos": ["Maior autonomia nas atividades.", "Boa interação com o profissional."],
            "atencao": ["Seguir de perto a evolução nas próximas semanas."],
            "objetivo": f"Consolidar os ganhos da semana com repetição das atividades já dominadas.",
            "mensagem": f"Semana positiva para {primeiro_nome}! O empenho da família em casa está refletindo direto "
                        f"nas sessões.",
        },
    ]


def main():
    conn = resetar_banco()
    print("🗄️  Banco recriado a partir do schema.sql")
    hoje = datetime.now()

    # ------------------------------------------------------------- Planos comerciais
    import json
    planos_data = [
        ("starter", "Starter", 29700, 8, 3, 0,
         ["Até 8 pacientes ativos", "Até 3 profissionais", "Jornada terapêutica completa",
          "Biblioteca de exercícios", "Chat com famílias", "Gamificação (Mundo da Criança)",
          "Suporte por e-mail"], "#6A6280", 1),
        ("pro", "Pro", 69700, 30, 10, 1,
         ["Tudo do Starter", "Até 30 pacientes ativos", "Até 10 profissionais", "1 secretária administrativa",
          "Indicadores avançados", "Mural da clínica", "Integrações (WhatsApp, Google Agenda)",
          "Suporte prioritário"], "#5B4FE9", 2),
        ("enterprise", "Enterprise", 149700, None, None, None,
         ["Tudo do Pro", "Pacientes e profissionais ilimitados", "Secretárias administrativas ilimitadas",
          "Múltiplas unidades", "Gerente de conta dedicado", "Onboarding assistido", "SLA garantido"], "#E8875E", 3),
    ]
    for codigo, nome, preco, lim_pac, lim_prof, lim_sec, recursos, cor, ordem in planos_data:
        conn.execute(
            """INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_pacientes, limite_profissionais,
                                    limite_secretarias, recursos_json, cor, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (codigo, nome, preco, lim_pac, lim_prof, lim_sec, json.dumps(recursos, ensure_ascii=False), cor, ordem),
        )
    conn.commit()

    # ------------------------------------------------------------- Organização
    cur = conn.execute(
        """INSERT INTO organizacoes (nome, cor_primaria, cor_secundaria, logo_emoji, plano, status_comercial,
                                      assinatura_inicio, contato_nome, contato_email, contato_telefone,
                                      origem_lead, observacoes_comerciais)
           VALUES (?, ?, ?, ?, ?, 'ativa', ?, ?, ?, ?, 'indicação', ?)""",
        ("Clínica Encantar", "#5B4FE9", "#FFB84D", "🌟", "pro",
         (hoje - timedelta(days=94)).strftime("%Y-%m-%d"), "André Martins",
         "andre@clinicaencantar.com.br", "(31) 99876-5432",
         "Cliente engajado — 7 de 30 pacientes do plano Pro. Bom fit para case de sucesso."),
    )
    org_id = cur.lastrowid
    conn.commit()

    # ------------------------------------------------------------- Admin do SaaS
    admin_id = usuario(conn, None, "Admin Encanto", "admin@encantoemcasa.com", "admin_master", avatar="🛠️", senha="admin123")

    # ------------------------------------------------------------- Biblioteca da Plataforma (Doc 31A/32)
    # organizacao_id NULL = visível para TODAS as clínicas automaticamente.
    exercicios_plataforma = [
        ("Boas-vindas: como usar o Mundo da Criança", "video", "facil", "", 2, 12,
         "Vídeo curto explicando pra família como funciona a plataforma e as missões.", "onboarding,tutorial"),
        ("Respiração do balão", "atividade", "facil", "Fonoaudiologia", 3, 8,
         "Exercício clássico de respiração diafragmática, universal entre clínicas de fono.", "respiracao,linguagem"),
        ("Trilha sensorial com texturas", "atividade", "facil", "Terapia Ocupacional", 2, 7,
         "Percurso simples com diferentes texturas para estimulação sensorial básica.", "sensorial,motricidade"),
        ("Cartas de emoções para nomear", "jogo", "medio", "Psicologia", 4, 10,
         "Conjunto de cartas com expressões faciais para trabalhar reconhecimento emocional.", "emocoes,social"),
        ("Sequência de rotina em figuras", "atividade", "facil", "Psicopedagogia", 3, 9,
         "Apoio visual de rotina diária, útil em praticamente qualquer especialidade.", "rotina,cognicao"),
    ]
    for titulo, tipo, dif, esp, fmin, fmax, desc, tags in exercicios_plataforma:
        conn.execute(
            """INSERT INTO exercicios (organizacao_id, categoria_id, titulo, descricao, tipo, conteudo_url,
                                        faixa_etaria_min, faixa_etaria_max, dificuldade, especialidade, tags)
               VALUES (NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (titulo, desc, tipo, "https://exemplo.com/biblioteca-plataforma", fmin, fmax, dif, esp, tags),
        )
    conn.commit()

    # ------------------------------------------------------------- Gestor
    gestor_id = usuario(conn, org_id, "André Martins", "andre@clinicaencantar.com.br", "gestor", avatar="👨‍💼", senha="gestor123")

    # ------------------------------------------------------------- Profissionais
    prof1 = usuario(conn, org_id, "Camila Ribeiro", "camila@clinicaencantar.com.br", "profissional", "Fonoaudiologia", "👩‍⚕️", "prof123", cor_agenda="#5B4FE9")
    prof2 = usuario(conn, org_id, "Rafael Souza", "rafael@clinicaencantar.com.br", "profissional", "Terapia Ocupacional", "🧑‍⚕️", "prof123", cor_agenda="#E8385A")
    prof3 = usuario(conn, org_id, "Juliana Alves", "juliana@clinicaencantar.com.br", "profissional", "Psicopedagogia", "👩‍🏫", "prof123", cor_agenda="#10B981")

    # ------------------------------------------------------------- Categorias & Exercícios (Biblioteca)
    categorias = {}
    for nome, icone in [("Linguagem", "🗣️"), ("Motricidade", "🤸"), ("Cognição", "🧠"), ("Sensorial", "🖐️"), ("Social", "🤝")]:
        cur = conn.execute(
            "INSERT INTO categorias_exercicio (organizacao_id, nome, icone_emoji) VALUES (?, ?, ?)",
            (org_id, nome, icone),
        )
        categorias[nome] = cur.lastrowid
    conn.commit()

    exercicios_data = [
        ("Nomear objetos do dia a dia", "Linguagem", "video", "facil", "Fonoaudiologia", 2, 5),
        ("Sopro com canudinho", "Linguagem", "atividade", "facil", "Fonoaudiologia", 3, 6),
        ("Contação de história com fantoches", "Linguagem", "video", "medio", "Fonoaudiologia", 3, 8),
        ("Circuito motor com almofadas", "Motricidade", "video", "medio", "Terapia Ocupacional", 4, 9),
        ("Recorte e colagem livre", "Motricidade", "atividade", "facil", "Terapia Ocupacional", 3, 7),
        ("Equilíbrio em uma perna só", "Motricidade", "jogo", "medio", "Terapia Ocupacional", 4, 10),
        ("Jogo da memória de emoções", "Cognição", "jogo", "medio", "Psicopedagogia", 4, 9),
        ("Sequência lógica com blocos", "Cognição", "atividade", "dificil", "Psicopedagogia", 5, 10),
        ("Caixa sensorial de texturas", "Sensorial", "atividade", "facil", "Terapia Ocupacional", 2, 6),
        ("Massinha caseira: apertar e moldar", "Sensorial", "video", "facil", "Terapia Ocupacional", 2, 7),
        ("Roda de brincar com outra criança", "Social", "atividade", "medio", "Psicopedagogia", 3, 8),
        ("Reconhecer expressões faciais", "Social", "jogo", "facil", "Psicopedagogia", 3, 7),
    ]
    exercicio_ids = {}
    for titulo, cat, tipo, dif, esp, fmin, fmax in exercicios_data:
        cur = conn.execute(
            """INSERT INTO exercicios (organizacao_id, categoria_id, titulo, descricao, tipo, conteudo_url,
                                        faixa_etaria_min, faixa_etaria_max, dificuldade, especialidade, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (org_id, categorias[cat], titulo, f"Atividade terapêutica: {titulo.lower()}.", tipo,
             "https://exemplo.com/midia", fmin, fmax, dif, esp, cat.lower()),
        )
        exercicio_ids[titulo] = cur.lastrowid
    conn.commit()

    # ------------------------------------------------------------- Medalhas padrão
    from gamificacao_service import garantir_medalhas_padrao
    garantir_medalhas_padrao()

    # ------------------------------------------------------------- Pacientes + Responsáveis + Jornadas
    pacientes_data = [
        # nome, nascimento, avatar, profissional_principal, responsavel(nome,email), objetivo
        ("João Pedro", "2020-03-12", "🐻", prof1, ("Ana Martins", "ana@familia.com"), "Desenvolver linguagem expressiva e ampliar vocabulário funcional."),
        ("Maria Luiza", "2019-07-22", "🐰", prof1, ("Fernanda Costa", "fernanda@familia.com"), "Melhorar articulação e fluência na fala."),
        ("Miguel", "2018-11-05", "🦁", prof2, ("Patrícia Lima", "patricia@familia.com"), "Aprimorar coordenação motora fina e ampla."),
        ("Alice", "2021-01-30", "🐼", prof2, ("Carla Nunes", "carla@familia.com"), "Desenvolver integração sensorial e autorregulação."),
        ("Davi", "2017-09-18", "🐨", prof3, ("Roberto Dias", "roberto@familia.com"), "Fortalecer habilidades cognitivas e de atenção sustentada."),
        ("Sofia", "2020-06-02", "🦊", prof3, ("Mariana Torres", "mariana@familia.com"), "Desenvolver habilidades sociais e reconhecimento emocional."),
        ("Enzo", "2019-04-14", "🐯", prof1, ("Bruna Ferreira", "bruna@familia.com"), "Ampliar repertório de linguagem receptiva e expressiva."),
    ]

    responsavel_ids = {}

    for i, (nome, nasc, avatar, prof_id, (resp_nome, resp_email), objetivo) in enumerate(pacientes_data):
        cur = conn.execute(
            "INSERT INTO pacientes (organizacao_id, nome, data_nascimento, avatar_mascote) VALUES (?, ?, ?, ?)",
            (org_id, nome, nasc, avatar),
        )
        paciente_id = cur.lastrowid
        conn.execute("INSERT INTO gamificacao_paciente (paciente_id) VALUES (?)", (paciente_id,))

        if resp_email not in responsavel_ids:
            resp_id = usuario(conn, org_id, resp_nome, resp_email, "responsavel", avatar="👩", senha="familia123")
            responsavel_ids[resp_email] = resp_id
        conn.execute(
            "INSERT INTO responsaveis_pacientes (usuario_id, paciente_id, parentesco) VALUES (?, ?, 'Mãe/Pai')",
            (responsavel_ids[resp_email], paciente_id),
        )
        conn.execute(
            "INSERT INTO profissionais_pacientes (usuario_id, paciente_id, principal) VALUES (?, ?, 1)",
            (prof_id, paciente_id),
        )

        cur = conn.execute(
            "INSERT INTO jornadas (paciente_id, objetivo_principal, criado_em) VALUES (?, ?, ?)",
            (paciente_id, objetivo, (hoje - timedelta(days=60)).isoformat(sep=" ")),
        )
        jornada_id = cur.lastrowid

        cur = conn.execute(
            """INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio, status)
               VALUES (?, ?, ?, ?, 'ativo')""",
            (jornada_id, prof_id, f"Plano {hoje.strftime('%B/%Y')}", (hoje - timedelta(days=7)).strftime("%Y-%m-%d")),
        )
        plano_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO objetivos_terapeuticos (plano_id, descricao) VALUES (?, ?)",
            (plano_id, objetivo),
        )
        objetivo_id = cur.lastrowid

        # 5 missões da semana, com estados variados para alimentar os KPIs (Doc 11)
        titulos_exercicios = list(exercicio_ids.keys())
        estados = ["concluida", "concluida", "concluida", "pendente", "pendente"]
        if i in (2, 4):  # dois pacientes com atraso -> "precisa de atenção" no dashboard do profissional
            estados = ["concluida", "pendente", "pendente", "pendente", "pendente"]
        if i == 5:
            estados = ["pendente"] * 5  # baixa adesão

        # A missão concluída MAIS RECENTE de cada paciente fica de propósito sem
        # feedback ainda — assim dá pra ver e testar o botão "Como foi essa
        # atividade?" na tela do responsável sem precisar criar nada manualmente.
        indices_concluidos = [j for j, s in enumerate(estados) if s == "concluida"]
        indice_sem_feedback = max(indices_concluidos) if indices_concluidos else None

        for j, status in enumerate(estados):
            ex_titulo = titulos_exercicios[(i + j) % len(titulos_exercicios)]
            prazo = (hoje - timedelta(days=3) + timedelta(days=j)).strftime("%Y-%m-%d")
            concluida_em = (hoje - timedelta(days=5 - j)).isoformat(sep=" ") if status == "concluida" else None
            cur = conn.execute(
                """INSERT INTO missoes (plano_id, objetivo_id, titulo, descricao, prazo, status, recompensa_xp,
                                         tempo_estimado_min, concluida_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (plano_id, objetivo_id, f"Praticar: {ex_titulo}", f"Realizar a atividade '{ex_titulo}' com a criança.",
                 prazo, status, 15, 10, concluida_em),
            )
            missao_id = cur.lastrowid
            conn.execute(
                "INSERT INTO atividades (missao_id, exercicio_id, ordem, concluida) VALUES (?, ?, 1, ?)",
                (missao_id, exercicio_ids[ex_titulo], 1 if status == "concluida" else 0),
            )
            if status == "concluida":
                conn.execute(
                    "INSERT INTO eventos (organizacao_id, tipo, entidade, entidade_id, paciente_id, criado_em) "
                    "VALUES (?, 'missao_concluida', 'missao', ?, ?, ?)",
                    (org_id, missao_id, paciente_id, concluida_em),
                )
                if j != indice_sem_feedback:
                    conn.execute(
                        "INSERT INTO feedbacks_familia (missao_id, usuario_id, texto, humor, criado_em) VALUES (?, ?, ?, ?, ?)",
                        (missao_id, responsavel_ids[resp_email], "Ele adorou fazer essa atividade hoje!", "😄", concluida_em),
                    )

        # Gamificação acumulada
        concluidas_count = estados.count("concluida")
        xp = concluidas_count * 15 + (i * 5)
        conn.execute(
            """UPDATE gamificacao_paciente SET xp_total=?, nivel=?, estrelas=?, sequencia_dias=?,
               ultima_atividade_em=?, mascote_estagio=? WHERE paciente_id=?""",
            (xp, 1 + xp // 100, concluidas_count, min(concluidas_count, 4), hoje.isoformat(sep=" "),
             min(3, 1 + (1 + xp // 100) // 3), paciente_id),
        )
        if concluidas_count >= 1:
            medalha = conn.execute("SELECT id FROM medalhas WHERE nome='Primeira Missão'").fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO medalhas_paciente (paciente_id, medalha_id) VALUES (?, ?)",
                (paciente_id, medalha["id"]),
            )

        # ------------------------------------------------------------- MÓDULO 07 — Diário Terapêutico
        # Dois registros por paciente, para a linha do tempo/histórico terem conteúdo real.
        diarios_exemplo = DIARIOS_POR_PACIENTE.get(nome, DIARIOS_PADRAO(nome))
        for j, dex in enumerate(diarios_exemplo):
            data_atend = (hoje - timedelta(days=10 - j * 7)).strftime("%Y-%m-%d")
            diario_id = conn.execute(
                """INSERT INTO diarios_terapeuticos
                   (jornada_id, profissional_id, data_atendimento, evolucao_clinica,
                    pontos_positivos_json, pontos_atencao_json, objetivo_semana, mensagem_familia,
                    compartilhado_familia, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (jornada_id, prof_id, data_atend, dex["evolucao"],
                 json.dumps(dex["positivos"], ensure_ascii=False), json.dumps(dex["atencao"], ensure_ascii=False),
                 dex["objetivo"], dex["mensagem"], (hoje - timedelta(days=10 - j * 7)).isoformat(sep=" ")),
            ).lastrowid
            # Notificação correspondente para o(s) responsável(is), replicando o fluxo real
            conn.execute(
                "INSERT INTO notificacoes (usuario_id, titulo, mensagem, tipo, lida, criado_em) VALUES (?, ?, ?, 'diario', ?, ?)",
                (responsavel_ids[resp_email], f"Novo registro no diário de {nome} 📔", dex["mensagem"][:120],
                 0 if j == len(diarios_exemplo) - 1 else 1, (hoje - timedelta(days=10 - j * 7)).isoformat(sep=" ")),
            )

        # Marco de exemplo
        if i in (0, 3):
            conn.execute(
                "INSERT INTO marcos_terapeuticos (jornada_id, titulo, descricao, criado_em) VALUES (?, ?, ?, ?)",
                (jornada_id, "Primeira semana completa", "Concluiu todas as missões da primeira semana de tratamento.",
                 (hoje - timedelta(days=45)).isoformat(sep=" ")),
            )

        # Consultas (passadas e futuras)
        conn.execute(
            """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status, observacoes)
               VALUES (?, ?, ?, 'realizada', 'Sessão regular, boa participação.')""",
            (paciente_id, prof_id, (hoje - timedelta(days=7)).strftime("%Y-%m-%d 15:00:00")),
        )
        conn.execute(
            """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status)
               VALUES (?, ?, ?, 'agendada')""",
            (paciente_id, prof_id, (hoje + timedelta(days=2)).strftime("%Y-%m-%d 15:00:00")),
        )

        # Conversa + mensagens
        cur = conn.execute("INSERT INTO conversas (paciente_id) VALUES (?)", (paciente_id,))
        conversa_id = cur.lastrowid
        conn.execute(
            "INSERT INTO mensagens (conversa_id, autor_id, tipo, conteudo, criado_em) VALUES (?, ?, 'texto', ?, ?)",
            (conversa_id, prof_id, f"Olá! {nome} está indo muito bem essa semana. Continue reforçando as atividades em casa 💛",
             (hoje - timedelta(days=1)).isoformat(sep=" ")),
        )
        conn.execute(
            "INSERT INTO mensagens (conversa_id, autor_id, tipo, conteudo, criado_em) VALUES (?, ?, 'texto', ?, ?)",
            (conversa_id, responsavel_ids[resp_email], "Muito obrigada! Ele está adorando as missões 😊",
             (hoje - timedelta(hours=20)).isoformat(sep=" ")),
        )

        # Financeiro
        conn.execute(
            "INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status) VALUES (?, ?, ?, ?, 'pago')",
            (paciente_id, "Mensalidade - mês anterior", 35000, (hoje - timedelta(days=25)).strftime("%Y-%m-%d")),
        )
        status_atual = "pendente" if i % 3 != 0 else "vencido"
        cur = conn.execute(
            "INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status) VALUES (?, ?, ?, ?, ?)",
            (paciente_id, "Mensalidade - mês atual", 35000,
             (hoje + timedelta(days=5)).strftime("%Y-%m-%d") if status_atual == "pendente" else (hoje - timedelta(days=3)).strftime("%Y-%m-%d"),
             status_atual),
        )
        if i % 3 == 0 and status_atual != "vencido":
            conn.execute(
                "INSERT INTO pagamentos (cobranca_id, valor_centavos, forma) VALUES (?, 35000, 'pix')",
                (cur.lastrowid,),
            )

    conn.commit()

    # ------------------------------------------------------------- Atividade de HOJE
    # Garante que o Dashboard do Gestor (Documento 11) tenha números "vivos" hoje:
    # crianças ativas, consultas, pagamentos — replicando o exemplo do documento.
    todos_pacientes = conn.execute("SELECT id, organizacao_id FROM pacientes WHERE organizacao_id = ?", (org_id,)).fetchall()
    for idx, p in enumerate(todos_pacientes[:5]):
        conn.execute(
            "INSERT INTO eventos (organizacao_id, tipo, entidade, entidade_id, paciente_id, criado_em) "
            "VALUES (?, 'missao_concluida', 'missao', NULL, ?, ?)",
            (org_id, p["id"], hoje.isoformat(sep=" ")),
        )
    for idx, p in enumerate(todos_pacientes[:3]):
        conn.execute(
            """INSERT INTO consultas (paciente_id, profissional_id, data_hora, status)
               VALUES (?, ?, ?, 'confirmada')""",
            (p["id"], prof1, hoje.strftime("%Y-%m-%d") + f" {9+idx}:00:00"),
        )
    for idx, p in enumerate(todos_pacientes[:2]):
        cur = conn.execute(
            "INSERT INTO cobrancas (paciente_id, descricao, valor_centavos, vencimento, status) VALUES (?, ?, ?, ?, 'pago')",
            (p["id"], "Pacote de sessões", 42000, hoje.strftime("%Y-%m-%d")),
        )
        conn.execute(
            "INSERT INTO pagamentos (cobranca_id, valor_centavos, forma, pago_em) VALUES (?, 42000, 'pix', ?)",
            (cur.lastrowid, hoje.isoformat(sep=" ")),
        )
    conn.commit()

    # ------------------------------------------------------------- Avisos (mural)
    conn.execute(
        "INSERT INTO avisos (organizacao_id, autor_id, titulo, conteudo, criado_em) VALUES (?, ?, ?, ?, ?)",
        (org_id, gestor_id, "Horário especial de feriado",
         "Na próxima segunda-feira (feriado) a clínica funcionará em horário reduzido, das 9h às 13h.",
         (hoje - timedelta(days=2)).isoformat(sep=" ")),
    )
    conn.execute(
        "INSERT INTO avisos (organizacao_id, autor_id, titulo, conteudo, criado_em) VALUES (?, ?, ?, ?, ?)",
        (org_id, gestor_id, "Nova sala sensorial",
         "Inauguramos essa semana nossa nova sala de integração sensorial! Peça mais informações à equipe.",
         (hoje - timedelta(days=6)).isoformat(sep=" ")),
    )
    conn.commit()

    # ------------------------------------------------------------- Outras clínicas (para o painel comercial do Admin do SaaS)
    outras_clinicas = [
        # nome, cores, emoji, plano, status_comercial, dias_desde_inicio_trial/assinatura, contato, origem, observação
        ("Instituto Crescer Feliz", "#2E9E6B", "#FFD166", "🌈", "pro", "trial", 11,
         "Beatriz Souza", "beatriz@crescerfeliz.com.br", "(21) 98765-4321", "inbound",
         "Testando o módulo de gamificação com a equipe de TO. Trial termina em breve — priorizar follow-up."),
        ("Espaço Terapêutico Girassol", "#E8A93C", "#FFF3DE", "🌻", "starter", "ativa", 40,
         "Rodrigo Nunes", "rodrigo@girassol.com.br", "(11) 91234-5678", "evento",
         "Fechou no plano Starter após a feira de terapias em março. Perto do limite de pacientes — oportunidade de upsell para o Pro."),
        ("Clínica Passo a Passo", "#8B5FBF", "#F3EEFF", "👣", "starter", "inadimplente", 60,
         "Fernanda Reis", "fernanda@passoapasso.com.br", "(41) 99999-1122", "outbound",
         "Pagamento do mês em atraso há 12 dias. Time comercial já entrou em contato 2x, aguardando retorno."),
        ("Terapias Pequeno Príncipe", "#E85D75", "#FCE7E3", "👑", "pro", "cancelada", 120,
         "Camila Duarte", "camila@pequenoprincipe.com.br", "(51) 98888-3344", "indicação",
         "Cancelou após 3 meses — motivo declarado: equipe pequena, achou o Pro caro para o uso real. Candidata a win-back no Starter."),
    ]
    for idx, (nome, cor1, cor2, emoji, plano, status, dias, contato_nome, contato_email, contato_tel, origem, obs) in enumerate(outras_clinicas):
        campo_data = "assinatura_inicio" if status in ("ativa", "inadimplente", "cancelada") else "data_inicio_trial"
        cur = conn.execute(
            f"""INSERT INTO organizacoes (nome, cor_primaria, cor_secundaria, logo_emoji, plano, status_comercial,
                                          {campo_data}, contato_nome, contato_email, contato_telefone, origem_lead,
                                          observacoes_comerciais, ativo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nome, cor1, cor2, emoji, plano, status, (hoje - timedelta(days=dias)).strftime("%Y-%m-%d"),
             contato_nome, contato_email, contato_tel, origem, obs, 0 if status == "cancelada" else 1),
        )
        org_x_id = cur.lastrowid
        avatar_gestor = ["👩‍💼", "👨‍💼", "👩‍💼", "👩‍💼"][idx % 4]
        usuario(conn, org_x_id, contato_nome, contato_email, "gestor", avatar=avatar_gestor, senha="gestor123")

        # Girassol (starter, limite 8 pacientes) recebe 7 pacientes simples só para
        # o indicador de uso do plano (%) fazer sentido no painel comercial.
        if nome == "Espaço Terapêutico Girassol":
            for k in range(7):
                conn.execute(
                    "INSERT INTO pacientes (organizacao_id, nome, data_nascimento, avatar_mascote) VALUES (?, ?, ?, ?)",
                    (org_x_id, f"Paciente Demo {k+1}", "2019-01-01", "🧒"),
                )
    conn.commit()

    conn.close()

    print("✅ Seed concluído com sucesso!\n")
    print("=" * 60)
    print("CREDENCIAIS DE DEMONSTRAÇÃO")
    print("=" * 60)
    print(f"Admin do SaaS ......... admin@encantoemcasa.com / admin123")
    print(f"Gestor (Clínica) ...... andre@clinicaencantar.com.br / gestor123")
    print(f"Profissional (Fono) ... camila@clinicaencantar.com.br / prof123")
    print(f"Profissional (TO) ..... rafael@clinicaencantar.com.br / prof123")
    print(f"Profissional (Psicop) . juliana@clinicaencantar.com.br / prof123")
    print(f"Responsável ............ ana@familia.com / familia123")
    print(f"  (demais responsáveis usam a senha: familia123)")
    print("=" * 60)


if __name__ == "__main__":
    main()
