#!/usr/bin/env python3
"""
Generate the system architecture diagram as a high-quality SVG.
Shows all major components, data flows, and integration points.
"""

SVG_W = 1400
SVG_H = 2050

# Color palette
C_BG = "#f8f9fa"
C_PRIMARY = "#1a365d"      # Dark blue - headers
C_SECONDARY = "#2b6cb0"    # Medium blue - modules
C_ACCENT = "#e53e3e"       # Red - AI/ML components
C_SUCCESS = "#276749"      # Green - output
C_ORANGE = "#c05621"       # Orange - data stores
C_PURPLE = "#6b46c1"       # Purple - external
C_LIGHT_BLUE = "#ebf4ff"
C_LIGHT_RED = "#fff5f5"
C_LIGHT_GREEN = "#f0fff4"
C_LIGHT_ORANGE = "#fffaf0"
C_LIGHT_PURPLE = "#faf5ff"
C_WHITE = "#ffffff"
C_GRAY = "#718096"
C_LIGHT_GRAY = "#e2e8f0"
C_BORDER = "#cbd5e0"

def rounded_box(x, y, w, h, rx, fill, stroke, stroke_w=1.5, opacity=1):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}" opacity="{opacity}"/>'

def text(x, y, txt, size=14, weight="normal", fill="#000", anchor="middle", family="Inter, Arial, sans-serif"):
    safe = txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{fill}">{safe}</text>'

def arrow(x1, y1, x2, y2, color="#718096", width=2, dashed=False):
    dash = ' stroke-dasharray="6,3"' if dashed else ''
    # Arrowhead
    mid_id = f"ah_{x1}_{y1}_{x2}_{y2}".replace(".","_").replace("-","m")
    marker = f'<marker id="{mid_id}" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="{color}"/></marker>'
    line = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{dash} marker-end="url(#{mid_id})"/>'
    return marker + line

def arrow_path(d, color="#718096", width=2, dashed=False):
    dash = ' stroke-dasharray="6,3"' if dashed else ''
    mid_id = f"ap_{hash(d) % 100000}"
    marker = f'<marker id="{mid_id}" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="{color}"/></marker>'
    path = f'<path d="{d}" stroke="{color}" stroke-width="{width}" fill="none"{dash} marker-end="url(#{mid_id})"/>'
    return marker + path

def module_box(x, y, w, h, title, items, header_color, bg_color, icon=""):
    svg = ""
    svg += rounded_box(x, y, w, h, 8, bg_color, header_color, 2)
    # Header bar
    svg += f'<rect x="{x}" y="{y}" width="{w}" height="38" rx="8" ry="8" fill="{header_color}"/>'
    svg += f'<rect x="{x}" y="{y+20}" width="{w}" height="18" fill="{header_color}"/>'
    # Title
    svg += text(x + w/2, y + 25, f"{icon} {title}" if icon else title, 13, "700", C_WHITE)
    # Items
    for i, item in enumerate(items):
        iy = y + 52 + i * 22
        svg += f'<circle cx="{x+18}" cy="{iy-4}" r="3" fill="{header_color}" opacity="0.6"/>'
        svg += text(x + 28, iy, item, 11, "500", "#333", "start")
    return svg

def data_store(x, y, w, h, label, sublabel="", color=C_ORANGE):
    svg = ""
    # Cylinder shape for data store
    svg += f'<ellipse cx="{x+w/2}" cy="{y+12}" rx="{w/2}" ry="12" fill="{color}" opacity="0.15" stroke="{color}" stroke-width="1.5"/>'
    svg += f'<rect x="{x}" y="{y+12}" width="{w}" height="{h-24}" fill="{color}" opacity="0.08" stroke="none"/>'
    svg += f'<line x1="{x}" y1="{y+12}" x2="{x}" y2="{y+h-12}" stroke="{color}" stroke-width="1.5"/>'
    svg += f'<line x1="{x+w}" y1="{y+12}" x2="{x+w}" y2="{y+h-12}" stroke="{color}" stroke-width="1.5"/>'
    svg += f'<ellipse cx="{x+w/2}" cy="{y+h-12}" rx="{w/2}" ry="12" fill="{color}" opacity="0.15" stroke="{color}" stroke-width="1.5"/>'
    svg += text(x + w/2, y + h/2 + 2, label, 11, "700", color)
    if sublabel:
        svg += text(x + w/2, y + h/2 + 16, sublabel, 9, "400", C_GRAY)
    return svg


