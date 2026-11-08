"""
Cron opcional do cPanel — sincroniza a agenda com as cobranças das famílias
(financeiro da clínica, 07/11/2026) em todas as clínicas ativas com o módulo
Financeiro. A mesma sincronização roda sozinha ao abrir as telas do
financeiro, então este script só adianta o trabalho (ex.: marcar vencidas e
criar as mensalidades no 1º dia do mês). Rodar de novo é seguro.

Como agendar no cPanel (uma vez por dia, 05:00):
  source /home/<usuario>/virtualenv/panda-tech/3.11/bin/activate && \
  cd /home/<usuario>/panda-tech/backend && \
  python3 gerar_cobrancas_clinicas.py >> cron_cobrancas_clinicas.log 2>&1

Atenção (CLAUDE.md 7.2): o script não carrega o backend/.env. Sem
DATABASE_URL no ambiente ele grava no SQLite local — confira que a última
linha da saída é "(Postgres)".
"""
import os
from datetime import datetime, timezone

import db
import cobranca_service
from modulos_service import modulo_ativo_para_clinica


def main(hoje=None):
    hoje = hoje or os.environ.get("HOJE") or None
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{agora}] Sincronizando cobranças das famílias...")
    clinicas = db.query("""SELECT id, nome, plano FROM organizacoes
                           WHERE COALESCE(ativo, 1) = 1 AND COALESCE(status_comercial, '') != 'cancelada'
                           ORDER BY id""")
    for org in clinicas:
        if not modulo_ativo_para_clinica(org["id"], org["plano"], "financeiro"):
            continue
        try:
            r = cobranca_service.sincronizar(org["id"], hoje)
            print(f"  {org['nome']} (id={org['id']}): {r['criadas']} cobrança(s) criada(s), "
                  f"{r['itens']} sessão(ões), {r['revisar']} a revisar")
        except Exception as e:  # uma clínica com problema não para as outras
            print(f"  {org['nome']} (id={org['id']}): ERRO {type(e).__name__}: {e}")
    print("(Postgres)" if db.USANDO_POSTGRES else "(SQLite)")


if __name__ == "__main__":
    main()
