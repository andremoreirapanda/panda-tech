"""
Ponto de entrada WSGI para hospedagem cPanel (CloudLinux "Setup Python App" /
Phusion Passenger).

Este arquivo precisa ficar na RAIZ da "Application Root" configurada no
cPanel (a mesma pasta que contém as pastas backend/ e frontend/, lado a
lado — exatamente como o repositório já está organizado). O Passenger
importa este módulo e procura por uma variável chamada `application`.

O app Flask de verdade mora em backend/app.py (mesmo código que roda na
Fly.io) — aqui só adicionamos backend/ ao sys.path (os imports internos do
projeto são todos "flat", ex: `from blueprints import ...`, `import db`,
então backend/ precisa estar no sys.path, não a raiz do projeto) e
reaproveitamos o `app` que backend/app.py já cria.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Alguns caminhos internos (ex: db.py -> encanto.db) são calculados a partir
# de __file__, então não dependem do diretório de trabalho — mas manter o
# cwd em backend/ replica exatamente o "cd backend && python app.py" do
# ambiente de desenvolvimento, evitando qualquer surpresa.
os.chdir(BACKEND_DIR)

from app import app as application  # noqa: E402 (import depois do sys.path de propósito)