def generate():
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}">
<defs>
  <filter id="shadow" x="-2%" y="-2%" width="104%" height="104%">
    <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.1"/>
  </filter>
  <linearGradient id="bgGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#f0f4f8"/>
    <stop offset="100%" stop-color="#e2e8f0"/>
  </linearGradient>
</defs>

<!-- Background -->
<rect width="{SVG_W}" height="{SVG_H}" fill="url(#bgGrad)"/>

'''
    # ── TITLE ──
    svg += text(SVG_W/2, 42, "EXPORT LABELING AUTOMATION SYSTEM", 26, "900", C_PRIMARY)
    svg += text(SVG_W/2, 66, "AI-Powered Carton Labels, Warning Labels & Compliance — Generic Architecture v2.0", 14, "400", C_GRAY)
    svg += f'<line x1="100" y1="82" x2="{SVG_W-100}" y2="82" stroke="{C_BORDER}" stroke-width="1"/>'

    # ════════════════════════════════════════════════════════════════════
    # LAYER 1: INPUT SOURCES (top)
    # ════════════════════════════════════════════════════════════════════
    ly1 = 100
    svg += text(70, ly1 + 18, "INPUTS", 12, "800", C_PURPLE, "start")
    svg += f'<line x1="70" y1="{ly1+24}" x2="160" y2="{ly1+24}" stroke="{C_PURPLE}" stroke-width="2"/>'

    # Input boxes - row 1: per-order inputs
    svg += text(90, ly1+30, "Per-Order Inputs:", 10, "700", C_PURPLE, "start")
    inputs_row1 = [
        (90, ly1+40, 185, 85, "Purchase Order (PO)", ["PDF / Excel / EDI", "Item#, UPC, Desc, Dims", "Product images embedded"], C_PURPLE, C_LIGHT_PURPLE),
        (295, ly1+40, 185, 85, "Proforma Invoice (PI)", ["Excel (exporter format)", "Carton L×W×H, CBM", "Inner/outer pack counts"], C_PURPLE, C_LIGHT_PURPLE),
        (500, ly1+40, 185, 85, "Product Images", ["Extracted from PO PDF", "Or uploaded separately", "Any raster format"], C_PURPLE, C_LIGHT_PURPLE),
    ]
    # Row 2: onboarding inputs
    svg += text(730, ly1+30, "Onboarding Inputs (once per Importer):", 10, "700", C_ACCENT, "start")
    inputs_row2 = [
        (730, ly1+40, 165, 85, "Client Protocol", ["Brand guidelines", "Panel layout rules", "Annotated images"], C_ACCENT, C_LIGHT_RED),
        (915, ly1+40, 165, 85, "Warning Label Specs", ["Prop65, FDA, TSCA", "Label artwork + sizes", "Application methods"], C_ACCENT, C_LIGHT_RED),
        (1100, ly1+40, 180, 85, "Checklist + Mockups", ["Document checklist", "Trigger conditions", "Carton mockup photos"], C_ACCENT, C_LIGHT_RED),
    ]
    inputs = inputs_row1 + inputs_row2
    for (x, y, w, h, title, items_list, hc, bg) in inputs:
        svg += module_box(x, y, w, h, title, items_list, hc, bg)

    # ════════════════════════════════════════════════════════════════════
    # LAYER 2: DOCUMENT INGESTION ENGINE
    # ════════════════════════════════════════════════════════════════════
    ly2 = 310
    svg += text(70, ly2 + 18, "LAYER 1: DOCUMENT INGESTION", 12, "800", C_SECONDARY, "start")
    svg += f'<line x1="70" y1="{ly2+24}" x2="340" y2="{ly2+24}" stroke="{C_SECONDARY}" stroke-width="2"/>'

    # Arrows from inputs to ingestion
    for ix in [182, 387, 592]:
        svg += arrow(ix, ly1+125, ix, ly2+35, C_GRAY, 1.5)
    for ix in [812, 997, 1190]:
        svg += arrow(ix, ly1+125, ix, ly2+35, C_ACCENT, 1.5, dashed=True)

    svg += module_box(70, ly2+35, 255, 140, "Multi-Format Document Parser", [
        "PDF text + image extraction (pymupdf)",
        "Excel/CSV structured reader (pandas)",
        "OCR fallback for scanned docs",
        "Auto-detect document type",
    ], C_SECONDARY, C_LIGHT_BLUE, "📄")

    svg += module_box(345, ly2+35, 255, 140, "Adaptive Field Extractor (AI)", [
        "LLM-based field recognition",
        "Maps any PO format → standard schema",
        "Confidence scoring per field",
        "Human review for low confidence",
    ], C_ACCENT, C_LIGHT_RED, "🤖")

    svg += module_box(620, ly2+35, 215, 140, "Image Processor", [
        "Extract from PDF pages",
        "Background removal",
        "Quality assessment",
        "SKU matching",
    ], C_SECONDARY, C_LIGHT_BLUE, "🖼")

    svg += module_box(855, ly2+35, 215, 140, "Warning Label & Checklist Parser", [
        "Extract trigger conditions",
        "Parse label artwork + text",
        "Build compliance rules DB",
        "Material-to-label mapping",
    ], C_ACCENT, C_LIGHT_RED, "⚠")

    svg += module_box(1090, ly2+35, 230, 140, "Protocol & Mockup Analyzer", [
        "Vision AI on annotated images",
        "Extract brand + layout rules",
        "Barcode placement from mockup",
        "One-time per Importer",
    ], C_ACCENT, C_LIGHT_RED, "🔍")

    # ════════════════════════════════════════════════════════════════════
    # DATA STORES (center-right)
    # ════════════════════════════════════════════════════════════════════
    ly_ds = 540
    svg += text(70, ly_ds + 18, "DATA LAYER", 12, "800", C_ORANGE, "start")
    svg += f'<line x1="70" y1="{ly_ds+24}" x2="195" y2="{ly_ds+24}" stroke="{C_ORANGE}" stroke-width="2"/>'

    # Arrows from L1 to data stores
    svg += arrow(197, ly2+175, 160, ly_ds+40, C_GRAY, 1.5)
    svg += arrow(472, ly2+175, 370, ly_ds+40, C_GRAY, 1.5)
    svg += arrow(727, ly2+175, 580, ly_ds+40, C_GRAY, 1.5)
    svg += arrow(962, ly2+175, 870, ly_ds+40, C_ACCENT, 1.5)
    svg += arrow(1205, ly2+175, 870, ly_ds+40, C_ACCENT, 1.5)

    svg += data_store(80, ly_ds+40, 160, 70, "Extracted PO Data", "Normalized JSON", C_SECONDARY)
    svg += data_store(270, ly_ds+40, 160, 70, "Extracted PI Data", "Carton specs", C_SECONDARY)
    svg += data_store(460, ly_ds+40, 160, 70, "Product Images", "Cleaned, indexed", C_SECONDARY)

    # Importer Profile DB - special emphasis (now includes compliance rules)
    svg += rounded_box(670, ly_ds+30, 340, 95, 8, C_LIGHT_ORANGE, C_ORANGE, 2.5)
    svg += f'<rect x="670" y="{ly_ds+30}" width="340" height="32" rx="8" ry="8" fill="{C_ORANGE}"/>'
    svg += f'<rect x="670" y="{ly_ds+45}" width="340" height="17" fill="{C_ORANGE}"/>'
    svg += text(840, ly_ds+52, "⭐ Importer Profile DB", 12, "700", C_WHITE)
    svg += text(840, ly_ds+75, "Brand, fonts, panel layout, handling symbols,", 10, "400", "#555")
    svg += text(840, ly_ds+88, "compliance rules DB, warning label templates,", 10, "400", "#555")
    svg += text(840, ly_ds+101, "barcode config, carton mockup reference", 10, "400", "#555")
    svg += text(840, ly_ds+116, "FIXED per importer — configured once", 10, "700", C_ORANGE)

    svg += data_store(1060, ly_ds+40, 160, 70, "Exporter Profile", "PI format map", C_SUCCESS)

    # ════════════════════════════════════════════════════════════════════
    # LAYER 3: DATA FUSION & VALIDATION
    # ════════════════════════════════════════════════════════════════════
    ly3 = 720
    svg += text(70, ly3 + 18, "LAYER 2: DATA FUSION &amp; VALIDATION", 12, "800", C_SECONDARY, "start")
    svg += f'<line x1="70" y1="{ly3+24}" x2="370" y2="{ly3+24}" stroke="{C_SECONDARY}" stroke-width="2"/>'

    # Arrows from data stores to fusion
    svg += arrow(160, ly_ds+110, 250, ly3+40, C_GRAY, 1.5)
    svg += arrow(350, ly_ds+110, 350, ly3+40, C_GRAY, 1.5)
    svg += arrow(540, ly_ds+110, 450, ly3+40, C_GRAY, 1.5)
    svg += arrow(840, ly_ds+125, 700, ly3+40, C_GRAY, 1.5)
    svg += arrow(840, ly_ds+125, 1050, ly3+40, C_ACCENT, 1.5)

    svg += module_box(120, ly3+35, 280, 135, "Data Fusion Engine", [
        "Match PO items ↔ PI line items by SKU",
        "Merge: product info + carton specs",
        "Calculate derived fields (CBM, panel sizes)",
        "Generate unified CartonDataRecord per SKU",
        "Flag missing data (e.g., gross weight)",
    ], C_SECONDARY, C_LIGHT_BLUE, "🔗")

    svg += module_box(430, ly3+35, 280, 135, "Validation & QC Engine", [
        "Cross-validate item# across PO ↔ PI",
        "Verify carton dims ≥ product dims",
        "Validate UPC/GTIN check digits",
        "Check all required fields present",
        "Generate validation report with scores",
    ], C_SECONDARY, C_LIGHT_BLUE, "✅")

    svg += module_box(740, ly3+35, 260, 135, "Compliance Rules Engine", [
        "Classify product material & type via AI",
        "Evaluate trigger conditions per SKU",
        "Determine applicable warning labels",
        "Generate compliance manifest",
        "Flag low-confidence for human review",
    ], C_ACCENT, C_LIGHT_RED, "⚖")

    # Missing data + barcode
    svg += module_box(1030, ly3+45, 240, 115, "Barcode & Missing Data", [
        "Generate UPC-A / ITF-14 SVGs",
        "Estimate gross weight if missing",
        "Queue critical gaps for human input",
        "Log all assumptions made",
    ], C_ORANGE, C_LIGHT_ORANGE, "📊")

    # ════════════════════════════════════════════════════════════════════
    # LAYER 4: AI GENERATION ENGINE
    # ════════════════════════════════════════════════════════════════════
    ly4 = 960
    svg += text(70, ly4 + 18, "LAYER 3: AI GENERATION ENGINE", 12, "800", C_ACCENT, "start")
    svg += f'<line x1="70" y1="{ly4+24}" x2="340" y2="{ly4+24}" stroke="{C_ACCENT}" stroke-width="2"/>'

    # Arrows from fusion to generation
    svg += arrow(260, ly3+170, 260, ly4+40, C_ACCENT, 2)
    svg += arrow(570, ly3+170, 530, ly4+40, C_ACCENT, 2)
    svg += arrow(870, ly3+170, 800, ly4+40, C_ACCENT, 2)
    svg += arrow(1150, ly3+160, 1100, ly4+40, C_ACCENT, 2)

    svg += module_box(80, ly4+35, 270, 155, "Line Drawing Generator", [
        "Vision AI analyzes product photos",
        "Extracts shape silhouette + features",
        "Generates clean SVG vector outline",
        "Style-consistent per importer profile",
        "Cached per product for reuse",
        "Handles: vases, jugs, bowls, furniture",
    ], C_ACCENT, C_LIGHT_RED, "🎨")

    svg += module_box(375, ly4+35, 290, 155, "Die-Cut Layout Composer", [
        "Reads importer SVG template spec",
        "Calculates panel widths from box L×W",
        "Places: brand, text, symbols, barcodes",
        "Inserts product drawing on short sides",
        "Handles rect/square/tall/short boxes",
        "Outputs actual-size SVG (mm units)",
    ], C_ACCENT, C_LIGHT_RED, "📐")

    svg += module_box(690, ly4+35, 270, 155, "Text, Symbol & Barcode Renderer", [
        "Brand name in specified font",
        "Handling symbols (outline or solid)",
        "UPC-A barcodes at specified positions",
        "Logistics text: PO#, carton#, wt, cube",
        "Country of origin block",
        "All elements as SVG paths",
    ], C_ACCENT, C_LIGHT_RED, "✏")

    svg += module_box(985, ly4+35, 290, 155, "Compliance Label Renderer", [
        "Render warning labels from templates",
        "Prop65, FDA, TSCA, anti-tip, etc.",
        "Carton part count labels (1 of 2)",
        "Team lift / heavy object caution",
        "Output: separate sticker-print SVGs",
        "Per-SKU compliance package",
    ], C_ACCENT, C_LIGHT_RED, "⚖")

    # ════════════════════════════════════════════════════════════════════
    # LAYER 5: OUTPUT & DELIVERY
    # ════════════════════════════════════════════════════════════════════
    ly5 = 1200
    svg += text(70, ly5 + 18, "LAYER 4: OUTPUT &amp; DELIVERY", 12, "800", C_SUCCESS, "start")
    svg += f'<line x1="70" y1="{ly5+24}" x2="310" y2="{ly5+24}" stroke="{C_SUCCESS}" stroke-width="2"/>'

    # Arrows from generation to output
    svg += arrow(215, ly4+190, 200, ly5+40, C_SUCCESS, 2)
    svg += arrow(520, ly4+190, 450, ly5+40, C_SUCCESS, 2)
    svg += arrow(825, ly4+190, 700, ly5+40, C_SUCCESS, 2)
    svg += arrow(1130, ly4+190, 950, ly5+40, C_SUCCESS, 2)

    svg += module_box(70, ly5+35, 285, 155, "SVG Output Manager", [
        "Die-cut SVG per SKU (actual size)",
        "Warning label SVGs (sticker sheets)",
        "Barcode SVGs",
        "Batch generation for full PO",
        "CorelDraw-compatible formatting",
        "Version control & archival",
    ], C_SUCCESS, C_LIGHT_GREEN, "📦")

    svg += module_box(385, ly5+35, 285, 155, "Human Review Dashboard", [
        "Side-by-side: AI output vs mockup",
        "Compliance manifest review per SKU",
        "Field-level edit capability",
        "Approve / reject / revise workflow",
        "Batch approval for routine orders",
        "Feedback loop to improve AI",
    ], "#4a5568", "#f7fafc", "👁")

    svg += module_box(700, ly5+35, 285, 155, "Delivery & Integration", [
        "Email printer sheets to printer",
        "Separate: die-cut SVGs + sticker SVGs",
        "API for ERP/WMS integration",
        "Webhook on PO → auto-generate",
        "Audit trail & compliance log",
        "Analytics dashboard",
    ], C_SUCCESS, C_LIGHT_GREEN, "🚀")

    svg += module_box(1015, ly5+35, 285, 155, "Compliance Audit Trail", [
        "Per-SKU label decisions logged",
        "Trigger condition match evidence",
        "Human override history",
        "Regulatory change tracking",
        "Exportable for customs review",
        "Proof of due diligence",
    ], C_SUCCESS, C_LIGHT_GREEN, "📋")

    # ════════════════════════════════════════════════════════════════════
    # LAYER 6: ONBOARDING FLOW (bottom)
    # ════════════════════════════════════════════════════════════════════
    ly6 = 1430
    svg += text(70, ly6 + 18, "ONBOARDING FLOW (ONE-TIME PER IMPORTER)", 12, "800", C_ACCENT, "start")
    svg += f'<line x1="70" y1="{ly6+24}" x2="440" y2="{ly6+24}" stroke="{C_ACCENT}" stroke-width="2"/>'

    # Onboarding steps as a horizontal flow
    steps = [
        ("1. Upload All\nImporter Docs", "Protocol, warnings,\nchecklist, mockups"),
        ("2. AI Parses\nProtocol + Labels", "Brand rules, layout,\nwarning templates"),
        ("3. AI Builds\nCompliance Rules", "Trigger conditions\nfrom checklist"),
        ("4. Mockup Analysis\n& Validation", "Barcode placement,\nsymbol style"),
        ("5. Human Reviews\n& Adjusts", "Fine-tune rules,\nfix font mappings"),
        ("6. Profile Saved\n& Locked", "Ready for all\nfuture orders"),
    ]
    step_w = 185
    step_h = 85
    gap = 12
    start_x = 55
    for i, (title, desc) in enumerate(steps):
        sx = start_x + i * (step_w + gap)
        sy = ly6 + 40
        color = C_ACCENT if i == 2 else C_SECONDARY
        bg = C_LIGHT_RED if i == 2 else C_LIGHT_BLUE
        svg += rounded_box(sx, sy, step_w, step_h, 8, bg, color, 2)
        lines = title.split("\n")
        svg += text(sx + step_w/2, sy + 24, lines[0], 12, "700", color)
        if len(lines) > 1:
            svg += text(sx + step_w/2, sy + 38, lines[1], 12, "700", color)
        desc_lines = desc.split("\n")
        svg += text(sx + step_w/2, sy + 56, desc_lines[0], 10, "400", C_GRAY)
        if len(desc_lines) > 1:
            svg += text(sx + step_w/2, sy + 68, desc_lines[1], 10, "400", C_GRAY)

        # Arrow between steps
        if i < len(steps) - 1:
            svg += arrow(sx + step_w + 2, sy + step_h/2, sx + step_w + gap - 2, sy + step_h/2, color, 2)

    # ════════════════════════════════════════════════════════════════════
    # PRODUCTION FLOW (bottom)
    # ════════════════════════════════════════════════════════════════════
    ly7 = 1600
    svg += text(70, ly7 + 18, "PRODUCTION FLOW (PER ORDER)", 12, "800", C_SUCCESS, "start")
    svg += f'<line x1="70" y1="{ly7+24}" x2="340" y2="{ly7+24}" stroke="{C_SUCCESS}" stroke-width="2"/>'

    prod_steps = [
        ("1. Receive PO\n+ PI", "Auto-ingest via\nemail/API/upload"),
        ("2. Extract &amp;\nFuse Data", "AI reads docs,\nmerges with profile"),
        ("3. Generate\nLine Drawings", "Vision AI creates\nSVG per product"),
        ("4. Compose\nDie-Cut SVGs", "Full carton layout\nat actual size"),
        ("5. Review &amp;\nApprove", "Human QC check\n&amp; approval"),
        ("6. Deliver to\nPrinter", "SVG files sent\nto carton printer"),
    ]
    step_w = 185
    step_h = 80
    gap = 12
    start_x = 55
    for i, (title, desc) in enumerate(prod_steps):
        sx = start_x + i * (step_w + gap)
        sy = ly7 + 40
        svg += rounded_box(sx, sy, step_w, step_h, 8, C_LIGHT_GREEN, C_SUCCESS, 2)
        lines = title.split("\n")
        svg += text(sx + step_w/2, sy + 22, lines[0], 11, "700", C_SUCCESS)
        if len(lines) > 1:
            svg += text(sx + step_w/2, sy + 36, lines[1], 11, "700", C_SUCCESS)
        desc_lines = desc.split("\n")
        svg += text(sx + step_w/2, sy + 52, desc_lines[0], 9, "400", C_GRAY)
        if len(desc_lines) > 1:
            svg += text(sx + step_w/2, sy + 63, desc_lines[1], 9, "400", C_GRAY)

        if i < len(prod_steps) - 1:
            svg += arrow(sx + step_w + 2, sy + step_h/2, sx + step_w + gap - 2, sy + step_h/2, C_SUCCESS, 2)

    # ════════════════════════════════════════════════════════════════════
    # KEY DESIGN PRINCIPLES (bottom right)
    # ════════════════════════════════════════════════════════════════════
    ly8 = 1760
    svg += rounded_box(70, ly8, SVG_W - 140, 160, 10, C_WHITE, C_BORDER, 1.5)
    svg += text(SVG_W/2, ly8 + 25, "KEY DESIGN PRINCIPLES", 14, "800", C_PRIMARY)

    principles = [
        ("Importer-Agnostic Ingestion", "Adaptive AI reads ANY PO/Protocol/Warning format — no hardcoded parsers"),
        ("Fixed Output per Importer", "Once an importer profile is configured, all their orders use the same template"),
        ("Automated Compliance", "Rules engine auto-determines which warning labels apply per SKU from product attributes"),
        ("AI-Generated Line Drawings", "No pre-built library — Vision AI creates fresh SVG outlines from product photos"),
        ("Human-in-the-Loop QC", "AI generates, human validates — compliance manifest reviewed before delivery"),
        ("Actual-Size SVG Output", "Die-cuts + warning stickers as SVGs with real mm units for CorelDraw"),
    ]
    cols = 3
    col_w = (SVG_W - 180) / cols
    for i, (title, desc) in enumerate(principles):
        col = i % cols
        row = i // cols
        px = 100 + col * col_w
        py = ly8 + 48 + row * 50
        svg += f'<circle cx="{px}" cy="{py}" r="4" fill="{C_ACCENT}"/>'
        svg += text(px + 12, py + 4, title, 11, "700", C_PRIMARY, "start")
        svg += text(px + 12, py + 18, desc, 9, "400", C_GRAY, "start")

    # Footer
    svg += text(SVG_W/2, SVG_H - 15, "Export Labeling Automation System — Architecture v2.0 — Includes Compliance Engine, Barcodes & Warning Labels", 10, "400", C_GRAY)

    svg += '\n</svg>'
    return svg


def main():
    import os
    output_dir = os.environ.get("LABELFORGE_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "..", "outputs", "docs"))
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "System_Architecture_Diagram.svg")
    with open(output_path, "w") as f:
        f.write(generate())
    print("Architecture diagram generated successfully.")


if __name__ == '__main__':
    main()
