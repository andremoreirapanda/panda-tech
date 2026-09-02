"""
Feature Flags — Módulos opcionais habilitáveis (Documento 22A).

Implementa 3 das 5 camadas descritas no documento (Plataforma e Feature Flag
globais não fazem sentido numa instância única de clínica-SaaS pequena;
ver GAP_ANALYSIS.md para a justificativa):

  Plano contratado → Clínica (gestor decide) → Usuário (override pontual)

Módulos OBRIGATÓRIOS (sempre ativos, não aparecem aqui):
  jornada, biblioteca, comunicacao, diario_terapeutico, gamificacao, agenda

Módulos OPCIONAIS (controlados por este serviço):
  financeiro, ia, analytics_avancado, integracoes, white_label
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
]

# Camada "Plano": quais módulos opcionais cada plano contratado libera.
MODULOS_POR_PLANO = {
    "starter": [],
    "pro": ["financeiro", "ia", "analytics_avancado", "integracoes", "importacao_pacientes"],
    "enterprise": ["financeiro", "ia", "analytics_avancado", "integracoes", "white_label", "importacao_pacientes"],
}


def modulos_do_plano(codigo_plano):
    return MODULOS_POR_PLANO.get(codigo_plano, [])


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
    linhas = query("SELECT modulo_codigo, habilitado FROM modulos_clinica WHERE organizacao_id = ?", (organizacao_id,))
    habilitados = {l["modulo_codigo"] for l in linhas if l["habilitado"] and l["modulo_codigo"] in liberados_plano}
    return habilitados


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
