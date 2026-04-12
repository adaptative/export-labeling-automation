#!/usr/bin/env python3
"""
Generate the comprehensive Solution Design & Architecture PDF document for
the Export Labeling Automation System.

This document contains every detail needed for a real-world development team
to build the application:
  - Current manual process (pain points, time, errors)
  - Proposed automation (end-to-end workflow)
  - Available artifacts (input/output documents already identified)
  - System architecture (layers, data flow, components)
  - AI agent catalog (roles, I/O, tools, prompts)
  - Orchestration and feedback loops
  - Human-in-the-loop interactive chatbot specification
  - Technology stack with specific library/model choices
  - Data models, APIs, database schemas
  - Implementation roadmap and milestones
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm, inch
from reportlab.lib.colors import HexColor, black, white, Color
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, Image, ListFlowable, ListItem, HRFlowable, Flowable,
    NextPageTemplate, PageTemplate, Frame, BaseDocTemplate
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OUTPUT_DIR = os.environ.get("LABELFORGE_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "..", "outputs", "docs"))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "Export_Labeling_Automation_Solution_Design.pdf")

# ── Color palette ─────────────────────────────────────────────────────────
PRIMARY = HexColor("#1a3a6c")      # deep blue
SECONDARY = HexColor("#2b7fc7")    # mid blue
ACCENT = HexColor("#d32f2f")       # red (same as label dimensions)
SUCCESS = HexColor("#2e7d32")      # green
WARN = HexColor("#ef6c00")         # orange
TEXT = HexColor("#212121")
MUTED = HexColor("#666666")
LIGHT_BG = HexColor("#f5f7fa")
BORDER = HexColor("#cccccc")
TABLE_HEADER = HexColor("#1a3a6c")
TABLE_ROW_ALT = HexColor("#f0f4f8")
CODE_BG = HexColor("#272822")
CODE_TEXT = HexColor("#f8f8f2")

# ── Page setup ────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_L = 20 * mm
MARGIN_R = 20 * mm
MARGIN_T = 25 * mm
MARGIN_B = 25 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

# ── Paragraph styles ──────────────────────────────────────────────────────
styles = getSampleStyleSheet()

H1 = ParagraphStyle(
    'H1', parent=styles['Heading1'], fontName='Helvetica-Bold',
    fontSize=22, textColor=PRIMARY, spaceAfter=10, spaceBefore=20,
    leading=26, alignment=TA_LEFT, keepWithNext=True,
)
H2 = ParagraphStyle(
    'H2', parent=styles['Heading2'], fontName='Helvetica-Bold',
    fontSize=16, textColor=PRIMARY, spaceAfter=8, spaceBefore=16,
    leading=20, keepWithNext=True,
)
H3 = ParagraphStyle(
    'H3', parent=styles['Heading3'], fontName='Helvetica-Bold',
    fontSize=13, textColor=SECONDARY, spaceAfter=6, spaceBefore=12,
    leading=17, keepWithNext=True,
)
H4 = ParagraphStyle(
    'H4', parent=styles['Heading4'], fontName='Helvetica-Bold',
    fontSize=11, textColor=TEXT, spaceAfter=4, spaceBefore=8,
    leading=14, keepWithNext=True,
)
BODY = ParagraphStyle(
    'Body', parent=styles['Normal'], fontName='Helvetica',
    fontSize=9.5, textColor=TEXT, leading=13,
    alignment=TA_JUSTIFY, spaceAfter=6,
)
BULLET = ParagraphStyle(
    'Bullet', parent=BODY, leftIndent=14, bulletIndent=2,
    spaceAfter=3,
)
CODE = ParagraphStyle(
    'Code', parent=styles['Code'], fontName='Courier',
    fontSize=8, textColor=CODE_TEXT, backColor=CODE_BG,
    leading=10, leftIndent=8, rightIndent=8,
    borderPadding=6, spaceAfter=8, spaceBefore=6,
)
INLINE_CODE_TAG = '<font face="Courier" color="#d32f2f">'
NOTE = ParagraphStyle(
    'Note', parent=BODY, backColor=LIGHT_BG, borderColor=SECONDARY,
    borderWidth=0.5, borderPadding=8, leftIndent=6, rightIndent=6,
    spaceBefore=6, spaceAfter=10,
)
CAPTION = ParagraphStyle(
    'Caption', parent=BODY, fontSize=8, textColor=MUTED,
    alignment=TA_CENTER, spaceAfter=8,
)
TITLE = ParagraphStyle(
    'Title', parent=styles['Title'], fontName='Helvetica-Bold',
    fontSize=30, textColor=PRIMARY, alignment=TA_CENTER,
    leading=36, spaceAfter=12,
)
SUBTITLE = ParagraphStyle(
    'Subtitle', parent=styles['Normal'], fontName='Helvetica',
    fontSize=14, textColor=SECONDARY, alignment=TA_CENTER,
    leading=18, spaceAfter=8,
)

# ── Helper functions ──────────────────────────────────────────────────────
def p(text, style=BODY):
    return Paragraph(text, style)

def bullet_list(items, style=BULLET):
    return ListFlowable(
        [ListItem(Paragraph(it, style), leftIndent=14, value='circle') for it in items],
        bulletType='bullet', start='circle', leftIndent=12,
    )

def numbered_list(items, style=BULLET):
    return ListFlowable(
        [ListItem(Paragraph(it, style), leftIndent=14) for it in items],
        bulletType='1', leftIndent=12,
    )

def kv_table(pairs, col_widths=None, header=None):
    """Two-column key/value table."""
    data = []
    if header:
        data.append(header)
    data.extend([[Paragraph(str(k), BODY), Paragraph(str(v), BODY)] for k, v in pairs])
    if col_widths is None:
        col_widths = [CONTENT_W * 0.28, CONTENT_W * 0.72]
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style_cmds = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.3, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1 if header else 0), (-1, -1), [white, TABLE_ROW_ALT]),
    ]
    if header:
        style_cmds += [
            ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
        ]
    t.setStyle(TableStyle(style_cmds))
    return t

def multi_table(headers, rows, col_widths=None):
    data = [[Paragraph(f"<b>{h}</b>", BODY) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c), BODY) for c in r])
    if col_widths is None:
        n = len(headers)
        col_widths = [CONTENT_W / n] * n
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.3, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, TABLE_ROW_ALT]),
    ]))
    return t

def code_block(code_text):
    """Render a code block with fixed-width font and background."""
    # Escape characters properly
    escaped = (code_text
               .replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace("\n", "<br/>")
               .replace("  ", "&nbsp;&nbsp;"))
    return Paragraph(escaped, CODE)

def chat_bubble(speaker, text, role='agent'):
    """Render a chat bubble flowable with speaker label."""
    if role == 'agent':
        bg = HexColor("#e8f1ff")
        brd = SECONDARY
        prefix = f'<font color="#1a3a6c"><b>[AGENT]</b></font> '
    elif role == 'human':
        bg = HexColor("#fff4e6")
        brd = WARN
        prefix = f'<font color="#ef6c00"><b>[HUMAN]</b></font> '
    else:
        bg = LIGHT_BG
        brd = MUTED
        prefix = f'<font color="#666666"><b>[SYSTEM]</b></font> '
    s = ParagraphStyle(
        f'Chat_{role}', parent=BODY, backColor=bg,
        borderColor=brd, borderWidth=0.5, borderPadding=6,
        leftIndent=4, rightIndent=4, spaceBefore=3, spaceAfter=3,
        fontSize=9, leading=12,
    )
    return Paragraph(prefix + f'<b>{speaker}:</b> ' + text, s)

def section_divider():
    return HRFlowable(width="100%", thickness=0.8, color=SECONDARY,
                       spaceBefore=6, spaceAfter=12)


# ── Page decoration (header/footer) ───────────────────────────────────────
def draw_header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    # Header
    canvas_obj.setStrokeColor(SECONDARY)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN_L, PAGE_H - MARGIN_T + 12,
                     PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 12)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(MUTED)
    canvas_obj.drawString(MARGIN_L, PAGE_H - MARGIN_T + 16,
                           "Export Labeling Automation — Solution Design & Architecture")
    canvas_obj.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 16,
                                "Nakoda Art & Craft · v1.0")
    # Footer
    canvas_obj.setStrokeColor(SECONDARY)
    canvas_obj.line(MARGIN_L, MARGIN_B - 10, PAGE_W - MARGIN_R, MARGIN_B - 10)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(MUTED)
    canvas_obj.drawString(MARGIN_L, MARGIN_B - 18,
                           "Confidential — Prepared for Nakoda Art & Craft")
    canvas_obj.drawRightString(PAGE_W - MARGIN_R, MARGIN_B - 18,
                                f"Page {doc.page}")
    canvas_obj.restoreState()


def draw_cover(canvas_obj, doc):
    """Draw the cover page (no header/footer)."""
    canvas_obj.saveState()
    # Background block
    canvas_obj.setFillColor(PRIMARY)
    canvas_obj.rect(0, PAGE_H - 260, PAGE_W, 260, fill=1, stroke=0)
    canvas_obj.setFillColor(SECONDARY)
    canvas_obj.rect(0, PAGE_H - 280, PAGE_W, 20, fill=1, stroke=0)
    canvas_obj.setFillColor(ACCENT)
    canvas_obj.rect(0, 0, PAGE_W, 15, fill=1, stroke=0)

    # Title text on dark band
    canvas_obj.setFillColor(white)
    canvas_obj.setFont("Helvetica-Bold", 32)
    canvas_obj.drawCentredString(PAGE_W / 2, PAGE_H - 120,
                                   "Export Labeling")
    canvas_obj.drawCentredString(PAGE_W / 2, PAGE_H - 160,
                                   "Automation System")
    canvas_obj.setFont("Helvetica", 14)
    canvas_obj.drawCentredString(PAGE_W / 2, PAGE_H - 190,
                                   "Solution Design · Architecture · Agent Specification")
    canvas_obj.setFont("Helvetica-Oblique", 11)
    canvas_obj.drawCentredString(PAGE_W / 2, PAGE_H - 215,
                                   "From Purchase Order to Printer-Ready Die-Cut in Minutes")

    # Subtitle info block
    canvas_obj.setFillColor(PRIMARY)
    canvas_obj.setFont("Helvetica-Bold", 14)
    canvas_obj.drawCentredString(PAGE_W / 2, PAGE_H - 340,
                                   "Prepared for")
    canvas_obj.setFont("Helvetica-Bold", 18)
    canvas_obj.drawCentredString(PAGE_W / 2, PAGE_H - 365,
                                   "Nakoda Art & Craft")
    canvas_obj.setFont("Helvetica", 11)
    canvas_obj.setFillColor(MUTED)
    canvas_obj.drawCentredString(PAGE_W / 2, PAGE_H - 385,
                                   "Jodhpur, Rajasthan, India")

    # Scope box
    box_y = PAGE_H - 510
    canvas_obj.setFillColor(LIGHT_BG)
    canvas_obj.setStrokeColor(BORDER)
    canvas_obj.roundRect(MARGIN_L + 20, box_y, CONTENT_W - 40, 110,
                          8, fill=1, stroke=1)
    canvas_obj.setFillColor(PRIMARY)
    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.drawString(MARGIN_L + 35, box_y + 90, "Document Scope")
    canvas_obj.setFillColor(TEXT)
    canvas_obj.setFont("Helvetica", 9)
    lines = [
        "This document is the implementation blueprint for an AI-powered export",
        "labeling automation system. It covers the complete transformation from the",
        "current manual CorelDraw-based workflow to a multi-agent autonomous system",
        "with human-in-the-loop clarification when documents are missing or decisions",
        "are ambiguous. It is detailed enough for a development team to estimate, plan,",
        "and build the application without further requirements discovery.",
    ]
    y = box_y + 70
    for line in lines:
        canvas_obj.drawString(MARGIN_L + 35, y, line)
        y -= 12

    # Footer strip
    canvas_obj.setFillColor(MUTED)
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.drawCentredString(PAGE_W / 2, 50,
                                   "Version 1.0  ·  April 2026  ·  Confidential")
    canvas_obj.restoreState()


# ═══════════════════════════════════════════════════════════════════════════
#                         DOCUMENT CONTENT BUILDER
# ═══════════════════════════════════════════════════════════════════════════
story = []

# ── SECTION 1: Executive Summary ──────────────────────────────────────────
story.append(Paragraph("1. Executive Summary", H1))
story.append(section_divider())

story.append(p(
    "Nakoda Art & Craft, an export house based in Jodhpur specialising in "
    "handmade decorative items (paper mache, reclaimed wood, ceramic, stone), "
    "currently produces carton box die-cut printer sheets manually for every "
    "Purchase Order (PO) received from importers such as Sagebrook Home, "
    "Elevarre, and others. This document proposes a multi-agent AI system "
    "that automates the entire workflow — from PO ingestion to printer-ready "
    "SVG and client-approval PDF generation — reducing a 2–5 hour manual "
    "process per order down to approximately 3–10 minutes with 10–20 minutes "
    "of final human review."
))

story.append(p(
    "The system is designed to be <b>generic across any exporter/importer pair</b>. "
    "Input document formats vary wildly (PO formats differ per importer, "
    "protocols use annotated photographs, warning labels have legal wording "
    "requirements), so the ingestion side uses adaptive AI parsing. Output "
    "requirements on the other hand are fixed per importer (each importer has "
    "a deterministic die-cut template), so rendering is template-driven for "
    "maximum reliability and brand consistency."
))

story.append(p("<b>Key outcomes of this solution:</b>"))
story.append(bullet_list([
    "Time per order: <b>2-5 hours -> 10-20 minutes</b> (human review only)",
    "Accuracy: UPC barcodes, dimensions, case quantities, and warning label applicability determined by deterministic rules rather than manual lookup",
    "Compliance: Automatic application of importer-specific warning labels (PROP 65, FDA Non-Food Use, TSCA, Law Tags, Team Lift, Fragile, etc.) based on SKU attributes and destination",
    "Scalability: Onboarding a new importer is a one-time 2-4 hour session that captures their protocol, warning library, and die-cut template into an Importer Profile stored in the database",
    "Auditability: Every decision made by the AI is logged with its reasoning, making QA and rework efficient",
    "Human control: When the system is unsure or a critical document is missing, it pauses and opens an interactive chat with the human operator until the block is resolved",
]))

story.append(p(
    "<b>Proof of concept already built during this engagement:</b> Eight production-ready "
    "die-cut SVGs and eight approval PDFs have been generated for PO#25364 "
    "(8 items from the Sagebrook Home order) using the real protocol document, "
    "real warning labels, and the real brand logo extracted from the client's "
    "protocol PDF. These outputs are already in the client workspace folder. "
    "This document describes how to productise that proof of concept into a "
    "scalable, robust, multi-tenant application."
))

story.append(PageBreak())

# ── SECTION 2: Current Manual Process ─────────────────────────────────────
story.append(p("2. Current Manual Process", H1))
story.append(section_divider())

story.append(p("2.1 The Team and Tools", H2))
story.append(p(
    "The exporter's current labeling team typically consists of a designer "
    "trained in CorelDraw, a merchandiser who reads the PO, and a QA reviewer. "
    "The team communicates with the client via email attachments (PO, protocol, "
    "warning labels) and with the carton box printer via WhatsApp or courier "
    "with printed die-cut layouts. Tools in use today:"
))
story.append(kv_table([
    ("CorelDraw (X7 / 2021)", "Primary die-cut layout design tool. Human designers create panels by manually drawing rectangles, placing text boxes, importing logo files, and positioning handling symbols."),
    ("Microsoft Excel", "Used to write the Proforma Invoice (PI) based on production planning — carton dimensions, CBM, total cartons, item codes."),
    ("Email / WhatsApp", "Used to exchange PO, protocol, warning label PDFs, approval screenshots with the client. No central system of record."),
    ("Adobe Acrobat", "Used to open client-supplied PDFs (protocols, warning labels, checklists)."),
    ("Windows file folders", "Organised per-client, per-PO. Naming convention varies per team member."),
], header=[p("<b>Tool</b>", BODY), p("<b>Usage</b>", BODY)]))

story.append(p("2.2 Step-By-Step Manual Workflow", H2))
story.append(p(
    "Below is the actual step-by-step process the team follows today, captured "
    "during our discovery calls. Each step includes the approximate time spent, "
    "the artifacts consumed, and the common error modes observed."
))

manual_steps = [
    ("1. Receive PO",
     "Client emails a PO PDF (e.g., PO#25364 from Sagebrook Home). The merchandiser downloads it, skim-reads it, and forwards to design team.",
     "~5 min",
     "PO may arrive in any layout. Missing UPCs or inconsistent item codes are common."),
    ("2. Extract order data",
     "Merchandiser manually transcribes each SKU's item number, UPC, description, product dimensions, case quantity, and total ordered quantity from the PO into an internal Excel file.",
     "~20-40 min",
     "Transcription errors. UPCs are frequently mistyped (they're 12 digits). Descriptions get truncated."),
    ("3. Prepare Proforma Invoice (PI)",
     "Merchandiser fills out the PI Excel template with carton outer dimensions (L x W x H in inches), total cartons, CBM per carton, inner/outer pack counts, and HS codes. Dimensions are decided based on production planning and sample carton tests.",
     "~30-60 min",
     "Wrong dimensions lead to reprinting. CBM calculation errors affect freight quotes."),
    ("4. Consult client protocol",
     "Designer opens the Client Protocol PDF (e.g., Sagebrook Home SPO Process v3) and checks: brand treatment, handling symbol placement, panel layout rules, required fields, barcode placement. This document contains annotated photographs — designer interprets visually.",
     "~15 min (first time) / ~5 min (subsequent)",
     "Protocol sometimes gets updated by client without notification. Old versions still in use."),
    ("5. Determine required warning labels",
     "Designer (or QA) opens the Document Checklist PDF and the Warning Labels PDF. For each SKU they manually check: product material, product type, destination state, carton weight. Based on these they decide which warning labels apply (Prop 65? FDA Non-Food? TSCA? Team Lift? Fragile?).",
     "~10-20 min per order",
     "Easy to miss a rule. Rules change per importer. Prop 65 has product vs furniture variants that get confused."),
    ("6. Design die-cut in CorelDraw",
     "For each SKU, designer creates a new CorelDraw file: draws the die-cut outline (4 panels + top/bottom flaps), adds fold lines, imports the brand logo, types item number / case qty / description / dimensions, imports and positions handling symbols, types PO number and blank fields for carton number and weight, draws a rough product line sketch, places the UPC barcode.",
     "~20-40 min per SKU",
     "Many manual steps. Typos. Inconsistent font sizes. Barcode placement errors. Line sketches vary in quality."),
    ("7. Generate UPC barcode",
     "Designer uses an online barcode generator (barcodesinc.com or similar) to produce a UPC-A image from the 12-digit code, downloads the PNG, and imports it into CorelDraw.",
     "~3 min per SKU",
     "Wrong barcode format (EAN vs UPC-A). Low-resolution images that print badly."),
    ("8. Internal review",
     "A senior designer or QA reviews each die-cut file for typos, missing labels, wrong dimensions, and protocol compliance.",
     "~10 min per SKU",
     "Defects still slip through under deadline pressure."),
    ("9. Send to client for approval",
     "Designer exports each die-cut as a PDF and emails them to the importer's QA contact. The PDF has red dimension annotations showing the panel widths and heights so the client can verify the layout.",
     "~15 min per order",
     "Approval rounds can take 1-3 days per round. Multiple rounds common."),
    ("10. Client feedback and rework",
     "Client marks up the PDFs with comments (typos, font size, brand guideline violations, wrong SKU info). Designer fixes and resubmits.",
     "~20-60 min per round",
     "Rework cycles are the biggest time sink."),
    ("11. Send to carton box printer",
     "Once approved, designer sends the CorelDraw files (.cdr) or exports as SVG/PDF and sends via WhatsApp or printed hard copy to the carton printer's workshop, who then sets up the printing plates.",
     "~10 min",
     "File format issues at the printer (missing fonts, converted outlines)."),
]

story.append(multi_table(
    ["Step", "Description", "Time", "Common Errors"],
    [[s[0], s[1], s[2], s[3]] for s in manual_steps],
    col_widths=[CONTENT_W*0.14, CONTENT_W*0.52, CONTENT_W*0.10, CONTENT_W*0.24]
))

story.append(p("2.3 Quantified Pain Points", H2))
story.append(p(
    "Aggregating the above, an order with 10 SKUs typically consumes:"
))
story.append(kv_table([
    ("Merchandiser time", "1.5 - 2 hours (data entry, PI preparation, warning label lookups)"),
    ("Designer time", "4 - 7 hours (CorelDraw design for 10 SKUs at 25-40 min each)"),
    ("QA time", "1.5 hours (internal review + approval-round management)"),
    ("Elapsed time including client approval rounds", "2 - 5 business days"),
    ("Rework cycles per order (typical)", "1 - 3 rounds"),
    ("Error rate (defects found by client)", "15 - 30% of SKUs get at least one correction"),
    ("Scaling cost", "Linear — doubling SKUs doubles labour hours"),
]))

story.append(p(
    "<b>Biggest friction points identified:</b>"
))
story.append(bullet_list([
    "<b>Data transcription</b>: Humans retyping UPC codes, dimensions, item numbers from PO into the PI and then into CorelDraw text boxes. Single digits flipped in a UPC cause warehouse scanner failures downstream.",
    "<b>Warning label rule lookup</b>: No structured rules engine; designers rely on memory and checklist skimming. This is how Prop 65 violations and FDA warning omissions slip through.",
    "<b>CorelDraw manual layout</b>: Each panel is drawn from scratch every time. Same brand logo, same handling symbols, same fonts — but no parametric template.",
    "<b>Product line drawing</b>: Drawing the tiny product silhouette on the short panel is a surprisingly large time sink (5-10 minutes per SKU) and quality varies.",
    "<b>Approval round loops</b>: Back-and-forth emails with screenshots and mark-ups is slow and error-prone. No versioning.",
    "<b>Printer handoff</b>: .cdr files sometimes arrive at the printer with font substitution bugs, producing garbled output that has to be reprinted.",
]))

story.append(PageBreak())

# ── SECTION 3: Proposed Automation ────────────────────────────────────────
story.append(p("3. Proposed Automation", H1))
story.append(section_divider())

story.append(p("3.1 Target Workflow Overview", H2))
story.append(p(
    "The automated workflow replaces manual steps 1-8 of the current process with "
    "a pipeline of AI agents. Manual steps 9-11 (client approval, printer handoff) "
    "remain but are dramatically sped up by having the system generate approval "
    "PDFs and printer-ready SVGs automatically. The new workflow:"
))

automation_flow = [
    ("1. Document Intake", "User drags-and-drops PO, PI, protocol, warning labels, and checklist onto the web interface. Files are auto-classified by document type. Intake Agent tags and stores them."),
    ("2. Parallel Parsing", "Multiple specialised parsing agents work in parallel on the documents: PO Parser (LLM-based, handles any layout), PI Parser (template-mapped, fast), Protocol Analyzer (vision LLM), Warning Label Parser (vision + text), Checklist Rule Extractor (text + LLM)."),
    ("3. Data Fusion", "Fusion Agent joins PO and PI by item number, cross-validates (UPC matches, dimensions present, weights consistent), fills in missing fields from Importer Profile or asks the human."),
    ("4. Compliance Classification", "Rules Engine classifies each SKU against the Compliance Rules DB, producing a list of warning labels required for each item."),
    ("5. Line Drawing Generation", "Drawing Agent processes each product image (extracted from PO) and generates a clean line-art SVG using a diffusion model or traditional vectorisation."),
    ("6. Die-Cut Composition", "Composer Agent assembles each SKU's die-cut using the Importer Profile template + the fused order data + the generated line drawings + the applicable warning labels. Outputs actual-size SVG."),
    ("7. Approval PDF Generation", "Approval Agent generates client-facing PDF with red dimension annotations matching the importer's expected format."),
    ("8. Validation", "Validator Agent runs a post-generation sanity check: does every SVG have a brand logo, handling symbols, UPC barcode, and MADE IN INDIA text? Any missing -> flag for human."),
    ("9. Human Review", "Human receives a dashboard with all 8 generated files plus any flagged items. Approves, rejects, or requests fixes via the chat interface."),
    ("10. Client Approval", "Approved approval PDFs sent to client (via integrated email) with one-click approve/reject."),
    ("11. Printer Handoff", "Printer-ready SVG files are delivered to the carton printer via secure link or direct email. Each SVG is in mm units, ready to import into CorelDraw."),
]

story.append(multi_table(
    ["Phase", "Description"],
    [[x[0], x[1]] for x in automation_flow],
    col_widths=[CONTENT_W*0.28, CONTENT_W*0.72]
))

story.append(p("3.2 Before and After Metrics (Projected)", H2))
story.append(multi_table(
    ["Metric", "Current (Manual)", "Target (Automated)"],
    [
        ["Elapsed time per 10-SKU order", "2-5 business days", "30 min (incl. review)"],
        ["Designer hours", "4-7 hours", "10-15 minutes"],
        ["Merchandiser hours", "1.5-2 hours", "5 minutes"],
        ["Rework rounds", "1-3", "0-1"],
        ["Typo rate", "15-30% of SKUs", "< 1%"],
        ["Warning label miss rate", "~5% of applicable labels", "~0%"],
        ["Onboarding new importer", "N/A (tribal knowledge)", "2-4 hour structured session"],
        ["Auditability", "None", "Full log per decision"],
    ],
    col_widths=[CONTENT_W*0.36, CONTENT_W*0.32, CONTENT_W*0.32]
))

story.append(PageBreak())

# ── SECTION 4: Available Artifacts ────────────────────────────────────────
story.append(p("4. Available Artifacts", H1))
story.append(section_divider())

story.append(p(
    "The following artifacts have been identified and catalogued during discovery. "
    "These are the inputs the system must handle and the outputs it must produce. "
    "Each artifact has been classified by whether it's consumed during onboarding "
    "(processed once per importer) or during production (processed for every order)."
))

story.append(p("4.1 Input Artifacts (Provided by Importer)", H2))

story.append(p("4.1.1 Purchase Order (PO)", H3))
story.append(kv_table([
    ("Sample filename", "<font face='Courier'>NAKODA 24966 REVISED 01.12.26.pdf</font>"),
    ("Format", "PDF (most common), Excel, occasionally EDI"),
    ("Frequency", "Per order (production)"),
    ("Size", "Typically 5-50 pages, 2-10 MB"),
    ("Content", "Item numbers, UPCs/GTINs, product descriptions, product dimensions (L×W×H in inches), net weights, case quantities, total ordered quantity, shipping instructions, compliance notes, and embedded product photographs"),
    ("Variability", "<b>High</b>. Each importer uses their own format. Column layouts, field names, and groupings differ. Some are machine-generated (clean tables), others are scanned PDFs."),
    ("Extraction approach", "Adaptive LLM-based field extraction with schema validation and confidence scoring"),
    ("Critical fields", "item_no, upc, description, product_dimensions, case_qty, total_qty"),
]))

story.append(p("4.1.2 Proforma Invoice (PI)", H3))
story.append(kv_table([
    ("Sample filename", "<font face='Courier'>11. NACSBH290126.xlsx</font> (PO#25364, 8 items)"),
    ("Format", "Excel (.xlsx)"),
    ("Frequency", "Per order (production)"),
    ("Source", "<b>Prepared by exporter</b> — so format is stable within one exporting agency"),
    ("Content", "Carton outer dimensions (L×W×H), CBM per carton and total, inner/outer pack counts, exporter item codes, finish remarks, country of origin, HS codes"),
    ("Variability", "<b>Low</b>. Format is fixed per exporter; configured once, then consistent."),
    ("Extraction approach", "Template-mapped parser with explicit sheet name, header row, and column mappings stored in Exporter Profile"),
    ("Critical fields", "item_no, box_L, box_W, box_H, cbm, total_cartons, inner_pack"),
]))

story.append(p("4.1.3 Client Protocol", H3))
story.append(kv_table([
    ("Sample filename", "<font face='Courier'>SAGEBROOK HOME SPO PROCESS v3.pdf</font> (7 MB)"),
    ("Format", "PDF with annotated photographs (bilingual English + sometimes Hindi/Chinese)"),
    ("Frequency", "Onboarding (once per importer)"),
    ("Content", "Brand name treatment (font, letter-spacing, trademark), tagline style, handling symbol specs (which symbols, size in inches, placement), panel layout rules (what goes on long vs short sides), label placement instructions, packing standards, showroom-specific variants"),
    ("Extraction approach", "Multimodal Vision LLM analyzes each page; outputs structured Importer Profile JSON"),
    ("Key extractable facts", "brand.name, brand.font, brand.letter_spacing, tagline, handling_symbols.size (3.15\" × 1\"), panel_layout.long_side, panel_layout.short_side, barcode_placement"),
]))

story.append(p("4.1.4 Warning Label Specifications", H3))
story.append(kv_table([
    ("Sample filenames", "<font face='Courier'>SBH &amp; EV MASTER CARTON WARNING LABELS UPDATED.pdf, NON-FOOD USE, FDA WARNING.pdf</font>"),
    ("Format", "PDF — label designs with exact wording and visual specifications"),
    ("Frequency", "Onboarding (once per importer, re-synced when importer publishes updates)"),
    ("Content", "Label artwork, exact legal wording, dimensions (e.g., 4\" × 3\"), colors, font sizes, borders, placement instructions (carton / product / both), variants (product vs furniture for Prop 65; ceramic vs non-ceramic for FDA Non-Food)"),
    ("Extraction approach", "Vision LLM extracts label images as SVG templates; text LLM extracts wording verbatim (legal compliance requires word-for-word accuracy)"),
    ("Labels identified (Sagebrook)", "PROP 65 (2 variants), FDA Non-Food Use (2 variants), TSCA, Law Tag (3 lang), Flameless Candle, Candle Wax, Anti-tip (3 lang), Plastic Bag (EN/FR), Team Lift (28+ lbs), Heavy Caution (50+ lbs), Fragile, Carton Part Count, UL/CUL, Window Box Photo, Eco-Friendly Hangtag"),
]))

story.append(p("4.1.5 Document Checklist", H3))
story.append(kv_table([
    ("Sample filename", "<font face='Courier'>SBH PO DOCUMENTS CHECKLIST.pdf</font>"),
    ("Format", "PDF — structured checklist mapping product attributes to required labels"),
    ("Frequency", "Onboarding (once per importer)"),
    ("Content", "A master table of all possible labels, each with a trigger condition describing which products, materials, weights, or destinations require that label"),
    ("Extraction approach", "LLM-based extraction into structured rules stored in Compliance Rules DB"),
    ("Example rules parsed", "TSCA: material contains MDF/plywood AND destination USA; Law Tag: upholstered items incl. pillows AND destination USA; Prop 65 (furniture): furniture products AND destination CA; Team Lift: carton_weight > 28 lbs"),
]))

story.append(p("4.1.6 Carton Mockup References", H3))
story.append(kv_table([
    ("Sample filename", "<font face='Courier'>SAGEBROOK HOME 13 ITEM.pdf</font>"),
    ("Format", "PDF or image — shows die-cut layouts with red dimension annotations"),
    ("Frequency", "Onboarding (once) + as visual QA reference"),
    ("Content", "Actual expected die-cut layouts with red dimension markings, panel content, handling symbol placement. This is the ground truth the system's output must match visually."),
    ("Extraction approach", "Vision LLM analyzes each reference to extract: panel widths, panel heights, flap depth (3\"), handling symbol cluster size (1\" × 3.15\"), font sizes, content placement rules"),
    ("Discovered insights", "Barcode placement: long panel bottom-left, short panel bottom-right. Dimension markings use red color (~#d42f2f). Title format: 'ITEM_NO- L X W X H INCH'."),
]))

story.append(p("4.2 Output Artifacts (Produced by System)", H2))
story.append(p("4.2.1 Printer-Ready Die-Cut SVG", H3))
story.append(kv_table([
    ("Filename pattern", "<font face='Courier'>DieCut_{item_no}.svg</font>"),
    ("Format", "SVG 1.1 with embedded base64 images, mm units, xlink namespace for CorelDraw compatibility"),
    ("Size", "Actual size (1:1 scale). Example: 2052mm × 629mm for item 18236-08 (26.5×13.5×17\" box)."),
    ("Content", "Die-cut outline (black), fold lines (dashed), 4 panels with full content + top/bottom flaps, embedded brand logo image, embedded handling symbols image, UPC-A barcode (drawn as SVG rects), product line drawing, all required text"),
    ("Consumer", "Carton box printer imports into CorelDraw for plate preparation"),
    ("POC files delivered", "8 files for PO#25364: DieCut_v2_18236-08.svg, DieCut_v2_20655-01.svg, etc."),
]))

story.append(p("4.2.2 Client Approval PDF", H3))
story.append(kv_table([
    ("Filename pattern", "<font face='Courier'>Approval_{item_no}.pdf</font>"),
    ("Format", "PDF (landscape, ~1000x650 pts), not actual size (scaled to fit page)"),
    ("Content", "Title: 'ITEM_NO- L X W X H INCH'. Die-cut layout with 4 panels + flaps. RED dimension arrows showing panel widths, panel height, flap depth, total width, handling symbol area (1\" × 3.15\"). Full panel content. Footer: 'FOR CLIENT APPROVAL ONLY — NOT ACTUAL SIZE'"),
    ("Consumer", "Importer QA team reviews and approves/rejects"),
    ("POC files delivered", "8 files for PO#25364: Approval_18236-08.pdf, etc."),
]))

story.append(p("4.3 Proof-of-Concept Outputs Already Generated", H2))
story.append(p(
    "During this engagement we have already produced end-to-end outputs for "
    "PO#25364 (Sagebrook Home, 8 items) as a working demonstration. These "
    "files use the real extracted brand logo and real handling symbols from "
    "the client's protocol and warning label PDFs — not AI approximations. "
    "They validate the architecture described in this document."
))

poc_items = [
    ("18236-08", "15X12\" Paper Mache Vase w/ Handles, Taupe", "26.5×13.5×17\"", "300"),
    ("20655-01", "24\" Paper Mache Jug w/ Handles, White", "17×17×26.5\"", "500"),
    ("20656-03", "S/3 14/18/22\" Paper Mache Bowls, Taupe", "24×24×12.5\"", "300"),
    ("20657", "16\" Reclaimed Wood Riser w/ Handle, Brown", "28.5×18×20\"", "67"),
    ("20755-01", "12\" Fluted Paper Mache Bowl, Brown", "15×15×16\"", "150"),
    ("21496-02", "12X12\" Paper Mache Knobby Footed Bowl, Brown", "14×14×12\"", "200"),
    ("21496-04", "12X12\" Paper Mache Knobby Footed Bowl, Taupe", "14×14×12\"", "400"),
    ("21498-06", "26X15\" Paper Mache Handle Vase, Taupe", "17.5×17.5×28.5\"", "300"),
]
story.append(multi_table(
    ["Item #", "Description", "Carton Dims", "Cartons"],
    poc_items,
    col_widths=[CONTENT_W*0.14, CONTENT_W*0.52, CONTENT_W*0.20, CONTENT_W*0.14]
))

story.append(PageBreak())

# ── SECTION 5: System Architecture ────────────────────────────────────────
story.append(p("5. System Architecture &amp; Design", H1))
story.append(section_divider())

story.append(p("5.1 Architectural Principles", H2))
story.append(bullet_list([
    "<b>Fixed output, adaptive input</b>: Each importer has a deterministic template (fonts, layout, symbols). Inputs (POs, protocols) vary wildly. So rendering is template-driven; ingestion is AI-driven.",
    "<b>Agent specialisation</b>: Instead of one monolithic LLM call, we use specialised agents each with a focused prompt, limited tools, and deterministic validation. This improves reliability and auditability.",
    "<b>Human-in-the-loop as first-class citizen</b>: Humans are not a fallback — they are an explicit control point for ambiguity, missing data, and critical approvals. The system is designed to ask good questions and resume from interruption.",
    "<b>Deterministic where possible, AI where necessary</b>: Barcode generation, SVG composition, PDF rendering = deterministic code. Field extraction from unstructured PDF, image analysis, rule inference = LLM.",
    "<b>Event-driven orchestration</b>: Every step emits an event. State is persisted. Failures resume from checkpoint, not from scratch.",
    "<b>Multi-tenant from day one</b>: Exporter profiles and importer profiles are separate entities. One exporter can serve many importers; one importer can have many exporters.",
    "<b>Immutable artifact store</b>: All generated SVGs, PDFs, and intermediate JSON outputs are versioned and kept forever for audit and rework.",
]))

story.append(p("5.2 High-Level Architecture Diagram", H2))
story.append(p(
    "The system is organized in seven layers: Ingestion, Extraction, Fusion, "
    "Intelligence, Composition, Delivery, and Control (cross-cutting). Data "
    "flows top-to-bottom; the Control layer coordinates agents and mediates "
    "human interactions."
))

# Text-art diagram
architecture_text = """
+------------------------------------------------------------------+
|   LAYER 1: INGESTION                                             |
|   - Drag-and-drop UI / Email watcher / API endpoint              |
|   - Document classifier (PO / PI / Protocol / Warning / etc.)    |
|   - File storage (S3 / MinIO) + metadata in DB                   |
+---------------------------+--------------------------------------+
                            |
