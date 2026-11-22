"""PDF do relatório de atendimentos do repasse (Financeiro, etapa 3 — spec 6.1 e 6.4).

Serve ao relatório em aberto (`repasse_service.relatorio`) e ao fechamento já pago
(`repasse_service.detalhe_fechamento`); as rotas montam o mesmo dicionário para os dois.
"""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from caixa_pdf import _data, _data_hora, _logo, _moeda, _tabela
from relatorio_service import _estilos
import repasse_regras as rregras

_ROTULO_ORIGEM = {"manual": "Manual", "estorno": "Estorno", "status": "Sessão desmarcada/falta",
                  "recredito": "Recrédito"}

ROTULOS_BASE = {"procedimento": "valor do procedimento", "rateado": "rateio do valor pago"}


def rotulo_regra_do_item(item):
    """Rótulo da regra de uma linha de `repasse_itens` (guarda modo/percentual/valor soltos)."""
    if not item.get("regra_modo"):
        return "a definir"
    return rregras.rotulo_regra({"modo": item["regra_modo"],
                                 "percentual_centesimos": item.get("regra_percentual_centesimos"),
                                 "valor_centavos": item.get("regra_valor_centavos")})


def _sessao_texto(s):
    n, t = s.get("sessao_numero"), s.get("sessao_total")
    if n and t:
        return f"{n} de {t}"
    return str(n) if n else "-"


def gerar_repasse_pdf(d):
    """`d`: clinica_nome, logo_base64, emitido_em, de, ate, profissional_nome, registro, sessoes
    (data_hora, paciente_nome, descricao, sessao_numero/total, especialidade, base_centavos,
    regra_rotulo, profissional_centavos, clinica_centavos), por_especialidade, ajustes, totais,
    base (opcional) e pago_em (só no fechamento)."""
    e = _estilos()
    celula = e["corpo_suave"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=1.4 * cm, bottomMargin=1.4 * cm,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm, title="Relatório de atendimentos")
    story = []
    logo = _logo(d.get("logo_base64"))
    if logo:
        logo.hAlign = "LEFT"
        story += [logo, Spacer(1, 6)]
    story.append(Paragraph(escape(d.get("clinica_nome") or "Clínica"), e["corpo"]))
    story.append(Paragraph("Relatório de atendimentos", e["titulo"]))
    periodo = _data(d["de"]) if d["de"] == d["ate"] else f"{_data(d['de'])} a {_data(d['ate'])}"
    linha = f"Período: {periodo} · Emitido em {_data_hora(d['emitido_em'])}"
    if d.get("base"):
        linha += f" · Base de cálculo: {ROTULOS_BASE.get(d['base'], d['base'])}"
    if d.get("pago_em"):
        linha += f" · Pago em {_data(d['pago_em'])}"
    story.append(Paragraph(linha, e["subtitulo"]))
    prof = escape(d.get("profissional_nome") or "")
    if d.get("registro"):
        prof += f" · {escape(d['registro'])}"
    story.append(Paragraph(f"Profissional: {prof}", e["corpo"]))

    story.append(Paragraph("Sessões", e["secao"]))
    sessoes = d.get("sessoes") or []
    if sessoes:
        story.append(_tabela(
            [["Data/hora", "Paciente", "Procedimento / acordo", "Sessão", "Especialidade", "Base", "Regra",
              "Profissional", "Clínica"]] + [
                [_data_hora(s["data_hora"]), Paragraph(escape(s.get("paciente_nome") or ""), celula),
                 Paragraph(escape(s.get("descricao") or ""), celula), _sessao_texto(s),
                 Paragraph(escape(s.get("especialidade") or ""), celula), _moeda(s["base_centavos"]),
                 Paragraph(escape(s.get("regra_rotulo") or ""), celula),
                 _moeda(s["profissional_centavos"] or 0), _moeda(s["clinica_centavos"] or 0)]
                for s in sessoes],
            [2.8 * cm, 3.8 * cm, 4.6 * cm, 1.6 * cm, 3.2 * cm, 2.3 * cm, 2.2 * cm, 2.6 * cm, 2.3 * cm]))
    else:
        story.append(Paragraph("Nenhuma sessão neste relatório.", celula))

    story.append(Paragraph("Totais por especialidade", e["secao"]))
    if d.get("por_especialidade"):
        story.append(_tabela([["Especialidade", "Sessões", "Base", "Profissional"]] + [
            [Paragraph(escape(g["especialidade"] or ""), celula), str(g["quantidade"]),
             _moeda(g["base_centavos"]), _moeda(g["profissional_centavos"])]
            for g in d["por_especialidade"]], [8 * cm, 3 * cm, 4 * cm, 4 * cm]))
    else:
        story.append(Paragraph("Sem sessões.", celula))

    story.append(Paragraph("Ajustes", e["secao"]))
    if d.get("ajustes"):
        story.append(_tabela([["Descrição", "Origem", "Valor"]] + [
            [Paragraph(escape(a["descricao"] or ""), celula), _ROTULO_ORIGEM.get(a.get("origem"), "Manual"),
             _moeda(a["valor_centavos"])]
            for a in d["ajustes"]], [11 * cm, 5 * cm, 4 * cm]))
    else:
        story.append(Paragraph("Nenhum ajuste.", celula))

    story.append(Paragraph("Resumo", e["secao"]))
    story.append(_tabela([["", "Valor"],
                          ["Total das sessões (base)", _moeda(d["total_sessoes_centavos"])],
                          ["Parte do profissional", _moeda(d["total_profissional_centavos"])],
                          ["Ajustes", _moeda(d["total_ajustes_centavos"])],
                          ["Valor a pagar", _moeda(d["a_pagar_centavos"])]], [10 * cm, 4 * cm]))

    story.append(Spacer(1, 40))
    assinatura = Table([["Assinatura do profissional", "Data"]], colWidths=[10 * cm, 5 * cm])
    assinatura.hAlign = "LEFT"
    assinatura.setStyle(TableStyle([("LINEABOVE", (0, 0), (0, 0), 0.6, colors.black),
                                    ("LINEABOVE", (1, 0), (1, 0), 0.6, colors.black),
                                    ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(assinatura)
    story += [Spacer(1, 12), Paragraph("Gerado pelo PandaUp", e["rodape"])]
    doc.build(story)
    return buffer.getvalue()
