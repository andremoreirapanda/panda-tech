"""PDF do fechamento de caixa (Financeiro, etapa 2 — 09/11/2026).

Mesmo caminho do relatório da jornada (reportlab + `relatorio_service._estilos`).
Recebe o dicionário de `caixa_service.fechamento`.
"""
import base64
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from relatorio_service import CorFundoAlt, CorMarca, _estilos

ROTULOS_FORMA = {
    "pix": "Pix", "dinheiro": "Dinheiro", "cartao_credito": "Cartão de crédito",
    "cartao_debito": "Cartão de débito", "transferencia": "Transferência", "cartao": "Cartão", "boleto": "Boleto",
}


def rotulo_forma(forma):
    return ROTULOS_FORMA.get(forma, forma or "")


def _moeda(centavos):
    negativo = centavos < 0
    reais, cent = divmod(abs(int(centavos)), 100)
    texto = f"R$ {reais:,}".replace(",", ".") + f",{cent:02d}"
    return f"-{texto}" if negativo else texto


def _data(iso):
    """'AAAA-MM-DD' → 'DD/MM/AAAA'."""
    iso = str(iso or "")[:10]
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if len(iso) == 10 else iso


def _data_hora(iso):
    """'AAAA-MM-DD HH:MM:SS' → 'DD/MM/AAAA HH:MM'."""
    iso = str(iso or "")
    hora = iso[11:16]
    return f"{_data(iso)} {hora}".strip()


def _logo(logo_base64):
    """Image do logo da clínica, ou None se não houver ou não abrir."""
    if not logo_base64:
        return None
    try:
        bruto = logo_base64.split(",", 1)[1] if logo_base64.startswith("data:") else logo_base64
        dados = io.BytesIO(base64.b64decode(bruto, validate=False))
        largura, altura = ImageReader(dados).getSize()
        if not largura or not altura:
            return None
        dados.seek(0)
        alto = 1.6 * cm
        largo = min(alto * largura / altura, 6 * cm)
        return Image(dados, width=largo, height=largo * altura / largura)
    except Exception:  # logo quebrado nunca derruba o relatório
        return None


def _tabela(linhas, larguras, alinhar_direita_ultima=True):
    t = Table(linhas, colWidths=larguras, repeatRows=1)
    t.hAlign = "LEFT"
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), CorFundoAlt),
        ("TEXTCOLOR", (0, 0), (-1, 0), CorMarca),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if alinhar_direita_ultima:
        estilo.append(("ALIGN", (-1, 0), (-1, -1), "RIGHT"))
    t.setStyle(TableStyle(estilo))
    return t


def gerar_caixa_pdf(dados, clinica_nome, logo_base64, emitido_em, filtros=None):
    e = _estilos()
    celula = e["corpo_suave"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            leftMargin=1.6 * cm, rightMargin=1.6 * cm, title="Fechamento de caixa")
    story = []
    logo = _logo(logo_base64)
    if logo:
        logo.hAlign = "LEFT"
        story += [logo, Spacer(1, 6)]
    story.append(Paragraph(escape(clinica_nome or "Clínica"), e["corpo"]))
    story.append(Paragraph("Fechamento de caixa", e["titulo"]))
    periodo = _data(dados["de"]) if dados["de"] == dados["ate"] else f"{_data(dados['de'])} a {_data(dados['ate'])}"
    linha = f"Período: {periodo} · Emitido em {_data_hora(emitido_em)}"
    f = filtros or {}
    if f.get("recebido_por"):
        linha += f" · Quem recebeu: {escape(f['recebido_por'])}"
    if f.get("forma"):
        linha += f" · Forma: {escape(rotulo_forma(f['forma']))}"
    story.append(Paragraph(linha, e["subtitulo"]))

    t = dados["totais"]
    story.append(Paragraph("Resumo", e["secao"]))
    story.append(_tabela([["", "Valor"], ["Recebido", _moeda(t["recebido_centavos"])],
                          ["Estornado", _moeda(-t["estornado_centavos"]) if t["estornado_centavos"] else _moeda(0)],
                          ["Líquido", _moeda(t["liquido_centavos"])]], [8 * cm, 4 * cm]))

    def grupo(titulo, itens, chave, rotulo):
        story.append(Paragraph(titulo, e["secao"]))
        if not itens:
            story.append(Paragraph("Sem movimento no período.", celula))
            return
        story.append(_tabela([[rotulo, "Recebido", "Estornado", "Líquido"]] + [
            [Paragraph(escape(rotulo_forma(i[chave]) if chave == "forma" else i[chave]), celula),
             _moeda(i["recebido_centavos"]), _moeda(i["estornado_centavos"]), _moeda(i["liquido_centavos"])]
            for i in itens], [7 * cm, 3.4 * cm, 3.4 * cm, 3.4 * cm]))

    grupo("Por forma de pagamento", dados["por_forma"], "forma", "Forma")
    grupo("Por quem recebeu", dados["por_quem"], "recebido_por", "Quem recebeu")

    story.append(Paragraph("Recebimentos", e["secao"]))
    if dados["recebimentos"]:
        story.append(_tabela([["Data/hora", "Paciente", "Cobrança", "Forma", "Quem recebeu", "Valor"]] + [
            [_data_hora(r["pago_em"]), Paragraph(escape(r["paciente_nome"] or ""), celula),
             Paragraph(escape(r["cobranca_descricao"] or f"#{r['cobranca_id']}"), celula),
             Paragraph(escape(rotulo_forma(r["forma"])) + (" (estornado)" if r["estornado"] else ""), celula),
             Paragraph(escape(r["recebido_por"]), celula), _moeda(r["valor_centavos"])]
            for r in dados["recebimentos"]], [2.6 * cm, 3.6 * cm, 3.6 * cm, 2.6 * cm, 2.8 * cm, 2.6 * cm]))
    else:
        story.append(Paragraph("Nenhum recebimento no período.", celula))

    story.append(Paragraph("Estornos", e["secao"]))
    if dados["estornos"]:
        story.append(_tabela([["Data do estorno", "Paciente", "Cobrança", "Forma", "Motivo", "Valor"]] + [
            [_data_hora(r["estornado_em"]), Paragraph(escape(r["paciente_nome"] or ""), celula),
             Paragraph(escape(r["cobranca_descricao"] or f"#{r['cobranca_id']}"), celula),
             Paragraph(escape(rotulo_forma(r["forma"])), celula), Paragraph(escape(r["motivo"] or ""), celula),
             _moeda(-r["valor_centavos"])]
            for r in dados["estornos"]], [2.6 * cm, 3.4 * cm, 3.4 * cm, 2.4 * cm, 3.4 * cm, 2.6 * cm]))
    else:
        story.append(Paragraph("Nenhum estorno no período.", celula))

    story += [Spacer(1, 16), Paragraph("Gerado pelo PandaUp", e["rodape"])]
    doc.build(story)
    return buffer.getvalue()