+---------------------------v--------------------------------------+
|   LAYER 2: EXTRACTION (parallel agents)                          |
|   - PO Parser Agent (vision LLM + structured output)             |
|   - PI Parser Agent (template-based openpyxl)                    |
|   - Protocol Analyzer Agent (vision LLM, onboarding only)        |
|   - Warning Label Parser Agent (vision + text LLM)               |
|   - Checklist Rule Extractor Agent (text LLM)                    |
|   - Product Image Processor (bg removal, quality scoring)        |
+---------------------------+--------------------------------------+
                            |
+---------------------------v--------------------------------------+
|   LAYER 3: DATA FUSION &amp; VALIDATION                              |
|   - Fusion Agent: PO + PI join by item_no                        |
|   - Schema validator (Pydantic models)                           |
|   - Missing field detector                                       |
|   - Cross-validation (UPC format, dimension sanity, CBM match)   |
|   - Human-in-the-loop trigger on ambiguity                       |
+---------------------------+--------------------------------------+
                            |
+---------------------------v--------------------------------------+
|   LAYER 4: INTELLIGENCE                                          |
|   - Compliance Rules Engine (rules DB + classifier)              |
|   - Line Drawing Agent (vectorisation / diffusion)               |
|   - Product Attribute Classifier (material, type, category)      |
+---------------------------+--------------------------------------+
                            |
