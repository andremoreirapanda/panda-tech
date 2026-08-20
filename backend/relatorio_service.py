"""
Relatório exportável em PDF (insight do usuário) — resumo da jornada
terapêutica de um paciente: objetivo, plano ativo, missões, diário e
gamificação, pronto pra imprimir ou anexar em outro sistema.

A evolução clínica (linguagem técnica) só entra no PDF quando quem pede é
Gestor ou Profissional — mesma regra já aplicada em toda a tela do
paciente, aqui replicada pra não vazar esse campo pra um PDF que a família
baixe.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

CorMarca = colors.HexColor("#5B4FE9")
CorTextoSuave = colors.HexColor("#6B7280")
CorFundoAlt = colors.HexColor("#F5F4FA")


def _estilos():
    base = getSampleStyleSheet()
    estilos = {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], textColor=CorMarca, fontSize=20, spaceAfter=4),
        "subtitulo": ParagraphStyle("subtitulo", parent=base["Normal"], textColor=CorTextoSuave, fontSize=10, spaceAfter=14),
        "secao": ParagraphStyle("secao", parent=base["Heading2"], textColor=CorMarca, fontSize=13, spaceBefore=14, spaceAfter=6),
        "corpo": ParagraphStyle("corpo", parent=base["Normal"], fontSize=10, leading=14),
        "corpo_suave": ParagraphStyle("corpo_suave", parent=base["Normal"], fontSize=9, textColor=CorTextoSuave, leading=13),
        "rodape": ParagraphStyle("rodape", parent=base["Normal"], fontSize=8, textColor=CorTextoSuave),
    }
    return estilos


def gerar_relatorio_pdf(dados: dict, incluir_evolucao_clinica: bool) -> bytes:
    """
    `dados` é o mesmo formato retornado por GET /jornada/paciente/<id> —
    reaproveita a lógica que já existe pra montar esse bundle, sem duplicar
    consultas ao banco.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm)
    e = _estilos()
    story = []

    paciente = dados["paciente"]
    org_nome = dados.get("organizacao_nome", "Clínica")

    story.append(Paragraph(org_nome, e["subtitulo"]))
    story.append(Paragraph(f"Relatório de Acompanhamento — {paciente['nome']}", e["titulo"]))
    idade_txt = dados.get("idade_texto", "")
    story.append(Paragraph(f"{idade_txt} · Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}", e["subtitulo"]))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#E5E7EB"), thickness=1))

    jornada = dados.get("jornada")
    if not jornada:
        story.append(Spacer(1, 16))
        story.append(Paragraph("Este paciente ainda não tem uma jornada terapêutica iniciada.", e["corpo"]))
        doc.build(story)
        return buffer.getvalue()

    story.append(Paragraph("Objetivo Principal", e["secao"]))
    story.append(Paragraph(jornada.get("objetivo_principal", ""), e["corpo"]))

    plano = dados.get("plano_ativo")
    if plano:
        story.append(Paragraph(f"Plano: {plano['titulo']}", e["secao"]))
        story.append(Paragraph(f"Progresso: {dados.get('progresso_pct', 0)}% concluído ({dados.get('missoes_concluidas', 0)}/{dados.get('missoes_total', 0)} missões)", e["corpo"]))

        missoes = dados.get("missoes", [])
        if missoes:
            linhas = [["Missão", "Tipo", "Status", "Prazo"]]
            rotulos_status = {"pendente": "A fazer", "iniciada": "Em andamento", "concluida": "Concluída", "rascunho": "Rascunho", "atrasada": "Atrasada"}
            for m in missoes:
                tipo_txt = "Semanal" if m.get("tipo") == "semanal" else "Diária"
                if m.get("tipo") == "semanal" and m.get("status") != "concluida":
                    tipo_txt += f" ({m.get('dias_concluidos_total', 0)}/7 dias)"
                linhas.append([m["titulo"], tipo_txt, rotulos_status.get(m["status"], m["status"]), m.get("prazo") or "—"])
            tabela = Table(linhas, colWidths=[7.5 * cm, 3.2 * cm, 3 * cm, 2.3 * cm])
            tabela.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), CorMarca),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CorFundoAlt]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(Spacer(1, 6))
            story.append(tabela)
    else:
        story.append(Paragraph("Nenhum plano terapêutico ativo no momento.", e["secao"]))

    diarios = dados.get("diarios_recentes", [])
    if diarios:
        story.append(Paragraph("Diário Terapêutico — registros recentes", e["secao"]))
        for d in diarios:
            data_fmt = (d.get("data_atendimento") or "")[:10]
            story.append(Paragraph(f"<b>{data_fmt}</b> — {d.get('profissional_nome', '')}", e["corpo"]))
            if incluir_evolucao_clinica and d.get("evolucao_clinica"):
                story.append(Paragraph(d["evolucao_clinica"], e["corpo_suave"]))
            if d.get("mensagem_familia"):
                story.append(Paragraph(f"Mensagem para a família: {d['mensagem_familia']}", e["corpo_suave"]))
            story.append(Spacer(1, 6))

    gam = dados.get("gamificacao")
    if gam:
        story.append(Paragraph("Engajamento", e["secao"]))
        story.append(Paragraph(
            f"Nível {gam.get('nivel', 1)} · {gam.get('xp_total', 0)} XP · "
            f"{gam.get('estrelas', 0)} estrelas · {gam.get('sequencia_dias', 0)} dias seguidos de prática",
            e["corpo"],
        ))

    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#E5E7EB"), thickness=1))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Documento gerado automaticamente pela plataforma Panda Tech. "
        "As informações aqui resumidas complementam, mas não substituem, o prontuário clínico completo.",
        e["rodape"],
    ))

    doc.build(story)
    return buffer.getvalue()
