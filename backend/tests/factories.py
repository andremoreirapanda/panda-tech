"""
Helpers de criação de dados de teste — usados por todos os módulos de teste
para montar cenários com duas clínicas (org A e org B) sem repetir os
mesmos INSERTs em cada arquivo.

Precisam ser chamados dentro do fixture `db_ctx` (contexto de app ativo).
"""
import auth
import db


def nova_organizacao(nome="Clínica de Teste", plano="premium"):
    return db.execute("INSERT INTO organizacoes (nome, plano) VALUES (?, ?)", (nome, plano))


def novo_usuario(org_id, nome, email, papel, **extra):
    senha_hash, salt = auth.hash_senha("senhateste123")
    campos = ["organizacao_id", "nome", "email", "senha_hash", "senha_salt", "papel"]
    valores = [org_id, nome, email, senha_hash, salt, papel]
    for k, v in extra.items():
        campos.append(k)
        valores.append(v)
    placeholders = ", ".join("?" for _ in campos)
    uid = db.execute(f"INSERT INTO usuarios ({', '.join(campos)}) VALUES ({placeholders})", tuple(valores))
    return db.query_one("SELECT * FROM usuarios WHERE id = ?", (uid,))


def novo_paciente(org_id, nome="Paciente de Teste", nascimento="2018-01-01"):
    return db.execute(
        "INSERT INTO pacientes (organizacao_id, nome, data_nascimento) VALUES (?, ?, ?)",
        (org_id, nome, nascimento),
    )


def vincular_profissional(profissional_id, paciente_id, principal=1):
    db.execute(
        "INSERT INTO profissionais_pacientes (usuario_id, paciente_id, principal) VALUES (?, ?, ?)",
        (profissional_id, paciente_id, principal),
    )


def vincular_responsavel(responsavel_id, paciente_id, parentesco="Responsável"):
    db.execute(
        "INSERT INTO responsaveis_pacientes (usuario_id, paciente_id, parentesco) VALUES (?, ?, ?)",
        (responsavel_id, paciente_id, parentesco),
    )


def novo_exercicio(org_id, titulo="Exercício de Teste", **extra):
    """org_id=None cria na Biblioteca da Plataforma (visível a todas as clínicas)."""
    campos = ["organizacao_id", "titulo"]
    valores = [org_id, titulo]
    for k, v in extra.items():
        campos.append(k)
        valores.append(v)
    placeholders = ", ".join("?" for _ in campos)
    eid = db.execute(f"INSERT INTO exercicios ({', '.join(campos)}) VALUES ({placeholders})", tuple(valores))
    return db.query_one("SELECT * FROM exercicios WHERE id = ?", (eid,))


def nova_midia(exercicio_id, tipo="imagem", **extra):
    """Cria uma linha em midias_exercicio (Fase 3, 09/09/2026) — pra testes
    que montam o exercício direto no banco (via novo_exercicio) e precisam
    de mídias reais associadas, sem passar pela validação da API."""
    campos = ["exercicio_id", "tipo"]
    valores = [exercicio_id, tipo]
    for k, v in extra.items():
        campos.append(k)
        valores.append(v)
    placeholders = ", ".join("?" for _ in campos)
    mid = db.execute(f"INSERT INTO midias_exercicio ({', '.join(campos)}) VALUES ({placeholders})", tuple(valores))
    return db.query_one("SELECT * FROM midias_exercicio WHERE id = ?", (mid,))


def nova_categoria(org_id, nome="Pasta de Teste", **extra):
    """org_id=None cria na Biblioteca da Plataforma (pastas do Admin). Passe
    pasta_pai_id=<id> pra criar como subpasta."""
    campos = ["organizacao_id", "nome"]
    valores = [org_id, nome]
    for k, v in extra.items():
        campos.append(k)
        valores.append(v)
    placeholders = ", ".join("?" for _ in campos)
    cid = db.execute(f"INSERT INTO categorias_exercicio ({', '.join(campos)}) VALUES ({placeholders})", tuple(valores))
    return db.query_one("SELECT * FROM categorias_exercicio WHERE id = ?", (cid,))


class DuasClinicas:
    """Cenário padrão: duas clínicas (A e B), cada uma com gestor e
    profissionais, mais uma família — usado pelos testes de IDOR entre
    clínicas para provar que uma nunca enxerga/edita dado da outra."""

    def __init__(self):
        self.org_a = nova_organizacao("Clínica A")
        self.org_b = nova_organizacao("Clínica B")

        self.gestor_a = novo_usuario(self.org_a, "Gestora A", "gestora@a.com", "gestor")
        self.prof_a1 = novo_usuario(self.org_a, "Prof A1", "prof.a1@a.com", "profissional")
        self.prof_a2 = novo_usuario(self.org_a, "Prof A2", "prof.a2@a.com", "profissional")
        self.resp_a1 = novo_usuario(self.org_a, "Familia A1", "familia.a1@a.com", "responsavel")

        self.gestor_b = novo_usuario(self.org_b, "Gestor B", "gestor@b.com", "gestor")
        self.prof_b1 = novo_usuario(self.org_b, "Prof B1", "prof.b1@b.com", "profissional")
        self.resp_b1 = novo_usuario(self.org_b, "Familia B1", "familia.compartilhada@x.com", "responsavel")

        self.paciente_a1 = novo_paciente(self.org_a, "Paciente A1", "2018-01-01")
        self.paciente_a2 = novo_paciente(self.org_a, "Paciente A2", "2019-01-01")
        vincular_profissional(self.prof_a1["id"], self.paciente_a1)
        vincular_profissional(self.prof_a1["id"], self.paciente_a2)
