"""PDF do extrato financeiro do paciente (Financeiro 6.5, 23/11/2026) — para entregar à família.

Recebe o dicionário de `relatorios_service.extrato_paciente`. Mesmo visual do fechamento de caixa
(`caixa_pdf`): logo, cabeçalho, tabelas e "Gerado pelo PandaUp".
"""
import io
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from caixa_pdf import _data, _data_hora, _logo, _moeda, _tabela, rotulo_forma
from relatorio_service import _estilos

STATUS = {"pendente": "Em aberto", "parcial": "Paga em parte", "pago": "Paga", "vencido": "Vencida"}


def gerar_extrato_pdf(dados, clinica_nome, logo_base64, emitido_em):
    e = _estilos()
    celula = e["corpo_suave"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            leftMargin=1.6 * cm, rightMargin=1.6 * cm, title="Extrato financeiro")
    story = []
    logo = _logo(logo_base64)
    if logo:
        logo.hAlign = "LEFT"
        story += [logo, Spacer(1, 6)]
    story.append(Paragraph(escape(clinica_nome or "Clínica"), e["corpo"]))
    story.append(Paragraph("Extrato financeiro", e["titulo"]))
    p = dados["paciente"]
    periodo = _data(dados["de"]) if dados["de"] == dados["ate"] else f"{_data(dados['de'])} a {_data(dados['ate'])}"
    story.append(Paragraph(f"Paciente: <b>{escape(p['nome'] or '')}</b>", e["corpo"]))
    story.append(Paragraph(f"Período: {periodo} · Emitido em {_data_hora(emitido_em)}", e["subtitulo"]))

    t = dados["totais"]
    story.append(Paragraph("Resumo", e["secao"]))
    story.append(_tabela([["", "Valor"],
                          ["Cobrado no período", _moeda(t["cobrado_centavos"])],
                          ["Pago no período", _moeda(t["pago_centavos"])],
                          ["Saldo em aberto hoje", _moeda(t["saldo_aberto_centavos"])]], [8 * cm, 4 * cm]))

    story.append(Paragraph("Sessões", e["secao"]))
    if dados["sessoes"]:
        story.append(_tabela([["Data/hora", "Profissional", "Especialidade", "Procedimento", "Situação", "Valor"]] + [
            [_data_hora(s["data_hora"]), Paragraph(escape(s["profissional_nome"] or ""), celula),
             Paragraph(escape(s["especialidade"] or ""), celula), Paragraph(escape(s["procedimento_nome"] or ""), celula),
             Paragraph(escape(s["situacao"] or ""), celula), _moeda(s["valor_centavos"])]
            for s in dados["sessoes"]], [2.6 * cm, 2.5 * cm, 3.0 * cm, 3.4 * cm, 3.6 * cm, 2.1 * cm]))
    else:
        story.append(Paragraph("Nenhuma sessão no período.", celula))

    story.append(Paragraph("Cobranças", e["secao"]))
    if dados["cobrancas"]:
        story.append(_tabela([["Vencimento", "Descrição", "Situação", "A pagar", "Pago", "Saldo"]] + [
            [_data(c["vencimento"]), Paragraph(escape(c["descricao"] or ""), celula),
             STATUS.get(c["status"], c["status"]), _moeda(c["a_pagar_centavos"]), _moeda(c["pago_centavos"]),
             _moeda(c["saldo_centavos"])]
            for c in dados["cobrancas"]], [2.4 * cm, 5.4 * cm, 2.6 * cm, 2.4 * cm, 2.2 * cm, 2.2 * cm]))
    else:
        story.append(Paragraph("Nenhuma cobrança no período.", celula))

    story.append(Paragraph("Pagamentos", e["secao"]))
    if dados["pagamentos"]:
        story.append(_tabela([["Data", "Cobrança", "Forma", "Valor"]] + [
            [_data_hora(x["pago_em"]), Paragraph(escape(x["cobranca_descricao"] or ""), celula),
             rotulo_forma(x["forma"]) + (" (estornado)" if x["estornado"] else ""),
             _moeda(x["valor_centavos"])]
            for x in dados["pagamentos"]], [3 * cm, 7.6 * cm, 4 * cm, 2.6 * cm]))
    else:
        story.append(Paragraph("Nenhum pagamento no período.", celula))

    story += [Spacer(1, 16), Paragraph("Gerado pelo PandaUp", e["rodape"])]
    doc.build(story)
    return buffer.getvalue()
