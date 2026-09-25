"""
Feature Flags — Módulos opcionais habilitáveis (Documento 22A).

Implementa 3 das 5 camadas descritas no documento (Plataforma e Feature Flag
globais não fazem sentido numa instância única de clínica-SaaS pequena;
ver GAP_ANALYSIS.md para a justificativa):

  Plano contratado → Clínica (gestor decide) → Usuário (override pontual)

Módulos OBRIGATÓRIOS (sempre ativos, não aparecem aqui):
  jornada, biblioteca, comunicacao, diario_terapeutico, gamificacao, agenda

Módulos OPCIONAIS (controlados por este serviço): lista em MODULOS_OPCIONAIS.

Planos configuráveis (25/09/2026): quais módulos cada plano libera NÃO fica
mais no código — está em `planos_modulos` (módulos marcados no próprio plano)
+ `planos.plano_base_id` (herança viva: o plano tem tudo o que a base tem).
O Admin muda isso pela tela; `planos_padrao.py` guarda só o ponto de partida.
Além do plano, o Admin pode liberar módulos avulsos para uma clínica
(`modulos_clinica.liberado_admin` — "extras").
"""
from db import query, query_one, execute

MODULOS_OPCIONAIS = [
    {"codigo": "financeiro", "nome": "Financeiro", "icone": "💳",
     "descricao": "Cobranças das famílias em um só lugar: mensalidades e cobranças avulsas, pagamento por PIX ou "
                  "cartão pelo Mercado Pago com baixa automática e acompanhamento de quem está em dia. A família vê e "
                  "paga pelo próprio app — a clínica cobra menos no manual e recebe mais em dia."},
    {"codigo": "analytics_avancado", "nome": "Indicadores Avançados", "icone": "📊",
     "descricao": "Índice de Continuidade Terapêutica, engajamento das famílias com as missões e métricas por "
                  "profissional e por paciente. Mostra cedo quem está deixando de fazer as atividades em casa e ajuda "
                  "a mostrar resultado para as famílias."},
    {"codigo": "integracoes", "nome": "Central de Integrações", "icone": "🔌",
     "descricao": "Conecta o Panda Tech ao WhatsApp (convites e lembretes automáticos para as famílias), ao Google "
                  "Agenda (consultas sincronizadas com a agenda da equipe) e ao Mercado Pago. Menos retrabalho e menos "
                  "faltas."},
    {"codigo": "white_label", "nome": "Identidade Visual Própria", "icone": "🎨",
     "descricao": "Deixa o app com a cara da clínica: cores, nomes do assistente, da moeda e da medalha, nome e "
                  "ícone do app no celular, tela de login própria com a marca e a mensagem da clínica, e um Mundo "
                  "da Criança personalizado (fonte, fundo animado, mascote e texto da comemoração)."},
    {"codigo": "importacao_pacientes", "nome": "Importação de Pacientes", "icone": "📥",
     "descricao": "Traz de uma vez, por planilha (Excel ou CSV), os pacientes e responsáveis que já estão em outro "
                  "sistema, conferindo cada linha antes de gravar. Começar a usar o Panda Tech leva minutos, não dias."},
    {"codigo": "pandoo", "nome": "Pandoo", "icone": "🎮",
     "descricao": "Criador de jogos educativos: o profissional monta jogos (começando pela roleta de figuras) com as "
                  "próprias imagens e a própria voz, coloca nas missões e acompanha o desempenho da criança figura por "
                  "figura. Mais engajamento em casa, com evolução medida."},
    # Escondido até existir de verdade (decisão do usuário, 25/09/2026): hoje
    # nenhuma tela depende dele. Volta a aparecer quando o assistente for feito.
    {"codigo": "ia", "nome": "Assistente de IA", "icone": "✨", "oculto": True,
     "descricao": "Assistente que ajudará a equipe a encontrar informações e navegar no sistema (em desenvolvimento)."},
]

# O que aparece em telas, planos e checagens de acesso (sem os escondidos).
MODULOS_VISIVEIS = [m for m in MODULOS_OPCIONAIS if not m.get("oculto")]

CODIGOS_OPCIONAIS = {m["codigo"] for m in MODULOS_VISIVEIS}
_PROFUNDIDADE_MAX = 10


def cadeia_de_bases(plano_id):
    """Ids das bases do plano, da mais próxima para cima. Para em ciclo (que a
    API já recusa, mas o banco pode ter se alguém mexer à mão) ou em 10 níveis."""
    vistos, atual, cadeia = {plano_id}, plano_id, []
    for _ in range(_PROFUNDIDADE_MAX):
        linha = query_one("SELECT plano_base_id FROM planos WHERE id = ?", (atual,))
        base = linha.get("plano_base_id") if linha else None
        if not base or base in vistos:
            break
        cadeia.append(base)
        vistos.add(base)
        atual = base
    return cadeia


def modulos_proprios_do_plano(plano_id):
    return sorted(l["modulo_codigo"] for l in query(
        "SELECT modulo_codigo FROM planos_modulos WHERE plano_id = ?", (plano_id,)))


