"""
Auditoria pontual (NÃO é uma migração) — detecta vínculos que atravessam
clínicas diferentes: dados que podem ter sido criados ANTES das correções de
segurança de 25/08/2026, quando alguns endpoints de agenda, pessoas e
jornada não validavam se um id vindo da requisição (profissional_id,
responsaveis_ids, profissionais_ids, exercicios_ids) pertencia de fato à
mesma clínica do paciente. Ver o documento de auditoria de segurança para o
detalhe de cada correção.

100% somente leitura — este script NÃO apaga, desvincula nem corrige nada
automaticamente. Ele só IMPRIME o que encontrar; cabe ao time da clínica
decidir o que fazer com cada linha reportada (ex: desvincular manualmente
pela tela do gestor, ou confirmar que o vínculo era intencional e legítimo
mesmo atravessando organizações — o que não deveria acontecer no modelo
atual, mas o script não presume nada, só relata).

Uso (rode uma vez em produção, depois do deploy das correções):
    cd backend
    source /caminho/do/virtualenv/bin/activate
    python3 auditar_vinculos_cross_clinica.py
"""
import db


def _linha(titulo, rows, campos):
    print(f"\n=== {titulo} ===")
    if not rows:
        print("Nenhum encontrado. ✅")
        return
    print(f"{len(rows)} encontrado(s):")
    for r in rows:
        print("  - " + " | ".join(f"{c}={r.get(c)}" for c in campos))


def checar():
    responsaveis_cross = db.query("""
        SELECT rp.usuario_id, rp.paciente_id, u.organizacao_id AS org_usuario,
               p.organizacao_id AS org_paciente, u.nome AS usuario_nome, p.nome AS paciente_nome
        FROM responsaveis_pacientes rp
        JOIN usuarios u ON u.id = rp.usuario_id
        JOIN pacientes p ON p.id = rp.paciente_id
        WHERE u.organizacao_id != p.organizacao_id
    """)
    _linha(
        "responsaveis_pacientes com organizacao_id divergente (família de uma clínica vinculada a paciente de outra)",
        responsaveis_cross, ["usuario_nome", "paciente_nome", "org_usuario", "org_paciente"],
    )

    profissionais_cross = db.query("""
        SELECT pp.usuario_id, pp.paciente_id, u.organizacao_id AS org_usuario,
               p.organizacao_id AS org_paciente, u.nome AS usuario_nome, p.nome AS paciente_nome
        FROM profissionais_pacientes pp
        JOIN usuarios u ON u.id = pp.usuario_id
        JOIN pacientes p ON p.id = pp.paciente_id
        WHERE u.organizacao_id != p.organizacao_id
    """)
    _linha(
        "profissionais_pacientes com organizacao_id divergente (profissional de uma clínica vinculado a paciente de outra)",
        profissionais_cross, ["usuario_nome", "paciente_nome", "org_usuario", "org_paciente"],
    )

    consultas_cross = db.query("""
        SELECT c.id AS consulta_id, c.paciente_id, c.profissional_id,
               prof.organizacao_id AS org_profissional, p.organizacao_id AS org_paciente,
               prof.nome AS profissional_nome, p.nome AS paciente_nome
        FROM consultas c
        JOIN usuarios prof ON prof.id = c.profissional_id
        JOIN pacientes p ON p.id = c.paciente_id
        WHERE prof.organizacao_id != p.organizacao_id
    """)
    _linha(
        "consultas com profissional de outra clínica (agenda cross-clínica)",
        consultas_cross, ["consulta_id", "profissional_nome", "paciente_nome", "org_profissional", "org_paciente"],
    )

    atividades_cross = db.query("""
        SELECT a.id AS atividade_id, a.missao_id, a.exercicio_id,
               e.organizacao_id AS org_exercicio, p.organizacao_id AS org_paciente,
               e.titulo AS exercicio_titulo, p.nome AS paciente_nome
        FROM atividades a
        JOIN missoes m ON m.id = a.missao_id
        JOIN planos_terapeuticos pt ON pt.id = m.plano_id
        JOIN jornadas j ON j.id = pt.jornada_id
        JOIN pacientes p ON p.id = j.paciente_id
        JOIN exercicios e ON e.id = a.exercicio_id
        WHERE e.organizacao_id IS NOT NULL AND e.organizacao_id != p.organizacao_id
    """)
    _linha(
        "atividades referenciando exercício privado de OUTRA clínica (exercícios públicos, organizacao_id NULL, não contam)",
        atividades_cross, ["atividade_id", "exercicio_titulo", "paciente_nome", "org_exercicio", "org_paciente"],
    )

    total = len(responsaveis_cross) + len(profissionais_cross) + len(consultas_cross) + len(atividades_cross)
    print(f"\n{'='*60}\nTotal de linhas suspeitas encontradas: {total}")
    if total:
        print("Revise cada uma manualmente — este script não corrige nada sozinho.")
    else:
        print("Nenhum vínculo cross-clínica encontrado nos dados atuais. ✅")


if __name__ == "__main__":
    checar()
