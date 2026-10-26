// ============================================================================
// importacao_util.js — funções puras da importação do prontuário (26/10/2026):
// colunas das duas planilhas, colunas de data (série do Excel vira AAAA-MM-DD)
// e a divisão das evoluções em envios de até 1.000 linhas, juntando as prévias.
// Testes: frontend/tests/importacao_util.test.js
// ============================================================================

// Ficha Clínica: colunas opcionais no fim da planilha de pacientes.
const CAMPOS_FICHA_CSV = ["diagnostico", "alergias", "medicamentos_em_uso", "profissionais_externos", "observacoes_clinicas"];

const CAMPOS_EVOLUCOES_CSV = [
    "paciente_nome", "paciente_nascimento", "data_atendimento", "profissional_email",
    "profissional_nome", "evolucao", "observacao",
];

const MAX_EVOLUCOES_POR_ENVIO = 1000;

const _COLUNAS_DE_DATA = {
    pacientes: ["data_nascimento"],
    evolucoes: ["paciente_nascimento", "data_atendimento"],
};

function colunasDeData(aba) {
    return (_COLUNAS_DE_DATA[aba] || []).slice();
}

function ehColunaDeData(coluna) {
    return Object.values(_COLUNAS_DE_DATA).some(lista => lista.includes(coluna));
}

function dividirEmEnvios(linhas, tamanho = MAX_EVOLUCOES_POR_ENVIO) {
    const envios = [];
    for (let i = 0; i < (linhas || []).length; i += tamanho) envios.push(linhas.slice(i, i + tamanho));
    return envios;
}

// Uma prévia por envio → uma só, com os contadores somados e o número da
// linha contado desde o começo do arquivo (cada envio recomeça do 0).
function juntarPrevias(previas, tamanho = MAX_EVOLUCOES_POR_ENVIO) {
    const junta = { linhas: [], total: 0, prontas: 0, avisos: 0, erros: 0, ja_importadas: 0 };
    (previas || []).forEach((p, i) => {
        p.linhas.forEach(l => junta.linhas.push({ ...l, linha: l.linha + i * tamanho }));
        ["total", "prontas", "avisos", "erros", "ja_importadas"].forEach(k => { junta[k] += p[k] || 0; });
    });
    return junta;
}

// Selo do registro do Diário que veio da planilha de evoluções (só a equipe vê).
function seloDiarioImportado() {
    return `<span class="badge badge-neutro texto-xs">Importado</span> <span class="texto-xs texto-suave">🔒 Só a equipe vê</span>`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        CAMPOS_FICHA_CSV, CAMPOS_EVOLUCOES_CSV, MAX_EVOLUCOES_POR_ENVIO,
        colunasDeData, ehColunaDeData, dividirEmEnvios, juntarPrevias, seloDiarioImportado,
    };
}
