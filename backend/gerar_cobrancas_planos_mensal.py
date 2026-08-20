"""
Script para o Cron Jobs do cPanel — gera as cobranças mensais das clínicas
pelo plano (Panda Tech cobrando a assinatura), a mesma lógica usada pelo
botão "Gerar cobranças agora" em Admin > Cobranças.

Não precisa de contexto Flask: db.py já sabe rodar em modo "standalone"
fora de uma app Flask (mesmo padrão de seed.py / migrar_integracoes.py),
então este script funciona tanto com SQLite local quanto com o Postgres de
produção (via DATABASE_URL).

Respeita o interruptor "Cobrança automática" de Admin > Integrações — se
estiver desligado, roda e não faz nada (fica só o log dizendo que pulou).

Como agendar no cPanel:
  1. cPanel > Cron Jobs > Add New Cron Job.
  2. Frequência sugerida: uma vez por mês, dia 1 às 06:00 —
     Minuto=0, Hora=6, Dia=1, Mês=*, Dia da semana=*.
  3. Comando (ajuste o caminho pro seu usuário/domínio):
     source /home/mimosart/virtualenv/panda-tech/3.11/bin/activate && \
     cd /home/mimosart/panda-tech/backend && \
     python3 gerar_cobrancas_planos_mensal.py >> /home/mimosart/panda-tech/backend/cron_cobrancas.log 2>&1

Rodar mais de uma vez no mesmo mês é seguro — cada clínica só recebe uma
cobrança por mês corrente (ver `_ja_gerada_no_mes` em
pagamento_plataforma_service.py).
"""
from datetime import datetime, timezone

import pagamento_plataforma_service


def main():
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{agora}] Iniciando geração de cobranças mensais de plano...")
    resultado = pagamento_plataforma_service.gerar_cobrancas_mensais()

    if not resultado["executado"]:
        print(f"  Pulado: {resultado['motivo']}")
        return

    print(f"  {resultado['geradas']} cobrança(s) gerada(s), {resultado['puladas']} clínica(s) pulada(s) (já cobradas este mês ou sem plano pago).")
    if resultado["erros"]:
        print(f"  {len(resultado['erros'])} erro(s) ao gerar o PIX (a cobrança foi criada mesmo assim — gere o PIX depois pelo Admin):")
        for erro in resultado["erros"]:
            print(f"    - {erro['organizacao_nome']} (id={erro['organizacao_id']}): {erro['erro']}")
    print("Concluído.")


if __name__ == "__main__":
    main()
