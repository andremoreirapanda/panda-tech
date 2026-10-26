"""
Importação do prontuário (26/10/2026): funções puras usadas pelas rotas de
importação (blueprints/importacao_bp.py) e a checagem das colunas novas do
Diário (`origem`, `importacao_chave`) e da ficha (`observacoes_equipe`), para
o deploy antes da migração não derrubar nada.

Spec: docs/superpowers/specs/2026-10-26-importacao-prontuario-design.md
"""
import hashlib
import re
import unicodedata
from datetime import date

from db import get_db, query_one

_colunas_ok = [False]  # depois de achar as colunas uma vez, não pergunta de novo
_obs_equipe_ok = [False]


def _colunas_existem(cache, sql):
    if cache[0]:
        return True
    try:
        query_one(sql)
    except Exception:
        try:
            get_db().rollback()  # no Postgres a transação fica abortada depois do erro
        except Exception:
            pass
        return False
    cache[0] = True
    return True


def colunas_diario_importacao_existem():
    """True se `diarios_terapeuticos` já tem `origem` e `importacao_chave`."""
    return _colunas_existem(_colunas_ok, "SELECT origem, importacao_chave FROM diarios_terapeuticos LIMIT 1")


def coluna_observacoes_equipe_existe():
    """True se `fichas_clinicas` já tem `observacoes_equipe` (só a equipe vê)."""
    return _colunas_existem(_obs_equipe_ok, "SELECT observacoes_equipe FROM fichas_clinicas LIMIT 1")


def normalizar_nome(texto):
    """Sem acento, minúsculas e espaços colapsados — para casar o mesmo
    paciente escrito de jeitos diferentes nos dois sistemas."""
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFKD", str(texto or "")) if not unicodedata.combining(ch)
    )
    return " ".join(sem_acento.lower().split())


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def converter_data(texto):
    """'AAAA-MM-DD' ou 'DD/MM/AAAA' → 'AAAA-MM-DD' (data que existe), senão None."""
    texto = str(texto or "").strip()
    m = _ISO.match(texto)
    if m:
        ano, mes, dia = m.groups()
    else:
        m = _BR.match(texto)
        if not m:
            return None
        dia, mes, ano = m.groups()
    try:
        return date(int(ano), int(mes), int(dia)).isoformat()
    except ValueError:
        return None


def chave_importacao(paciente_id, data_iso, texto_original):
    """Impressão da evolução importada: mesmo paciente + data + texto da
    planilha = mesma chave, mesmo que o registro seja editado depois."""
    base = f"{paciente_id}|{data_iso}|{str(texto_original or '').strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
