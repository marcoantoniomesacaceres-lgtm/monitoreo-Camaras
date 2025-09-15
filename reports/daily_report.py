import sqlite3
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from config import DB_PATH


def header_footer(canvas, doc):
    """Encabezado y pie de página en cada hoja"""
    canvas.saveState()
    canvas.setFont("Times-Bold", 10)
    canvas.drawString(72, 760, "HIT - TECH PEOPLE SAS")  # Encabezado

    canvas.setFont("Times-Roman", 9)
    canvas.drawString(72, 30, f"Reporte generado automáticamente - {datetime.date.today()}")
    canvas.drawRightString(550, 30, f"Página {doc.page}")  # Pie con número de página
    canvas.restoreState()


def generate_daily_report():
    today = datetime.date.today()
    filepath = f"reports/daily_report_{today}.pdf"

    # Documento PDF
    doc = SimpleDocTemplate(
        filepath, pagesize=letter,
        rightMargin=72, leftMargin=72,
        topMargin=72, bottomMargin=72
    )
    story = []

    # Estilos tipo APA
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Times-Bold",
        fontSize=16,
        alignment=1,  # centrado
        spaceAfter=20,
    )
    normal_style = styles["Normal"]

    # Portada
    story.append(Paragraph("Reporte Diario de Movimientos", title_style))
    story.append(Paragraph(f"Fecha: {today}", normal_style))
    story.append(Spacer(1, 40))
    story.append(Paragraph(
        "Este reporte presenta los eventos registrados en el sistema de monitoreo de personas, "
        "bajo el modelo de control de accesos.",
        normal_style
    ))
    story.append(PageBreak())

    # Conexión a la base de datos
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, action, timestamp, person_id FROM events WHERE DATE(timestamp) = ?",
        (today.isoformat(),)
    )
    data = cur.fetchall()
    conn.close()

    if not data:
        story.append(Paragraph("No se registraron eventos el día de hoy.", normal_style))
    else:
        # Tabla de datos
        table_data = [["ID", "Acción", "Fecha/Hora", "ID Persona"]]
        table_data.extend(data)

        table = Table(table_data, colWidths=[50, 150, 150, 100])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))

        story.append(Paragraph("Tabla 1. Eventos del día", normal_style))
        story.append(Spacer(1, 12))
        story.append(table)

    # Construir PDF con encabezado y pie
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

    return filepath