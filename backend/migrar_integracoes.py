"""
Migração não-destrutiva para quem já tem um `encanto.db` com dados reais e
não quer rodar `seed.py` de novo (que recria o banco do zero).

Adiciona as colunas novas usadas pelas integrações reais (Google Agenda,
Mercado Pago) em bancos já existentes. Rodar uma vez, depois de atualizar o
código:

    python3 migrar_integracoes.py

É seguro rodar mais de uma vez — colunas que já existem são ignoradas.
"""
import sqlite3

from db import DB_PATH

COLUNAS_NOVAS = [
    ("cobrancas", "mp_payment_id", "TEXT"),
    ("cobrancas", "pix_qr_code", "TEXT"),
    ("cobrancas", "pix_qr_code_base64", "TEXT"),
    ("cobrancas", "pix_copia_cola", "TEXT"),
    ("organizacoes", "agenda_permissao_total_padrao", "INTEGER DEFAULT 0"),
]


def migrar():
    conn = sqlite3.connect(DB_PATH)
    aplicadas = 0
    for tabela, coluna, tipo in COLUNAS_NOVAS:
        try:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
            conn.commit()
            aplicadas += 1
            print(f"✅ {tabela}.{coluna} adicionada")
        except sqlite3.OperationalError as exc:
            if "duplicate column" in str(exc).lower():
                print(f"↷  {tabela}.{coluna} já existia, pulei")
            else:
                raise
    conn.close()
    print(f"\nMigração concluída — {aplicadas} coluna(s) nova(s) aplicada(s).")
    print(
        "\n⚠️  Nota: o SQLite não permite alterar uma restrição CHECK já existente via"
        "\n   ALTER TABLE. Se você tinha um banco de antes desta rodada, a tabela"
        "\n   `pagamentos` ainda vai recusar forma='dinheiro'/'transferencia' até você"
        "\n   rodar `python3 seed.py` de novo (recria o banco do zero) ou recriar a"
        "\n   tabela manualmente. Bancos criados a partir de agora já nascem certos."
    )


if __name__ == "__main__":
    migrar()