+---------------------------v--------------------------------------+
|   LAYER 5: COMPOSITION                                           |
|   - Die-Cut Composer Agent (deterministic renderer)              |
|   - Approval PDF Composer Agent                                  |
|   - Warning Label Placement Agent                                |
|   - UPC-A Barcode Generator (deterministic)                      |
+---------------------------+--------------------------------------+
                            |
+---------------------------v--------------------------------------+
|   LAYER 6: DELIVERY                                              |
|   - Validator Agent (post-generation QA)                         |
|   - Human review dashboard                                       |
|   - Client email/portal delivery                                 |
|   - Printer handoff (secure link + SVG bundle)                   |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|   CROSS-CUTTING: CONTROL PLANE                                   |
|   - Orchestrator (state machine)                                 |
|   - Event bus (Kafka / Redis Streams)                            |
|   - Agent Memory (short-term: Redis; long-term: Postgres+pgvector)|
|   - Human-in-the-Loop chatbot (websocket)                        |
|   - Audit log (every agent call + every decision)                |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|   PERSISTENT DATA LAYER                                          |
|   - Postgres (orders, items, profiles, users, audit)             |
|   - Redis (sessions, short-term agent memory, locks)             |
|   - S3 / MinIO (PDFs, SVGs, images, generated artifacts)         |
|   - pgvector (embeddings of protocols, labels for retrieval)     |
+------------------------------------------------------------------+
"""
story.append(code_block(architecture_text))

story.append(p("5.3 Data Models (Core Schemas)", H2))
story.append(p(
    "Below are the Pydantic-style schemas that flow between layers. These "
    "should be implemented as Pydantic models in Python and mirrored as SQL "
    "tables in Postgres."
))

story.append(p("OrderItem — the unified per-SKU record after fusion", H4))
story.append(code_block('''class OrderItem(BaseModel):
    item_no: str                      # "18236-08"
    upc: str                          # "677478725232" (12-digit UPC-A)
    gtin: Optional[str]               # "60677478725234"
    description: str                  # raw PO description
    material: str                     # "Paper Mache" | "Wood" | "Ceramic" | ...
    finish: Optional[str]             # "Taupe"
    product_dims: Dimension           # product L x W x H in inches
    net_weight_lbs: Optional[float]
    case_qty: int
    total_qty: int
    total_cartons: int
    carton_dims: Dimension            # box L x W x H in inches
    carton_cbm: float
    inner_pack: int
    outer_pack: int
    country_of_origin: str = "India"
    product_images: List[str]         # S3 keys
    applicable_warnings: List[WarningLabel]  # populated by Rules Engine
    extraction_confidence: float
    fusion_issues: List[FusionIssue]  # fields missing / mismatched
'''))

story.append(p("ImporterProfile — the fixed template for an importer", H4))
story.append(code_block('''class ImporterProfile(BaseModel):
    importer_id: str                  # "sagebrook_home"
    name: str                         # "Sagebrook Home"
    brand: BrandRules                 # logo asset, font, letter-spacing, tagline
    panel_layout: PanelLayout         # what goes on long vs short sides
    handling_symbols: SymbolRules     # symbols, size, placement
    barcode_rules: BarcodeRules       # UPC-A, long=bottom-left, short=bottom-right
    dimension_annotations: DimRules   # red color, font, arrow style
    output_specs: OutputSpecs         # units=mm, stroke_w, flap_depth=3in
    compliance_rules: ComplianceRulesDB  # trigger rules for warning labels
    warning_label_templates: Dict[str, SVGTemplate]
    approval_pdf_style: PDFStyleSpec  # red color, font, layout scale
'''))

story.append(p("FusionIssue — surfaced to the Human-in-the-Loop chatbot", H4))
story.append(code_block('''class FusionIssue(BaseModel):
    item_no: str
    issue_type: Literal[
        "missing_upc", "missing_carton_dims", "ambiguous_material",
        "upc_format_invalid", "no_product_image", "dimension_mismatch",
        "missing_case_qty", "ambiguous_destination", "conflict_po_pi"
    ]
    severity: Literal["blocker", "warning", "info"]
    context: Dict[str, Any]           # what we saw in each document
    suggested_value: Optional[Any]    # agent's best guess
    question_for_human: str           # what the chatbot will ask
    resolution: Optional[Resolution]  # filled in once human answers
'''))

story.append(PageBreak())

# ── SECTION 6: AI Agents ──────────────────────────────────────────────────
story.append(p("6. AI Agents — Roles and Functions", H1))
story.append(section_divider())

story.append(p(
    "This section specifies each agent in detail: its role, inputs, outputs, "
    "tools it has access to, the LLM model it uses, and the skeleton of its "
    "prompt. A real implementation uses these specifications directly."
))

def agent_block(name, role, inputs, outputs, tools, model, prompt_sketch):
    story.append(p(name, H3))
    story.append(kv_table([
        ("Role", role),
        ("Inputs", inputs),
        ("Outputs", outputs),
        ("Tools", tools),
        ("Model", model),
    ]))
    story.append(p("<b>Prompt sketch:</b>", BODY))
    story.append(code_block(prompt_sketch))
    story.append(Spacer(1, 4))

agent_block(
    "6.1 Intake Agent",
    "Receives uploaded files, classifies each as PO / PI / Protocol / Warning / Checklist / Mockup / Image / Unknown. Routes to the right parser.",
    "List[UploadedFile] (filename, mime_type, first page text, first page image)",
    "List[ClassifiedDocument] with doc_type and confidence",
    "read_pdf_first_page, extract_filename_keywords, classify_with_llm",
    "GPT-4o-mini or Claude Haiku (fast, cheap; it's a classification task)",
    '''SYSTEM: You are a document classifier for an export labeling system.
Given a filename and the first page content, classify each file as:
  PO, PI, PROTOCOL, WARNING_LABELS, CHECKLIST, CARTON_MOCKUP,
  PRODUCT_IMAGE, REFERENCE_SHEET, UNKNOWN.
Return JSON: {doc_type, confidence, reasoning}.

USER: filename="SBH PO DOCUMENTS CHECKLIST.pdf"
first_page_text="SBH PO Documents Checklist... TSCA Warning..."
'''
)

agent_block(
    "6.2 PO Parser Agent",
    "Extracts the PO structured data regardless of the PO's layout.",
    "PO PDF or XLSX file (raw bytes + per-page images)",
    "PurchaseOrder schema JSON with items[] and per-field confidence",
    "ocr_page, extract_tables, extract_embedded_images, llm_structured_output",
    "Claude Sonnet 4.6 or GPT-4o (vision + long context, high quality)",
    '''SYSTEM: You are a purchase-order parser. Extract every line item.
For each item, return: item_no, upc (12-digit), gtin (14-digit if present),
description, product_dims {L,W,H,unit}, net_weight, case_qty, total_qty,
product_image_refs (which embedded image indexes belong to this SKU).

If a field is missing, set it to null and lower the confidence.
Flag ambiguities (e.g., two possible UPCs for one SKU) in notes[].

Return strict JSON matching the PurchaseOrder Pydantic schema.
'''
)

agent_block(
    "6.3 PI Parser Agent",
    "Reads Proforma Invoice Excel files using a template stored in the Exporter Profile. Purely mechanical, no LLM needed.",
    "PI XLSX + exporter_id (which template to use)",
    "ProformaInvoice schema JSON",
    "openpyxl_read_sheet, pandas_parse_table",
    "None (deterministic code)",
    '''# Pseudocode
template = exporter_profile.pi_template
sheet = wb[template.sheet_name]
for row in sheet.iter_rows(min_row=template.data_start_row):
    item = PIItem(
        item_no = row[template.col_item_no].value,
        box_L = row[template.col_box_L].value,
        box_W = row[template.col_box_W].value,
        box_H = row[template.col_box_H].value,
        total_cartons = row[template.col_total_cartons].value,
        cbm = row[template.col_cbm].value,
    )
'''
)

agent_block(
    "6.4 Protocol Analyzer Agent (Onboarding)",
    "Reads the importer's protocol PDF and produces the ImporterProfile. Runs ONCE per importer during onboarding.",
    "Protocol PDF (multi-page, annotated photographs)",
    "ImporterProfile partial (brand rules + panel layout + handling symbol rules + logo asset extracted)",
    "pdf_to_images, vision_llm, extract_embedded_logo, color_picker_from_image",
    "Claude Opus 4.6 or GPT-4o (multimodal, high reasoning)",
    '''SYSTEM: You are analyzing an export client's brand protocol.
For each page containing a carton mockup or brand treatment, extract:
1. Brand name, exact typography (font family guess, weight, letter-spacing)
2. Tagline text and style
3. Handling symbol requirements (which symbols, size in inches)
4. Panel layout: what content goes on long sides vs short sides
5. Barcode placement rules
6. Any callout text with specific requirements

Output strict JSON matching ImporterProfile schema. Cite page numbers for
each extracted rule so humans can verify.
'''
)

agent_block(
    "6.5 Warning Label Parser Agent (Onboarding)",
    "Extracts each warning label's exact text, dimensions, visual design, and variants from the warning labels PDF. Builds the warning label template library.",
    "Warning labels PDF (legal-grade content, must be extracted verbatim)",
    "Dict[label_id, WarningLabelTemplate] with SVG templates and exact wording",
    "pdf_to_images, ocr_with_layout, vision_llm, svg_generator",
    "Claude Opus 4.6 (strong OCR + extraction accuracy)",
    '''SYSTEM: You are extracting warning label specifications. Legal wording
MUST be extracted character-for-character. Do not paraphrase.

For each distinct label on each page:
1. Extract the exact warning text (verbatim)
2. Note variants (e.g., Prop 65 product vs furniture)
3. Extract visual specs: size (in inches), border style, colors (hex),
   font sizes, text alignment
4. Extract application instructions: printed on carton? stick-on label?
   permanent marking? hangtag? all 4 sides?
5. Reference the embedded artwork so the composer can reuse it
'''
)

agent_block(
    "6.6 Checklist Rule Extractor Agent (Onboarding)",
    "Parses the Document Checklist PDF into machine-readable rules that map product attributes to required warning labels.",
    "Checklist PDF",
    "ComplianceRulesDB (list of Rule objects with trigger conditions)",
    "pdf_extract_text, llm_structured_output",
    "Claude Sonnet 4.6 (text-heavy, rule extraction)",
    '''SYSTEM: You are reading an importer's Document Checklist. It contains
rules that map product attributes to required warning labels.

For each rule, output:
{
  label_id: str,         # unique id matching warning_label_templates
  label_name: str,       # human readable
  trigger: {             # a logical expression
     material_contains: [...],
     product_type_in: [...],
     destination_state_in: [...],
     carton_weight_gt: number,
     ...
  },
  placement: "carton" | "product" | "both" | "hangtag",
  min_font_size_mm: number?
}
'''
)

agent_block(
    "6.7 Product Image Processor Agent",
    "Extracts product photos from PO PDFs, matches them to SKUs by position, removes backgrounds, and scores quality.",
    "PO PDF + structured PO data (for SKU positions)",
    "Dict[item_no, List[ProcessedImage]]",
    "pdf_extract_images, remove_bg_ai, image_quality_score, match_by_position",
    "rembg (open source) or Segment Anything Model for bg removal; CLIP for quality scoring",
    '''# Pseudocode
for page in pdf.pages:
    images = page.extract_images()
    text_blocks = page.extract_text_blocks()
    for img in images:
        nearest_item = find_nearest_item_no(img.bbox, text_blocks)
        clean = remove_background(img.data)
        score = assess_quality(clean)
        store[nearest_item].append(ProcessedImage(clean, score))
'''
)

agent_block(
    "6.8 Fusion &amp; Validation Agent",
    "Joins PO and PI by item_no, validates fields, cross-checks UPC format, detects missing data, creates FusionIssues for human review.",
    "PurchaseOrder + ProformaInvoice + ImporterProfile",
    "List[OrderItem] with fusion_issues populated",
    "schema_validate, upc_checksum, llm_material_inference",
    "GPT-4o-mini for material inference; deterministic code for joins and validation",
    '''# Pseudocode flow
po_items = index_by(po.items, "item_no")
pi_items = index_by(pi.items, "item_no")
fused = []
for item_no in po_items.keys() | pi_items.keys():
    po = po_items.get(item_no)
    pi = pi_items.get(item_no)
    issues = []
    if not po: issues.append(missing_in_po(item_no))
    if not pi: issues.append(missing_in_pi(item_no))
    if po and not valid_upc(po.upc): issues.append(bad_upc(...))
    material = infer_material(po.description) if po else None
    fused.append(OrderItem(..., fusion_issues=issues))
return fused
'''
)

agent_block(
    "6.9 Compliance Rules Engine",
    "Classifies each SKU against the ComplianceRulesDB and returns the list of applicable warning labels.",
    "OrderItem (with material, type, dims, weight) + shipping destination + ComplianceRulesDB",
    "List[ApplicableWarning] with reasoning",
    "rule_engine_eval, llm_product_type_classifier",
    "Deterministic rule engine + GPT-4o-mini for product-type classification",
    '''# Deterministic matching
applicable = []
for rule in rules_db:
    if rule.trigger.evaluate(order_item):
        applicable.append(ApplicableWarning(
            label_id=rule.label_id,
            reason=rule.trigger.explain(order_item),
            placement=rule.placement,
        ))
return applicable
'''
)

agent_block(
    "6.10 Line Drawing Agent",
    "Converts a cleaned product photo into a minimal black-and-white SVG line drawing suitable for the short-side panel.",
    "ProcessedImage (bg-removed PNG, ~200×200 px)",
    "SVG line drawing (200×200 viewbox, stroke-only paths)",
    "edge_detection (OpenCV Canny), vectorize (potrace), or stable_diffusion_img2img line-art, or GPT-image-line-art",
    "Potrace (open source) for clean silhouettes; Stable Diffusion with ControlNet (edge) for richer line art when silhouette not enough",
    '''# Two-pass pipeline:
# 1. Try potrace (fast, deterministic, works for clean silhouettes)
mask = get_silhouette(image)
svg = potrace(mask, opttolerance=0.5, turdsize=2)
if quality_score(svg) < 0.7:
    # 2. Fall back to diffusion-based line art
    svg = sd_controlnet_lineart(image, prompt="product outline, minimalist")
'''
)

agent_block(
    "6.11 Die-Cut Composer Agent",
    "Assembles the actual-size die-cut SVG for a single SKU. Purely deterministic given the inputs — no LLM.",
    "OrderItem + ImporterProfile + applicable_warnings + line_drawing_svg",
    "DieCutSVG (actual-size, mm units, embedded base64 assets)",
    "svg_builder, base64_encoder, upc_barcode_generator",
    "None (deterministic Python)",
    '''# Deterministic SVG assembly (see POC: gen_diecuts_v2.py)
def generate_diecut(item, profile):
    L, W, H = item.carton_dims.to_mm()
    total_w = 2*L + 2*W
    total_h = FLAP + H + FLAP
    svg = SVGCanvas(total_w, total_h, unit="mm")
    svg.add_cut_line(...)
    svg.add_fold_lines(...)
    for panel in ["long1", "short1", "long2", "short2"]:
        svg.add_panel(profile.panel_layout[panel], item)
        svg.add_embedded_image(profile.brand.logo, ...)
        svg.add_embedded_image(profile.handling_symbols.image, ...)
        svg.add_upc_a_barcode(item.upc, ...)
        svg.add_product_drawing(line_drawing_svg, ...)
    return svg.render()
'''
)

agent_block(
    "6.12 Approval PDF Composer Agent",
    "Generates the client approval PDF with red dimension annotations, matching the importer's expected format.",
    "OrderItem + ImporterProfile",
    "Approval PDF file",
    "reportlab canvas, red arrow drawer, dimension label writer",
    "None (deterministic Python)",
    '''# See POC: gen_approval_pdfs.py
c = canvas.Canvas(path, pagesize=(page_w, page_h))
draw_title(c, f"{item.item_no}-  {L}X{W}X{H} INCH")
draw_diecut_layout_scaled(c, item, scale)
draw_red_dimension_arrows(c, panels)
draw_handling_symbols_with_size_labels(c)
draw_panel_content(c, item, profile)
c.save()
'''
)

agent_block(
    "6.13 Validator Agent",
    "Post-generation QA: checks every generated SVG and PDF for completeness. Flags any missing element.",
    "Generated SVG + PDF files + expected_ImporterProfile",
    "ValidationReport: pass | fail + list of issues",
    "svg_parser, image_present_check, text_present_check, barcode_decode_check",
    "Deterministic code + small LLM for visual spot-checks",
    '''checks = [
    check_svg_has_element(svg, "image", count=8),   # 4 logos + 4 symbol imgs
    check_svg_has_text(svg, item.item_no),
    check_svg_has_text(svg, "MADE IN INDIA"),
    check_barcode_decodes_to(svg, item.upc),
    check_all_panels_have_handling_symbols(svg),
    check_dimension_labels_present(pdf),
]
return ValidationReport(pass=all(c.ok for c in checks), issues=[...])
'''
)

agent_block(
    "6.14 Human-in-the-Loop Conversational Agent",
    "When any upstream agent raises a FusionIssue, missing document, or needs a critical decision, this agent opens an interactive chat with the human and collects the needed answers until the task is unblocked.",
    "OrchestratorContext + List[BlockingQuestion]",
    "Resolutions that unblock the stalled task",
    "chat_websocket, file_upload_request, show_options, context_retrieval",
    "Claude Sonnet 4.6 (for natural conversation + context awareness)",
    '''SYSTEM: You are the human liaison for an export labeling pipeline.
The pipeline is paused because of blocking issues. Your job is to:
1. Explain to the human what went wrong in plain language
2. Ask ONE question at a time (never a wall of questions)
3. Accept partial answers and follow up
4. Validate answers before closing the thread
5. When all blockers are resolved, signal the orchestrator to resume

Context: {fusion_issues}
Importer: {importer_name}
Order: {po_number}
'''
)

story.append(PageBreak())

# ── SECTION 7: Orchestration ──────────────────────────────────────────────
story.append(p("7. Orchestration &amp; Feedback Loops", H1))
story.append(section_divider())

story.append(p("7.1 Orchestrator State Machine", H2))
story.append(p(
    "The Orchestrator is the heart of the system. It is a finite state machine "
    "that drives each order through its lifecycle, persists state after every "
    "step, and can resume from a checkpoint after a crash or a human-in-the-loop "
    "pause. Recommended implementation: <b>LangGraph</b>, <b>Temporal</b>, or a "
    "custom state machine on Redis."
))

states = [
    ("CREATED", "Order created by user upload. Files stored. Waiting for intake."),
    ("INTAKE", "Intake Agent classifying documents. Emits DocumentClassified events."),
    ("EXTRACTING", "Parser agents running in parallel. Emits ExtractionCompleted per document."),
    ("FUSING", "Fusion Agent joining PO + PI. May raise FusionIssues."),
    ("HUMAN_BLOCKED", "One or more blocking issues. HiTL chatbot engaged. Waiting for human responses."),
    ("VALIDATING_COMPLIANCE", "Rules engine classifying each SKU. Applicable warnings computed."),
    ("GENERATING_DRAWINGS", "Line Drawing Agent running per SKU."),
    ("COMPOSING", "Die-Cut Composer + Approval PDF Composer running per SKU."),
    ("VALIDATING_OUTPUT", "Validator Agent checking all outputs. Failures loop back to COMPOSING."),
    ("REVIEW", "Human reviewing in dashboard. Approves / rejects / requests fix."),
    ("DELIVERED", "Sent to client and/or printer. Terminal state."),
    ("FAILED", "Unrecoverable error. Human must investigate."),
]
story.append(multi_table(
    ["State", "Description"],
    states,
    col_widths=[CONTENT_W*0.28, CONTENT_W*0.72]
))

story.append(p("7.2 Transitions and Feedback Loops", H2))
story.append(p(
    "Transitions are triggered by events. Every transition is logged. Loops exist "
    "where agents can retry or re-run sub-tasks based on validator feedback or "
    "human corrections:"
))

story.append(bullet_list([
    "<b>Extraction retry loop</b>: If PO Parser returns low confidence (&lt; 0.70 on any critical field), re-run with a different model (e.g., swap Haiku -&gt; Sonnet) before raising a HiTL issue.",
    "<b>Validation loop</b>: If Validator Agent fails a generated SVG (e.g., logo missing), the Composer Agent retries with explicit instruction; after 3 failures, escalates to Human.",
    "<b>Human correction loop</b>: When a human rejects a generated output in the review dashboard, the rejection reason flows back to the Composer as a targeted fix instruction (e.g., 'description line was wrapped incorrectly'). The Composer re-renders just that SKU and re-submits.",
    "<b>Compliance sanity loop</b>: If the Rules Engine returns zero warnings for a material that usually requires one (e.g., ceramic with no FDA Non-Food warning), Validator flags this as a suspicious pattern and routes to HiTL.",
    "<b>Learning loop</b>: Every HiTL resolution is stored. If the system sees the same blocking issue 3+ times, a 'Profile Update Suggestion' is raised for the Exporter/Importer Profile maintainer.",
]))

story.append(p("7.3 Event Schema", H2))
story.append(code_block('''class Event(BaseModel):
    event_id: UUID
    order_id: UUID
    timestamp: datetime
    source_agent: str                 # "po_parser" | "fusion" | "composer" | ...
    type: Literal[
        "order.created", "document.classified", "extraction.started",
        "extraction.completed", "extraction.failed",
        "fusion.issue_raised", "hitl.question_asked", "hitl.answer_received",
        "composition.started", "composition.completed",
        "validation.passed", "validation.failed",
        "review.approved", "review.rejected", "delivery.sent",
    ]
    payload: Dict[str, Any]
    caused_by: Optional[UUID]         # parent event
'''))

story.append(p("7.4 Agent Memory Model", H2))
story.append(p(
    "Agents have three tiers of memory:"
))
story.append(bullet_list([
    "<b>Conversation memory (short-term)</b>: The current order's context. Stored in Redis. TTL: 7 days. Used within a single order lifecycle.",
    "<b>Profile memory (long-term, per tenant)</b>: The ExporterProfile and ImporterProfile. Stored in Postgres. Updated during onboarding and via HiTL learning.",
    "<b>Semantic memory (vector)</b>: Embeddings of all past POs, protocols, and warning labels. Stored in pgvector. Used for 'have we seen something like this before?' retrieval during ambiguous extractions.",
    "<b>Audit memory (append-only)</b>: Every agent call, every prompt, every response, every tool invocation. Stored in an append-only Postgres table. Never deleted. Used for debugging and compliance.",
]))

story.append(PageBreak())

# ── SECTION 8: Human-in-the-Loop ──────────────────────────────────────────
story.append(p("8. Human-in-the-Loop Interactive Chatbot", H1))
story.append(section_divider())

story.append(p(
    "The Human-in-the-Loop (HiTL) system is a two-way interactive chat that engages "
    "the human operator whenever the pipeline encounters an issue it cannot "
    "resolve autonomously. It is <b>not</b> a 'drop a form on the screen and wait' "
    "pattern — it is a conversational agent that explains the problem, asks "
    "questions one at a time, accepts partial answers, and only resumes the "
    "pipeline when all blocking issues are resolved."
))

story.append(p("8.1 When HiTL is Triggered", H2))
story.append(bullet_list([
    "<b>Missing document</b>: User uploaded a PO and PI but no protocol — system cannot render without brand rules.",
    "<b>Missing critical field</b>: Item has no UPC, or UPC is not 12 digits, or checksum is wrong.",
    "<b>Ambiguous extraction</b>: Two possible UPCs found for one SKU (e.g., one on the product line, one on a separate UPC list).",
    "<b>Material inference uncertain</b>: Description says 'ceramic coated paper mache' — is the FDA Non-Food Ceramic rule applicable or the non-ceramic variant?",
    "<b>Destination unknown</b>: PO doesn't specify California or USA clearly; Prop 65 / TSCA applicability unknown.",
    "<b>Dimension mismatch</b>: PO says box is 26.5×13.5×17\" but PI says 27×14×17\" — which is authoritative?",
    "<b>Weight missing</b>: Carton weight field blank — cannot determine if Team Lift label applies (28+ lbs).",
    "<b>Unknown importer</b>: The PO is from an importer not in the Importer Profile DB — requires onboarding first.",
    "<b>Low-confidence line drawing</b>: No usable product image found, or extracted image too low-res.",
    "<b>New warning label variant</b>: Encountered a warning rule not in the Compliance Rules DB.",
    "<b>Client approval rejection with vague reason</b>: Client says 'wrong layout' — HiTL asks for clarification.",
]))

story.append(p("8.2 Conversation Design Principles", H2))
story.append(bullet_list([
    "<b>One question at a time</b>. Never show a wall of fields. A progress indicator shows how many more questions are pending.",
    "<b>Natural language + actionable options</b>. If there are finite choices, present them as clickable chips, but still accept free text.",
    "<b>Context-aware</b>. The agent references the specific item, PO number, and what it already knows (e.g., 'For item 18236-08, I found two possible UPCs...').",
    "<b>Fail-safe escape</b>. The human can always say 'I don't know — skip this SKU' and the pipeline excludes that item rather than hanging.",
    "<b>Partial answers allowed</b>. If the human answers 2 out of 5 questions and says 'I'll ask my colleague about the rest', the session is saved and resumes when they return.",
    "<b>Confirmation before resume</b>. Before unblocking the pipeline, the agent summarises all resolutions and asks 'Is this correct?'.",
    "<b>Learn from answers</b>. If the same question is asked 3+ times with the same answer, the system proposes updating the Profile so it doesn't ask again.",
]))

story.append(p("8.3 Example HiTL Conversation", H2))
story.append(p(
    "Below is a complete example conversation for a realistic blocking scenario: "
    "the PO has a missing UPC, an ambiguous material, and the carton weight is "
    "blank (which affects the Team Lift warning label decision)."
))

story.append(chat_bubble("System", "Pipeline paused at FUSING state. 3 blocking issues detected for order PO#25999 (Sagebrook Home).", role='system'))

story.append(chat_bubble("Nakoda-Agent", (
    "Hi! I'm reviewing PO#25999 from Sagebrook Home. I hit a few items where I need your help before I "
    "can generate the die-cut layouts. I'll go one at a time. Sound good?"
), role='agent'))

story.append(chat_bubble("Human", "yes go ahead", role='human'))

story.append(chat_bubble("Nakoda-Agent", (
    "Great. First issue — <b>Item 22104-03 (18\" Ceramic Vase, White)</b>. The PO lists the UPC but it's only "
    "11 digits: <font face='Courier'>67747867432</font>. UPC-A requires exactly 12 digits including the check digit. "
    "Can you confirm the correct UPC? I can suggest <font face='Courier'>677478674328</font> by computing the standard check digit, "
    "but I want you to verify with your client data."
), role='agent'))

story.append(chat_bubble("Human", "let me check... 677478674328 is correct", role='human'))

story.append(chat_bubble("Nakoda-Agent", (
    "Thanks, that matches. [Resolved: item 22104-03 UPC = 677478674328] "
    "<br/><br/>Next — <b>Item 22200-01 (12\" Coated Bowl, Taupe)</b>. The description says "
    "<i>'ceramic coated paper mache bowl'</i>. For the FDA Non-Food Use warning, I need to know: "
    "is the <b>food-contact surface ceramic</b> (in which case both permanent marking AND sticker apply, with the "
    "ceramic-variant wording), or is it paper mache with a ceramic look (non-ceramic variant applies)? "
    "This affects the legal wording printed on the label."
), role='agent'))

story.append(chat_bubble("Human", "paper mache body, only surface coating is ceramic-look", role='human'))

story.append(chat_bubble("Nakoda-Agent", (
    "Understood. I'll classify this as non-ceramic for FDA purposes, so the label text will be "
    "<i>\"For Decoration Only. Not Intended for Food Use.\"</i> and only a sticker is required. "
    "<br/><br/>One follow-up — since you mentioned this a couple of times now (5 items across the last 3 orders have had "
    "the same 'ceramic coated paper mache' description), would you like me to add a rule: <b>if material='paper mache' AND finish contains 'ceramic' "
    "-> classify as non-ceramic for FDA</b>? This will save you from answering this every time."
), role='agent'))

story.append(chat_bubble("Human", "yes add the rule", role='human'))

story.append(chat_bubble("System", "Profile update: rule added to Sagebrook Home Compliance Rules DB.", role='system'))

story.append(chat_bubble("Nakoda-Agent", (
    "Done. Rule saved. [Resolved: item 22200-01 FDA = non-ceramic variant]"
    "<br/><br/>Last one — <b>Item 22300-02 (S/3 Wood Riser, Brown)</b>. The PI has no carton weight value (blank cell). "
    "To determine whether the <b>Team Lift</b> warning label applies (required if carton &gt; 28 lbs) or the <b>Heavy Object "
    "Caution</b> (&gt; 50 lbs), I need a carton weight estimate. Do you have the actual weight, or should I use a "
    "calculated estimate? For reference: box size is 28\"×18\"×20\" with 12 pcs per carton; similar wood risers in your "
    "history average around 34 lbs per carton."
), role='agent'))

story.append(chat_bubble("Human", "use 34 lbs", role='human'))

story.append(chat_bubble("Nakoda-Agent", (
    "Got it. 34 lbs &gt; 28 lbs, so the Team Lift warning will be applied. Heavy Object Caution (&gt; 50 lbs) is not "
    "needed. [Resolved: item 22300-02 carton_weight = 34 lbs, team_lift applies]"
    "<br/><br/><b>Summary of resolutions:</b>"
    "<br/>1. item 22104-03 UPC set to 677478674328"
    "<br/>2. item 22200-01 FDA classification = non-ceramic (rule added to profile)"
    "<br/>3. item 22300-02 carton_weight = 34 lbs, Team Lift warning applied"
    "<br/><br/>Shall I resume generation with these values?"
), role='agent'))

story.append(chat_bubble("Human", "yes resume", role='human'))

story.append(chat_bubble("System", "Pipeline resuming at FUSING -&gt; VALIDATING_COMPLIANCE. All 3 blockers resolved.", role='system'))

story.append(p("8.4 HiTL Data Model", H2))
story.append(code_block('''class HiTLSession(BaseModel):
    session_id: UUID
    order_id: UUID
    state: Literal["active", "waiting_human", "resolved", "abandoned"]
    started_at: datetime
    last_activity_at: datetime
    blocking_issues: List[FusionIssue]
    conversation: List[Message]      # append-only
    resolutions: Dict[str, Any]      # keyed by issue_id
    profile_update_suggestions: List[ProfileUpdate]

class Message(BaseModel):
    role: Literal["system", "agent", "human"]
    content: str
    timestamp: datetime
    references: List[str]            # item_no or issue_id being discussed
'''))

story.append(p("8.5 HiTL UI Specification", H2))
story.append(p(
    "The HiTL chat is a websocket-based interface embedded in the main dashboard. "
    "When an order enters HUMAN_BLOCKED state, the user sees a notification and a "
    "'Resolve blockers' button that opens the chat panel."
))
story.append(bullet_list([
    "<b>Message bubbles</b>: System, Agent, and Human messages are visually distinct.",
    "<b>Inline attachments</b>: Agent can render product images, SVG previews, and file upload widgets inside the chat for the human.",
    "<b>Progress bar</b>: 'Blockers remaining: 2 of 3' at the top of the chat so the user knows how much is left.",
    "<b>Save and resume</b>: If the user closes the tab, the session persists. Re-opening resumes from the last message.",
    "<b>Typing indicator</b>: When the agent is thinking, a subtle animation is shown.",
    "<b>Slash commands</b>: <font face='Courier'>/skip-item 22300-02</font>, <font face='Courier'>/show-original-po</font>, <font face='Courier'>/escalate</font> for power users.",
    "<b>Async handoff</b>: If the user says 'I need to ask my client', the session can be tagged and notifications sent when external info arrives.",
]))

story.append(PageBreak())

# ── SECTION 9: Technology Stack ───────────────────────────────────────────
story.append(p("9. Technology Stack", H1))
story.append(section_divider())

story.append(p(
    "This stack has been chosen for: (a) fast iteration, (b) low ops burden for a "
    "small team, (c) strong AI/LLM ecosystem support in Python, and (d) battle-tested "
    "libraries for PDF, SVG, Excel, and image processing. All components are open "
    "source or have generous free tiers."
))

story.append(p("9.1 Backend", H2))
story.append(multi_table(
    ["Component", "Choice", "Rationale"],
    [
        ["Language", "Python 3.12", "Best ecosystem for LLMs, PDF, image, SVG"],
        ["Web framework", "FastAPI", "Async, Pydantic-native, auto OpenAPI docs, websocket support"],
        ["Task queue", "Celery + Redis (or Temporal)", "Long-running agent workflows, retries, scheduling"],
        ["Orchestrator", "LangGraph (or Temporal workflows)", "State machine with checkpointing, built-in for LLM agents"],
        ["LLM abstraction", "LiteLLM or LangChain", "Swap between Claude/GPT/Gemini without code change"],
        ["Auth", "FastAPI-Users + JWT", "Multi-tenant RBAC out of the box"],
        ["API docs", "FastAPI auto-generated OpenAPI", "Free from the framework"],
    ],
    col_widths=[CONTENT_W*0.22, CONTENT_W*0.33, CONTENT_W*0.45]
))

story.append(p("9.2 AI &amp; ML Models", H2))
story.append(multi_table(
    ["Task", "Model", "Notes"],
    [
        ["PO extraction (vision)", "Claude Sonnet 4.6 or GPT-4o", "Strong at reading complex PDF layouts"],
        ["Protocol analysis (vision, onboarding)", "Claude Opus 4.6", "Highest accuracy, runs once per importer"],
        ["Warning label extraction (OCR + verbatim)", "Claude Opus 4.6", "Legal wording must be exact"],
        ["Document classification (intake)", "Claude Haiku 4.5 or GPT-4o-mini", "Fast, cheap, classification-grade"],
        ["Material/product-type inference", "GPT-4o-mini", "Light classification task"],
        ["HiTL conversational agent", "Claude Sonnet 4.6", "Natural conversation + tool use"],
        ["Line-drawing generation (primary)", "Potrace + OpenCV", "Deterministic, fast, free"],
        ["Line-drawing generation (fallback)", "Stable Diffusion + ControlNet (lineart)", "For complex products needing AI interpretation"],
        ["Background removal", "rembg (u2net) or Segment Anything", "Open source, GPU or CPU"],
        ["Embeddings for vector memory", "text-embedding-3-small (OpenAI) or BGE-M3 (open)", "For semantic retrieval of past protocols"],
    ],
    col_widths=[CONTENT_W*0.30, CONTENT_W*0.30, CONTENT_W*0.40]
))

story.append(p("9.3 Document Processing Libraries", H2))
story.append(multi_table(
    ["Library", "Purpose"],
    [
        ["pymupdf (fitz)", "PDF text + image extraction, page rendering to image for vision LLMs"],
        ["pdfplumber", "PDF table extraction (for PO tabular data)"],
        ["openpyxl + pandas", "Excel parsing (PI template-mapped reads)"],
        ["reportlab", "Generating approval PDFs (used in POC)"],
        ["svgwrite", "Programmatic SVG generation (alternative to string templates)"],
        ["Pillow (PIL)", "Image manipulation, format conversion"],
        ["opencv-python", "Edge detection, contour extraction for line drawings"],
        ["rembg", "Background removal from product photos"],
        ["cairosvg", "SVG -&gt; PNG conversion for previews"],
        ["python-barcode", "UPC-A / EAN barcode validation (we generate SVG manually)"],
    ],
    col_widths=[CONTENT_W*0.28, CONTENT_W*0.72]
))

story.append(p("9.4 Data Layer", H2))
story.append(multi_table(
    ["Component", "Choice", "Rationale"],
    [
        ["Relational DB", "PostgreSQL 16", "ACID, JSONB for flexible schemas, pgvector extension"],
        ["Vector DB", "pgvector (same Postgres)", "Avoid separate vector DB infrastructure"],
        ["Cache / session store", "Redis 7", "Agent short-term memory, websocket sessions, Celery broker"],
        ["Blob storage", "MinIO (self-hosted) or AWS S3", "All PDFs, SVGs, intermediate images"],
        ["Full-text search", "Postgres tsvector (or Meilisearch)", "Search across past orders, POs, protocols"],
        ["Audit log", "Postgres append-only table + S3 cold storage", "Never delete; compliance trail"],
    ],
    col_widths=[CONTENT_W*0.22, CONTENT_W*0.33, CONTENT_W*0.45]
))

story.append(p("9.5 Frontend", H2))
story.append(multi_table(
    ["Component", "Choice", "Rationale"],
    [
        ["Framework", "React 18 + Vite + TypeScript", "Modern, fast builds, strong ecosystem"],
        ["UI library", "Tailwind CSS + shadcn/ui", "Fast prototyping, consistent design"],
        ["State management", "Zustand + TanStack Query", "Simple state + server cache"],
        ["Websocket client", "native WebSocket API or socket.io-client", "For HiTL chat"],
        ["PDF viewer", "react-pdf", "Preview generated approval PDFs inline"],
        ["SVG viewer", "native <svg> + pan/zoom lib", "Preview generated die-cuts inline"],
        ["Chat UI", "custom build on shadcn Dialog + ScrollArea", "HiTL chat panel"],
    ],
    col_widths=[CONTENT_W*0.22, CONTENT_W*0.33, CONTENT_W*0.45]
))

story.append(p("9.6 Infrastructure &amp; DevOps", H2))
story.append(multi_table(
    ["Component", "Choice"],
    [
        ["Containers", "Docker + Docker Compose (dev) / Kubernetes (prod)"],
        ["CI/CD", "GitHub Actions"],
        ["Secrets management", "AWS Secrets Manager or Doppler"],
        ["Observability", "OpenTelemetry + Grafana Tempo (traces) + Loki (logs) + Prometheus (metrics)"],
        ["Error tracking", "Sentry"],
        ["LLM cost + latency tracking", "Langfuse or Helicone"],
        ["Deployment target", "AWS (ECS Fargate + RDS) or Hetzner (single VPS for small scale)"],
    ],
    col_widths=[CONTENT_W*0.28, CONTENT_W*0.72]
))

story.append(PageBreak())

# ── SECTION 10: Database Schema ───────────────────────────────────────────
story.append(p("10. Database Schema (Postgres)", H1))
story.append(section_divider())

story.append(p(
    "The core tables below are sufficient to run the system. JSONB columns are used "
    "for flexible schemas that don't warrant normalised tables (e.g., ImporterProfile)."
))

story.append(p("10.1 Core Tables", H2))
story.append(code_block('''-- Tenants
CREATE TABLE exporters (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(64) DEFAULT 'India',
    pi_template JSONB NOT NULL,       -- sheet name, header row, col mappings
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE importers (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(64),
    profile JSONB NOT NULL,           -- full ImporterProfile
    onboarded_at TIMESTAMPTZ DEFAULT now(),
    last_synced_at TIMESTAMPTZ
);

-- Users (multi-tenant RBAC)
CREATE TABLE users (
    id UUID PRIMARY KEY,
    exporter_id UUID REFERENCES exporters(id),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255),
    role VARCHAR(32) NOT NULL,        -- admin, merchandiser, designer, qa
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Orders
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    exporter_id UUID NOT NULL REFERENCES exporters(id),
    importer_id UUID NOT NULL REFERENCES importers(id),
    po_number VARCHAR(64) NOT NULL,
    state VARCHAR(32) NOT NULL,       -- state machine states
    created_at TIMESTAMPTZ DEFAULT now(),
    created_by UUID REFERENCES users(id),
    completed_at TIMESTAMPTZ,
    UNIQUE (exporter_id, po_number)
);

CREATE INDEX idx_orders_state ON orders(state);

-- Documents uploaded for an order
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    doc_type VARCHAR(32) NOT NULL,    -- PO, PI, PROTOCOL, WARNING, CHECKLIST, IMAGE
    original_filename VARCHAR(512),
    storage_key VARCHAR(512) NOT NULL, -- S3 / MinIO path
    mime_type VARCHAR(128),
    size_bytes BIGINT,
    classification_confidence FLOAT,
    uploaded_at TIMESTAMPTZ DEFAULT now()
);

-- SKUs (after fusion)
CREATE TABLE order_items (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_no VARCHAR(64) NOT NULL,
    upc VARCHAR(14),
    gtin VARCHAR(14),
    description TEXT,
    material VARCHAR(128),
    finish VARCHAR(128),
    product_dims JSONB,
    carton_dims JSONB,
    case_qty INT,
    total_qty INT,
    total_cartons INT,
    carton_weight_lbs FLOAT,
    applicable_warnings JSONB,        -- list of ApplicableWarning
    extraction_confidence FLOAT,
    fusion_issues JSONB,              -- resolved or open issues
    UNIQUE (order_id, item_no)
);

-- Generated output files
CREATE TABLE artifacts (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    item_id UUID REFERENCES order_items(id),
    artifact_type VARCHAR(32),        -- diecut_svg, approval_pdf, line_drawing_svg
    storage_key VARCHAR(512) NOT NULL,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    created_by_agent VARCHAR(64)
);

-- Compliance rules (per importer)
CREATE TABLE compliance_rules (
    id UUID PRIMARY KEY,
    importer_id UUID NOT NULL REFERENCES importers(id),
    label_id VARCHAR(64) NOT NULL,    -- "prop65_product", "fda_nonfood_ceramic"
    label_name VARCHAR(255),
    trigger JSONB NOT NULL,           -- structured condition
    placement VARCHAR(32),
    warning_text TEXT,                -- verbatim legal text
    label_svg_key VARCHAR(512),       -- S3 path to SVG template
    min_font_size_mm FLOAT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (importer_id, label_id)
);

-- HiTL chat sessions
CREATE TABLE hitl_sessions (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    state VARCHAR(32) NOT NULL,       -- active, waiting_human, resolved, abandoned
    started_at TIMESTAMPTZ DEFAULT now(),
    last_activity_at TIMESTAMPTZ,
    blocking_issues JSONB,
    resolutions JSONB
);

CREATE TABLE hitl_messages (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES hitl_sessions(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,        -- system, agent, human
    content TEXT NOT NULL,
    references JSONB,                 -- item_no or issue_id
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Audit log (append only)
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    order_id UUID,
    event_id UUID,
    source_agent VARCHAR(64),
    event_type VARCHAR(64),
    payload JSONB,
    caused_by UUID,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_audit_order ON audit_log(order_id);
CREATE INDEX idx_audit_event_type ON audit_log(event_type);

-- Vector memory
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id),
    chunk_text TEXT,
    embedding vector(1536),
    metadata JSONB
);

CREATE INDEX idx_embeddings_hnsw ON document_embeddings
    USING hnsw (embedding vector_cosine_ops);
'''))

story.append(PageBreak())

# ── SECTION 11: API Design ────────────────────────────────────────────────
story.append(p("11. REST / WebSocket API Design", H1))
story.append(section_divider())

story.append(p(
    "The system exposes a FastAPI backend with REST endpoints for resource CRUD "
    "and WebSocket endpoints for the HiTL chat. Auth uses JWT bearer tokens with "
    "tenant scoping."
))

story.append(p("11.1 REST Endpoints", H2))
story.append(multi_table(
    ["Method", "Path", "Purpose"],
    [
        ["POST", "/api/v1/auth/login", "Authenticate, returns JWT"],
        ["POST", "/api/v1/orders", "Create a new order (uploads files via multipart)"],
        ["GET", "/api/v1/orders", "List orders for the current exporter, with filters"],
        ["GET", "/api/v1/orders/{id}", "Full order detail including items, artifacts, current state"],
        ["POST", "/api/v1/orders/{id}/documents", "Upload additional documents"],
        ["POST", "/api/v1/orders/{id}/start", "Trigger the extraction pipeline"],
        ["GET", "/api/v1/orders/{id}/state", "Get current orchestrator state (for polling, or use SSE)"],
        ["GET", "/api/v1/orders/{id}/items", "List parsed/fused items"],
        ["PATCH", "/api/v1/orders/{id}/items/{item_id}", "Override extracted values (audited)"],
        ["GET", "/api/v1/orders/{id}/artifacts", "List all generated files"],
        ["GET", "/api/v1/artifacts/{id}/download", "Stream a generated SVG/PDF"],
        ["POST", "/api/v1/orders/{id}/approve", "Human approves outputs, moves to DELIVERED"],
        ["POST", "/api/v1/orders/{id}/reject", "Human rejects, with reason, loops back to COMPOSING"],
        ["POST", "/api/v1/orders/{id}/send-to-client", "Email approval PDFs to importer"],
        ["POST", "/api/v1/orders/{id}/send-to-printer", "Send die-cut SVGs to carton printer"],
        ["POST", "/api/v1/importers", "Create a new importer profile (triggers onboarding flow)"],
        ["POST", "/api/v1/importers/{id}/onboard", "Upload protocol/warning/checklist for extraction"],
        ["GET", "/api/v1/importers/{id}/profile", "Get the full importer profile"],
        ["PATCH", "/api/v1/importers/{id}/profile", "Edit profile (audited)"],
        ["GET", "/api/v1/audit-log?order_id=...", "Query audit log"],
    ],
    col_widths=[CONTENT_W*0.10, CONTENT_W*0.38, CONTENT_W*0.52]
))

story.append(p("11.2 WebSocket Endpoints", H2))
story.append(multi_table(
    ["Path", "Purpose"],
    [
        ["/ws/orders/{id}/events", "Live stream of orchestrator events for UI progress bars"],
        ["/ws/hitl/{session_id}", "Bi-directional chat between human and HiTL agent"],
    ],
    col_widths=[CONTENT_W*0.40, CONTENT_W*0.60]
))

story.append(p("11.3 HiTL WebSocket Protocol", H2))
story.append(code_block('''// Server -> Client (agent message)
{
  "type": "agent_message",
  "content": "I found two possible UPCs for item 18236-08...",
  "references": ["item:18236-08"],
  "attachments": [
    {"type": "image", "url": "/artifacts/img_abc.jpg"}
  ],
  "options": ["Option A: 677478725232", "Option B: 677478725230"],
  "progress": {"current": 1, "total": 3}
}

// Client -> Server (human response)
{
  "type": "human_message",
  "content": "use option A",
  "references": ["item:18236-08"]
}

// Server -> Client (system status)
{
  "type": "system_status",
  "status": "resolved",
  "resolutions": {
    "item:18236-08:upc": "677478725232"
  }
}
'''))

story.append(PageBreak())

# ── SECTION 12: Implementation Roadmap ────────────────────────────────────
story.append(p("12. Implementation Roadmap", H1))
story.append(section_divider())

story.append(p(
    "We propose a phased 16-week implementation, starting with a single-tenant "
    "MVP for Nakoda Art & Craft serving Sagebrook Home, then generalising. Each "
    "phase ends with a demonstrable milestone."
))

phases = [
    ("Phase 0: Discovery & Setup", "Week 1-2",
     "Finalise requirements, set up dev environment, Docker Compose stack, CI/CD, database schema migrations. Import existing POC code (gen_diecuts_v2.py, gen_approval_pdfs.py)."),
    ("Phase 1: Ingestion & Extraction MVP", "Week 3-5",
     "Build PO Parser Agent (Claude Sonnet 4.6), PI Parser (deterministic), Intake Agent. End-to-end for Sagebrook Home POs with manual Importer Profile seeded."),
    ("Phase 2: Fusion, Composition & Delivery", "Week 6-8",
     "Fusion Agent with schema validation. Port gen_diecuts_v2.py and gen_approval_pdfs.py into Composer Agents. Generate SVGs + approval PDFs end-to-end. Human review dashboard."),
    ("Phase 3: Onboarding Agents", "Week 9-11",
     "Protocol Analyzer Agent (Claude Opus 4.6 vision). Warning Label Parser Agent. Checklist Rule Extractor Agent. Onboard a second importer (Elevarre) entirely through the system as proof of generality."),
    ("Phase 4: Compliance Rules Engine + Line Drawings", "Week 12-13",
     "Build the rule engine with Sagebrook's 15 warning labels. Line Drawing Agent (potrace + SD fallback). Warning Label placement on die-cuts."),
    ("Phase 5: HiTL Conversational Agent", "Week 14",
     "Claude-powered chat agent. Websocket protocol. Integration with orchestrator state machine. Learning loop that proposes profile updates."),
    ("Phase 6: Validation, Observability, Hardening", "Week 15",
     "Validator Agent. OpenTelemetry traces. Langfuse LLM tracking. Error handling and retries. Backup strategy."),
    ("Phase 7: Pilot & Handover", "Week 16",
     "Run 20 real orders through the system with Nakoda's team. Capture feedback. Document runbook. Train users. Go live."),
]

story.append(multi_table(
    ["Phase", "Timeline", "Deliverables"],
    [[p[0], p[1], p[2]] for p in phases],
    col_widths=[CONTENT_W*0.26, CONTENT_W*0.14, CONTENT_W*0.60]
))

story.append(p("12.1 MVP Definition (End of Phase 2)", H2))
story.append(p(
    "A Minimum Viable Product that can be used in anger after 8 weeks:"
))
story.append(bullet_list([
    "Single tenant: Nakoda Art & Craft",
    "Single importer: Sagebrook Home with hand-seeded profile",
    "Upload PO PDF + PI XLSX -> get 8 die-cut SVGs + 8 approval PDFs",
    "Human review + one-click approval",
    "No conversational HiTL (basic form-based resolution only)",
    "No automatic onboarding (profiles hand-built by dev team)",
    "No compliance rules engine yet (warning labels manually specified)",
]))

story.append(p("12.2 Effort Estimate", H2))
story.append(multi_table(
    ["Role", "FTE weeks"],
    [
        ["Backend engineer (Python, LLM, orchestration)", "10"],
        ["Frontend engineer (React, dashboard, HiTL chat)", "6"],
        ["AI/Prompt engineer (agent prompts, eval, tuning)", "6"],
        ["DevOps (CI/CD, infra, observability)", "3"],
        ["Product + QA (requirements, user testing)", "4"],
        ["<b>Total</b>", "<b>29 FTE-weeks</b>"],
    ],
    col_widths=[CONTENT_W*0.60, CONTENT_W*0.40]
))

story.append(p("12.3 Running Cost Estimate (monthly)", H2))
story.append(multi_table(
    ["Item", "Est. cost (USD)", "Notes"],
    [
        ["LLM API (Claude + GPT)", "$150 - $400", "Assumes 50 orders/month × 10 SKUs, vision + text calls"],
        ["Hosting (AWS ECS + RDS small)", "$120 - $200", "Can drop to $30/month on Hetzner VPS for small scale"],
        ["S3 / MinIO storage", "$10 - $30", "PDFs, SVGs, product images"],
        ["Langfuse / Sentry", "$0 - $50", "Free tier covers low volume"],
        ["Stable Diffusion GPU (if used for line drawings)", "$0 - $100", "Runpod or Replicate; or skip if potrace suffices"],
        ["<b>Total</b>", "<b>~$280 - $780</b>", "Scales sub-linearly with order volume"],
    ],
    col_widths=[CONTENT_W*0.36, CONTENT_W*0.22, CONTENT_W*0.42]
))

story.append(PageBreak())

# ── SECTION 13: Risks & Mitigations ───────────────────────────────────────
story.append(p("13. Risks &amp; Mitigations", H1))
story.append(section_divider())

risks = [
    ("LLM hallucinates a UPC or dimension",
     "HIGH", "Deterministic validation (UPC checksum, dimension sanity checks). HiTL trigger on low confidence. Never auto-accept a UPC if it fails checksum."),
    ("Legal wording on warning labels gets paraphrased",
     "HIGH", "Extract verbatim with Claude Opus 4.6 + explicit 'do not paraphrase' instruction. Store extracted text + original image side-by-side. Human QA approval required during onboarding."),
    ("Protocol PDF updated by client without notification",
     "MEDIUM", "Hash the protocol file on every order. If client attaches a newer protocol version, flag for re-onboarding review."),
    ("New importer format breaks PO Parser",
     "MEDIUM", "Confidence-threshold routing — low-confidence extractions go to HiTL, where the human resolution teaches the system. Vector memory retrieval finds similar past POs."),
    ("Line drawing quality is poor for some products",
     "MEDIUM", "Two-tier: potrace first, SD ControlNet fallback. If both fail, HiTL prompts user to draw or upload a better image."),
    ("Printer complains about SVG not importing into CorelDraw",
     "LOW", "POC already uses xlink:href + xmlns namespaces that CorelDraw understands. Have printer QA the output format in Phase 2."),
    ("Single LLM provider outage",
     "LOW", "LiteLLM abstraction allows swap between Anthropic / OpenAI / Google within minutes."),
    ("Data privacy (client POs contain confidential pricing)",
     "MEDIUM", "Encryption at rest (S3/Postgres). Tenant isolation. Configurable LLM provider (Azure OpenAI for enterprise)."),
    ("Cost spike from runaway LLM calls",
     "MEDIUM", "Per-order and per-tenant budget limits. Langfuse monitoring with alerts. Caching of repeated extractions."),
    ("User rejects the change (adoption risk)",
     "HIGH", "Run parallel with manual process for 2 weeks in Phase 7. Capture time savings. Involve designers in the HiTL UX design so they feel it's a helper not a replacement."),
]

story.append(multi_table(
    ["Risk", "Severity", "Mitigation"],
    risks,
    col_widths=[CONTENT_W*0.30, CONTENT_W*0.12, CONTENT_W*0.58]
))

story.append(PageBreak())

# ── SECTION 14: Glossary ──────────────────────────────────────────────────
story.append(p("14. Glossary", H1))
story.append(section_divider())

glossary = [
    ("Agent", "A specialised AI component with a focused prompt, limited tool access, and deterministic validation of its output."),
    ("Approval PDF", "Scaled-to-fit PDF with red dimension annotations sent to the client for review; NOT actual size."),
    ("CBM", "Cubic Meters — volume used for shipping freight calculations."),
    ("Compliance Rules DB", "Structured database of trigger rules (material, destination, weight) mapping to required warning labels."),
    ("CorelDraw", "Vector graphics editor used by carton box printers for plate preparation."),
    ("Die-cut", "Flattened carton box layout showing the 4 side panels plus top/bottom flaps with fold lines and cut outlines."),
    ("Exporter Profile", "Tenant configuration for an exporting agency; mainly the PI template layout."),
    ("Fusion", "The process of joining PO and PI data by item number and cross-validating fields."),
    ("HiTL", "Human-in-the-Loop. In this system, an interactive conversational agent that resolves blocking issues."),
    ("Importer Profile", "Fixed template for an importer (brand rules, panel layout, symbols, compliance). Built once during onboarding."),
    ("ISO 780", "International standard for handling symbols (this-side-up, fragile, keep-dry, etc.)."),
    ("LLM", "Large Language Model (Claude, GPT, Gemini, etc.)."),
    ("PI", "Proforma Invoice — Excel document prepared by exporter with carton dimensions and CBM."),
    ("PO", "Purchase Order — PDF/Excel document from importer listing ordered items."),
    ("Potrace", "Open source tool that converts bitmap images to SVG vector paths — used for line drawings."),
    ("Prop 65", "California Proposition 65 — requires warnings on products containing listed chemicals."),
    ("TSCA", "Toxic Substances Control Act — US law requiring formaldehyde warnings on MDF/plywood products."),
    ("UPC-A", "12-digit Universal Product Code with check digit; standard barcode format for retail products."),
    ("Vision LLM", "Multimodal LLM that accepts image input; used for reading protocol PDFs and warning label artwork."),
    ("Warning Label", "Legally-required printed notice on a carton or product (e.g., FDA Non-Food Use, Team Lift)."),
]
story.append(kv_table(glossary))

story.append(p("15. Conclusion", H1))
story.append(section_divider())
story.append(p(
    "This document lays out every element needed to build the Export Labeling "
    "Automation System: the current manual workflow with its pain points, the "
    "target automated workflow with projected metrics, every input and output "
    "artifact, the full multi-layer architecture, fourteen specialised AI "
    "agents with their prompts and tools, the orchestrator state machine with "
    "feedback loops, the human-in-the-loop conversational chatbot specification "
    "with a complete example dialogue, the complete technology stack with "
    "specific library and model choices, the database schema, the REST and "
    "WebSocket APIs, the 16-week phased implementation roadmap, the cost "
    "estimates, and the risk register. A proof of concept has already been "
    "delivered for PO#25364 with 8 working die-cut SVGs and 8 approval PDFs "
    "using real client assets. The next step is Phase 0 kickoff: finalize the "
    "development team, set up the infrastructure, and begin Phase 1 ingestion "
    "work on Week 1."
))

story.append(Spacer(1, 20))
story.append(p(
    "<i>End of document. For questions, revisions, or implementation kick-off, "
    "contact the solution architect team.</i>",
    ParagraphStyle('Closing', parent=BODY, alignment=TA_CENTER,
                    textColor=MUTED, fontSize=9, fontName='Helvetica-Oblique')
))


# ═══════════════════════════════════════════════════════════════════════════
#                              BUILD THE PDF
# ═══════════════════════════════════════════════════════════════════════════

class SolutionDoc(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, pagesize=A4,
                          leftMargin=MARGIN_L, rightMargin=MARGIN_R,
                          topMargin=MARGIN_T, bottomMargin=MARGIN_B)
        # Cover page — no header/footer
        cover_frame = Frame(0, 0, PAGE_W, PAGE_H, id='cover')
        cover_template = PageTemplate(id='cover', frames=[cover_frame],
                                       onPage=draw_cover)
        # Body pages — with header/footer
        body_frame = Frame(MARGIN_L, MARGIN_B, CONTENT_W,
                            PAGE_H - MARGIN_T - MARGIN_B, id='body')
        body_template = PageTemplate(id='body', frames=[body_frame],
                                      onPage=draw_header_footer)
        self.addPageTemplates([cover_template, body_template])


# Add a page break at the start to switch from cover to body template
def main():
    doc_story = [
        NextPageTemplate('body'),
        PageBreak(),
    ]
    doc_story.extend(story)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    doc = SolutionDoc(OUTPUT_FILE)
    doc.build(doc_story)

    print(f"✓ Generated: {OUTPUT_FILE}")
    print(f"  Size: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")


if __name__ == '__main__':
    main()