def modulos_do_plano(codigo_plano):
    """Módulos do plano + os herdados da cadeia de bases (camada "Plano")."""
    plano = query_one("SELECT id FROM planos WHERE codigo = ?", (codigo_plano,))
    if not plano:
        return []
    modulos = set()
    for pid in [plano["id"]] + cadeia_de_bases(plano["id"]):
        modulos.update(modulos_proprios_do_plano(pid))
    return sorted(m for m in modulos if m in CODIGOS_OPCIONAIS)


def modulos_extras_clinica(organizacao_id):
    """Módulos liberados pelo Admin para esta clínica, fora do plano."""
    return {l["modulo_codigo"] for l in query(
        "SELECT modulo_codigo FROM modulos_clinica WHERE organizacao_id = ? AND liberado_admin = 1 AND habilitado = 1",
        (organizacao_id,)) if l["modulo_codigo"] in CODIGOS_OPCIONAIS}


def _garantir_linhas_clinica(organizacao_id, codigo_plano):
    """Cria a linha de módulo (habilitado=1 por padrão) para cada módulo liberado pelo plano."""
    liberados = modulos_do_plano(codigo_plano)
    existentes = {m["modulo_codigo"] for m in query(
        "SELECT modulo_codigo FROM modulos_clinica WHERE organizacao_id = ?", (organizacao_id,)
    )}
    for codigo in liberados:
        if codigo not in existentes:
            execute(
                "INSERT INTO modulos_clinica (organizacao_id, modulo_codigo, habilitado) VALUES (?, ?, 1)",
                (organizacao_id, codigo),
            )


def modulos_habilitados_clinica(organizacao_id, codigo_plano):
    """
    Retorna o conjunto de módulos opcionais efetivamente habilitados para a
    clínica, já cruzando Plano × Clínica (camadas 1 e 2).
    """
    _garantir_linhas_clinica(organizacao_id, codigo_plano)
    liberados_plano = set(modulos_do_plano(codigo_plano))
    linhas = query("SELECT modulo_codigo, habilitado, liberado_admin FROM modulos_clinica WHERE organizacao_id = ?", (organizacao_id,))
    habilitados = {l["modulo_codigo"] for l in linhas if l["habilitado"] and l["modulo_codigo"] in liberados_plano}
    return habilitados | modulos_extras_clinica(organizacao_id)


def definir_liberacao_admin(organizacao_id, codigo, liberado):
    """Liga/desliga um módulo extra (fora do plano) numa clínica — linha criada se faltar."""
    if codigo not in CODIGOS_OPCIONAIS:
        raise ValueError("Módulo desconhecido.")
    # A mesma linha de modulos_clinica também guarda o liga/desliga do gestor
    # para módulos do plano: ao tirar o extra, `habilitado` volta a 1 para que,
    # se o módulo vier a fazer parte do plano, ele já nasça ligado (revisão final).
    valor = 1 if liberado else 0
    linha = query_one("SELECT id FROM modulos_clinica WHERE organizacao_id = ? AND modulo_codigo = ?",
                      (organizacao_id, codigo))
    if linha:
        execute("UPDATE modulos_clinica SET liberado_admin = ?, habilitado = 1 WHERE id = ?", (valor, linha["id"]))
    else:
        execute("INSERT INTO modulos_clinica (organizacao_id, modulo_codigo, habilitado, liberado_admin) VALUES (?, ?, 1, ?)",
                (organizacao_id, codigo, valor))


def limpar_extras_cobertos_pelo_plano(organizacao_id, codigo_plano):
    """Quando a clínica muda para um plano que já inclui um módulo que era
    extra, o extra deixa de existir (senão ele "voltaria" sozinho se a
    clínica mudasse de novo para um plano sem o módulo)."""
    for codigo in modulos_do_plano(codigo_plano):
        execute("UPDATE modulos_clinica SET liberado_admin = 0 WHERE organizacao_id = ? AND modulo_codigo = ?",
                (organizacao_id, codigo))


def modulo_ativo_para_clinica(organizacao_id, codigo_plano, modulo_codigo):
    return modulo_codigo in modulos_habilitados_clinica(organizacao_id, codigo_plano)


def financeiro_visivel_para_usuario(usuario):
    """
    Camada 'Usuário' (Doc 22A): o gestor pode sobrescrever a visibilidade do
    Financeiro para um responsável específico, mesmo que a clínica o tenha
    habilitado no geral.
    """
    org = query_one("SELECT plano FROM organizacoes WHERE id = ?", (usuario["organizacao_id"],))
    if not org:
        return False
    habilitado_clinica = modulo_ativo_para_clinica(usuario["organizacao_id"], org["plano"], "financeiro")
    override = usuario.get("financeiro_habilitado_override")
    if override is None:
        return habilitado_clinica
    return bool(override) and habilitado_clinica  # override nunca liga o que a clínica desligou
