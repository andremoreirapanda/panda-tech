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
     "descricao": "Cobranças e pagamentos visíveis para a clínica e as famílias."},
    {"codigo": "ia", "nome": "Assistente de IA", "icone": "✨",
     "descricao": "Assistente contextual para ajudar a navegar e encontrar informações."},
    {"codigo": "analytics_avancado", "nome": "Indicadores Avançados", "icone": "📊",
     "descricao": "Índice de Continuidade Terapêutica, funil de engajamento e métricas aprofundadas."},
    {"codigo": "integracoes", "nome": "Central de Integrações", "icone": "🔌",
     "descricao": "Conectar WhatsApp, Google Agenda, ERP e gateway de pagamento."},
    {"codigo": "white_label", "nome": "Identidade Visual Própria", "icone": "🎨",
     "descricao": "Personalizar cores, nome do assistente de IA e nome da gamificação."},
    {"codigo": "importacao_pacientes", "nome": "Importação de Pacientes", "icone": "📥",
     "descricao": "Trazer de uma vez, por planilha, os pacientes já cadastrados em outro sistema — "
                   "em vez de cadastrar um por um."},
    {"codigo": "pandoo", "nome": "Pandoo", "icone": "🎮",
     "descricao": "Jogos educativos criados pela clínica (roleta e outros), usados nas missões."},
]

CODIGOS_OPCIONAIS = {m["codigo"] for m in MODULOS_OPCIONAIS}
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
    valor = 1 if liberado else 0
    linha = query_one("SELECT id FROM modulos_clinica WHERE organizacao_id = ? AND modulo_codigo = ?",
                      (organizacao_id, codigo))
    if linha:
        execute("UPDATE modulos_clinica SET liberado_admin = ?, habilitado = ? WHERE id = ?", (valor, valor, linha["id"]))
    else:
        execute("INSERT INTO modulos_clinica (organizacao_id, modulo_codigo, habilitado, liberado_admin) VALUES (?, ?, ?, ?)",
                (organizacao_id, codigo, valor, valor))


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
