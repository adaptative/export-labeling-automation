#!/usr/bin/env python3
"""
Generate approval PDFs for client (importer) review.
Matches the exact format from the SAGEBROOK HOME 13 ITEM reference PDF:
  - Title header: "ITEM_NO- L X W X H INCH"
  - Die-cut layout with 4 panels + top/bottom flaps
  - RED dimension markings with arrow lines
  - Handling symbols area labeled "1"" and "3.15""
  - Two alternating panel types: LONG and SHORT
  - Scaled to fit on landscape page
"""

import os
from reportlab.lib.units import inch, mm
from reportlab.lib.pagesizes import landscape
from reportlab.lib.colors import Color, black, white, red
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

OUTPUT_DIR = "/sessions/zealous-charming-bohr/mnt/Printing and Labeling"
ASSETS_DIR = "/sessions/zealous-charming-bohr/extracted_assets"

# Load actual assets
HANDLING_IMG = os.path.join(ASSETS_DIR, "warning_p0_img2.jpeg")
BRAND_LOGO_IMG = os.path.join(ASSETS_DIR, "protocol_p0_img1.jpeg")

IN = 25.4  # mm per inch
RED = Color(0.83, 0.18, 0.18)  # #d42f2f style red for dimensions
LIGHT_GRAY = Color(0.85, 0.85, 0.85)

# ── Item Data from PI (PO#25364) ──────────────────────────────────────────
items = [
    {
        'item_no': '18236-08',
        'description': '15X12" PAPER MACHE VASE WITH HANDLES, TAUPE',
        'case_qty': '2 PCS',
        'box_L': 26.5, 'box_W': 13.5, 'box_H': 17.0,
        'upc': '677478725232',
        'po_no': '25364',
        'drawing': 'vase_handles',
        'material': 'Paper Mache', 'finish': 'Taupe',
        'carton_weight': 15,
    },
    {
        'item_no': '20655-01',
        'description': '24" PAPER MACHE JUG WITH HANDLES, WHITE',
        'case_qty': '1 PC',
        'box_L': 17.0, 'box_W': 17.0, 'box_H': 26.5,
        'upc': '677478677166',
        'po_no': '25364',
        'drawing': 'jug_handles',
        'material': 'Paper Mache', 'finish': 'White',
        'carton_weight': 13,
    },
    {
        'item_no': '20656-03',
        'description': 'S/3 14/18/22" PAPER MACHE BOWLS, TAUPE',
        'case_qty': '1 SET',
        'box_L': 24.0, 'box_W': 24.0, 'box_H': 12.5,
        'upc': '677478725201',
        'po_no': '25364',
        'drawing': 'bowls_s3',
        'material': 'Paper Mache', 'finish': 'Taupe',
        'carton_weight': 12,
    },
    {
        'item_no': '20657',
        'description': '16" RECLAIMED WOOD RISER WITH HANDLE, BROWN',
        'case_qty': '12 PCS',
        'box_L': 28.5, 'box_W': 18.0, 'box_H': 20.0,
        'upc': '677478677197',
        'po_no': '25364',
        'drawing': 'wood_riser',
        'material': 'Reclaimed Wood', 'finish': 'Brown',
        'carton_weight': 35,
    },
    {
        'item_no': '20755-01',
        'description': '12" FLUTED PAPER MACHE BOWL, BROWN',
        'case_qty': '4 PCS',
        'box_L': 15.0, 'box_W': 15.0, 'box_H': 16.0,
        'upc': '677478722644',
        'po_no': '25364',
        'drawing': 'fluted_bowl',
        'material': 'Paper Mache', 'finish': 'Brown',
        'carton_weight': 10,
    },
    {
        'item_no': '21496-02',
        'description': '12X12" PAPER MACHE KNOBBY FOOTED BOWL, BROWN',
        'case_qty': '2 PCS',
        'box_L': 14.0, 'box_W': 14.0, 'box_H': 12.0,
        'upc': '677478694903',
        'po_no': '25364',
        'drawing': 'knobby_bowl',
        'material': 'Paper Mache', 'finish': 'Brown',
        'carton_weight': 8,
    },
    {
        'item_no': '21496-04',
        'description': '12X12" PAPER MACHE KNOBBY FOOTED BOWL, TAUPE',
        'case_qty': '2 PCS',
        'box_L': 14.0, 'box_W': 14.0, 'box_H': 12.0,
        'upc': '677478725188',
        'po_no': '25364',
        'drawing': 'knobby_bowl',
        'material': 'Paper Mache', 'finish': 'Taupe',
        'carton_weight': 8,
    },
    {
        'item_no': '21498-06',
        'description': '26X15" PAPER MACHE HANDLE VASE, TAUPE',
        'case_qty': '1 PC',
        'box_L': 17.5, 'box_W': 17.5, 'box_H': 28.5,
        'upc': '677478725287',
        'po_no': '25364',
        'drawing': 'tall_handle_vase',
        'material': 'Paper Mache', 'finish': 'Taupe',
        'carton_weight': 14,
    },
]

# ── Simple product line drawing functions (draw on canvas) ───────────────
def draw_vase_handles(c, cx, cy, w, h):
    """Simple vase outline."""
    c.saveState()
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.setFillColor(white)
    # Body
    bw, bh = w*0.5, h*0.7
    # Simplified vase shape
    p = c.beginPath()
    p.moveTo(cx - bw*0.3, cy + bh*0.5)  # rim left
    p.lineTo(cx + bw*0.3, cy + bh*0.5)  # rim right
    p.lineTo(cx + bw*0.45, cy + bh*0.1)  # widen
    p.lineTo(cx + bw*0.5, cy - bh*0.2)  # body
    p.lineTo(cx + bw*0.35, cy - bh*0.5)  # base
    p.lineTo(cx - bw*0.35, cy - bh*0.5)  # base
    p.lineTo(cx - bw*0.5, cy - bh*0.2)  # body
    p.lineTo(cx - bw*0.45, cy + bh*0.1)  # widen
    p.close()
    c.drawPath(p, stroke=1, fill=0)
    # Handles
    c.arc(cx - bw*0.65, cy - bh*0.1, cx - bw*0.35, cy + bh*0.25, 0, 180)
    c.arc(cx + bw*0.35, cy - bh*0.1, cx + bw*0.65, cy + bh*0.25, 0, 180)
    c.restoreState()

def draw_jug_handles(c, cx, cy, w, h):
    """Simple jug outline."""
    c.saveState()
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    bw, bh = w*0.4, h*0.75
    p = c.beginPath()
    p.moveTo(cx - bw*0.25, cy + bh*0.5)
    p.lineTo(cx + bw*0.25, cy + bh*0.5)
    p.lineTo(cx + bw*0.5, cy + bh*0.05)
    p.lineTo(cx + bw*0.5, cy - bh*0.3)
    p.lineTo(cx + bw*0.3, cy - bh*0.5)
    p.lineTo(cx - bw*0.3, cy - bh*0.5)
    p.lineTo(cx - bw*0.5, cy - bh*0.3)
    p.lineTo(cx - bw*0.5, cy + bh*0.05)
    p.close()
    c.drawPath(p, stroke=1, fill=0)
    c.arc(cx - bw*0.7, cy - bh*0.15, cx - bw*0.38, cy + bh*0.15, 0, 180)
    c.arc(cx + bw*0.38, cy - bh*0.15, cx + bw*0.7, cy + bh*0.15, 0, 180)
    c.restoreState()

def draw_bowls_s3(c, cx, cy, w, h):
    """Set of 3 bowls."""
    c.saveState()
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    bw = w * 0.45
    # Large bowl
    c.arc(cx - bw, cy - h*0.15, cx + bw, cy + h*0.35, 180, 180)
    c.line(cx - bw, cy + h*0.1, cx + bw, cy + h*0.1)
    # Base
    c.line(cx - bw*0.2, cy - h*0.15, cx + bw*0.2, cy - h*0.15)
    c.line(cx - bw*0.2, cy - h*0.15, cx - bw*0.2, cy - h*0.1)
    c.line(cx + bw*0.2, cy - h*0.15, cx + bw*0.2, cy - h*0.1)
    c.restoreState()

def draw_wood_riser(c, cx, cy, w, h):
    """Wood riser with handle."""
    c.saveState()
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    pw, ph = w*0.55, h*0.2
    # Platform
    c.rect(cx - pw/2, cy - ph*0.5, pw, ph, stroke=1, fill=0)
    # Legs
    c.line(cx - pw*0.4, cy - ph*0.5, cx - pw*0.4, cy - ph*0.5 - h*0.3)
    c.line(cx + pw*0.4, cy - ph*0.5, cx + pw*0.4, cy - ph*0.5 - h*0.3)
    # Handle arch
    c.arc(cx - pw*0.2, cy + ph*0.5, cx + pw*0.2, cy + ph*0.5 + h*0.35, 0, 180)
    c.restoreState()

def draw_fluted_bowl(c, cx, cy, w, h):
    """Fluted bowl."""
    c.saveState()
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    bw = w * 0.4
    c.arc(cx - bw, cy - h*0.2, cx + bw, cy + h*0.25, 180, 180)
    c.line(cx - bw, cy + h*0.02, cx + bw, cy + h*0.02)
    # Scallops on rim
    step = bw * 2 / 5
    for i in range(5):
        sx = cx - bw + i * step
        c.arc(sx, cy + h*0.0, sx + step, cy + h*0.08, 0, 180)
    # Foot
    c.line(cx - bw*0.2, cy - h*0.2, cx + bw*0.2, cy - h*0.2)
    c.restoreState()

def draw_knobby_bowl(c, cx, cy, w, h):
    """Knobby footed bowl."""
    c.saveState()
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    bw = w * 0.4
    c.arc(cx - bw, cy - h*0.15, cx + bw, cy + h*0.3, 180, 180)
    c.line(cx - bw, cy + h*0.07, cx + bw, cy + h*0.07)
    # Knobs
    for kx in [cx - bw*0.6, cx - bw*0.2, cx + bw*0.2, cx + bw*0.6]:
        c.circle(kx, cy - h*0.02, w*0.025, stroke=1, fill=0)
    # Footed base
    c.arc(cx - bw*0.3, cy - h*0.3, cx + bw*0.3, cy - h*0.15, 180, 180)
    c.line(cx - bw*0.3, cy - h*0.22, cx - bw*0.3, cy - h*0.15)
    c.line(cx + bw*0.3, cy - h*0.22, cx + bw*0.3, cy - h*0.15)
    c.restoreState()

def draw_tall_handle_vase(c, cx, cy, w, h):
    """Tall handle vase."""
    c.saveState()
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    bw, bh = w*0.35, h*0.8
    p = c.beginPath()
    p.moveTo(cx - bw*0.3, cy + bh*0.5)
    p.lineTo(cx + bw*0.3, cy + bh*0.5)
    p.lineTo(cx + bw*0.4, cy + bh*0.3)
    p.lineTo(cx + bw*0.5, cy + bh*0.0)
    p.lineTo(cx + bw*0.45, cy - bh*0.25)
    p.lineTo(cx + bw*0.3, cy - bh*0.5)
    p.lineTo(cx - bw*0.3, cy - bh*0.5)
    p.lineTo(cx - bw*0.45, cy - bh*0.25)
    p.lineTo(cx - bw*0.5, cy + bh*0.0)
    p.lineTo(cx - bw*0.4, cy + bh*0.3)
    p.close()
    c.drawPath(p, stroke=1, fill=0)
    c.arc(cx - bw*0.7, cy - bh*0.05, cx - bw*0.38, cy + bh*0.2, 0, 180)
    c.arc(cx + bw*0.38, cy - bh*0.05, cx + bw*0.7, cy + bh*0.2, 0, 180)
    c.restoreState()

DRAW_FUNCS = {
    'vase_handles': draw_vase_handles,
    'jug_handles': draw_jug_handles,
    'bowls_s3': draw_bowls_s3,
    'wood_riser': draw_wood_riser,
    'fluted_bowl': draw_fluted_bowl,
    'knobby_bowl': draw_knobby_bowl,
    'tall_handle_vase': draw_tall_handle_vase,
}


def draw_dim_h_arrow(c, x1, x2, y, label, offset=6):
    """Horizontal dimension line with arrows and label (in RED), above the line."""
    c.saveState()
    c.setStrokeColor(RED)
    c.setFillColor(RED)
    c.setLineWidth(0.5)
    aw = 3  # arrowhead width
    ah = 1.5  # arrowhead height
    # Line
    c.line(x1, y, x2, y)
    # Left arrowhead
    c.line(x1, y, x1 + aw, y + ah)
    c.line(x1, y, x1 + aw, y - ah)
    # Right arrowhead
    c.line(x2, y, x2 - aw, y + ah)
    c.line(x2, y, x2 - aw, y - ah)
    # Vertical end ticks
    c.line(x1, y - 3, x1, y + 3)
    c.line(x2, y - 3, x2, y + 3)
    # Label
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString((x1 + x2) / 2, y + offset, label)
    c.restoreState()


def draw_dim_v_arrow(c, x, y1, y2, label, offset=-10):
    """Vertical dimension line with arrows and label (in RED), to the left of the line."""
    c.saveState()
    c.setStrokeColor(RED)
    c.setFillColor(RED)
    c.setLineWidth(0.5)
    aw = 1.5
    ah = 3
    # Line
    c.line(x, y1, x, y2)
    # Bottom arrowhead
    c.line(x, y1, x - aw, y1 + ah)
    c.line(x, y1, x + aw, y1 + ah)
    # Top arrowhead
    c.line(x, y2, x - aw, y2 - ah)
    c.line(x, y2, x + aw, y2 - ah)
    # Ticks
    c.line(x - 3, y1, x + 3, y1)
    c.line(x - 3, y2, x + 3, y2)
    # Label (rotated)
    c.saveState()
    c.translate(x + offset, (y1 + y2) / 2)
    c.rotate(90)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(0, 0, label)
    c.restoreState()
    c.restoreState()


def generate_approval_pdf(item):
    """Generate a single approval PDF matching the client reference format."""
    L_in = item['box_L']
    W_in = item['box_W']
    H_in = item['box_H']
    flap_in = 3.0  # standard flap depth in inches

    total_w_in = 2 * L_in + 2 * W_in
    total_h_in = flap_in + H_in + flap_in

    # ── Page sizing ──────────────────────────────────────────────────────
    # Scale die-cut to fit on landscape page with margins
    margin = 50  # points
    title_area = 50  # points for title at top
    dim_area = 30  # extra space for dimension annotations

    # Target drawing area
    target_w = 900  # points — wide landscape
    target_h = 550  # points

    scale_x = (target_w - 2 * dim_area) / total_w_in
    scale_y = (target_h - 2 * dim_area) / total_h_in
    scale = min(scale_x, scale_y)

    draw_w = total_w_in * scale
    draw_h = total_h_in * scale

    page_w = draw_w + 2 * margin + 2 * dim_area
    page_h = draw_h + 2 * margin + title_area + dim_area + 20

    # Origin of die-cut layout (bottom-left corner of the full die-cut)
    ox = margin + dim_area + (target_w - 2*dim_area - draw_w) / 2
    oy = margin + dim_area

    fn = f"Approval_{item['item_no']}.pdf"
    fp = os.path.join(OUTPUT_DIR, fn)
    c = canvas.Canvas(fp, pagesize=(page_w, page_h))

    # ── Title ────────────────────────────────────────────────────────────
    title = f"{item['item_no']}-  {L_in} X {W_in} X {H_in} INCH"
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(black)
    c.drawCentredString(page_w / 2, page_h - margin - 10, title)

    # ── Die-cut outline ──────────────────────────────────────────────────
    c.setStrokeColor(black)
    c.setLineWidth(1.0)
    c.rect(ox, oy, draw_w, draw_h, stroke=1, fill=0)

    # ── Fold lines (dashed) ──────────────────────────────────────────────
    c.setDash(6, 3)
    c.setLineWidth(0.6)

    flap_h = flap_in * scale
    panel_h = H_in * scale

    # Horizontal fold lines (top flap / bottom flap boundaries)
    c.line(ox, oy + flap_h, ox + draw_w, oy + flap_h)
    c.line(ox, oy + flap_h + panel_h, ox + draw_w, oy + flap_h + panel_h)

    # Panel widths
    L_w = L_in * scale
    W_w = W_in * scale
    panel_specs = [
        (0, L_w, 'long'),
        (L_w, W_w, 'short'),
        (L_w + W_w, L_w, 'long'),
        (L_w + W_w + L_w, W_w, 'short'),
    ]

    # Vertical fold lines
    for i, (poff, pw, ptype) in enumerate(panel_specs):
        if i > 0:
            c.line(ox + poff, oy, ox + poff, oy + draw_h)

    c.setDash()  # Reset dash

    # ── Flap labels ──────────────────────────────────────────────────────
    c.setFont("Helvetica", 6)
    c.setFillColor(LIGHT_GRAY)
    for (poff, pw, ptype) in panel_specs:
        pcx = ox + poff + pw / 2
        # Top flap label
        c.drawCentredString(pcx, oy + flap_h + panel_h + flap_h * 0.5, "TOP FLAP")
        # Bottom flap label
        c.drawCentredString(pcx, oy + flap_h * 0.5, "BOTTOM FLAP")

    # ── Panel content ────────────────────────────────────────────────────
    handling_img = ImageReader(HANDLING_IMG)
    brand_img = ImageReader(BRAND_LOGO_IMG)

    # Calculate handling symbol display size: original 537×202
    sym_aspect = 537.0 / 202.0

    for idx, (poff, pw, ptype) in enumerate(panel_specs):
        panel_left = ox + poff
        panel_bottom = oy + flap_h
        panel_cx = panel_left + pw / 2

        # ── Handling symbols (top-right of panel) ────────────────────
        sym_h_disp = min(panel_h * 0.07, 18)
        sym_w_disp = sym_h_disp * sym_aspect
        sym_x = panel_left + pw - sym_w_disp - 5
        sym_y = panel_bottom + panel_h - sym_h_disp - 5
        c.drawImage(handling_img, sym_x, sym_y, sym_w_disp, sym_h_disp,
                     preserveAspectRatio=True, mask='auto')

        # Symbol dimension labels in red: "1"" height, "3.15"" width
        c.saveState()
        c.setFont("Helvetica-Bold", 5)
        c.setFillColor(RED)
        # "1"" to the left of symbols
        c.drawRightString(sym_x - 2, sym_y + sym_h_disp / 2, '1"')
        # "3.15"" below symbols
        c.drawCentredString(sym_x + sym_w_disp / 2, sym_y - 6, '3.15"')
        c.restoreState()

        # ── Brand logo (centered, below symbols) ─────────────────────
        logo_w_disp = min(pw * 0.65, 140)
        logo_h_disp = logo_w_disp * (500.0 / 2000.0)
        logo_x = panel_cx - logo_w_disp / 2
        logo_y = sym_y - logo_h_disp - 8
        c.drawImage(brand_img, logo_x, logo_y, logo_w_disp, logo_h_disp,
                     preserveAspectRatio=True, mask='auto')

        # ── Item No ──────────────────────────────────────────────────
        info_y = logo_y - 20
        if ptype == 'long':
            c.setFont("Helvetica-Bold", 13)
        else:
            c.setFont("Helvetica-Bold", 11)
        c.setFillColor(black)
        c.drawCentredString(panel_cx, info_y, f"ITEM NO.: {item['item_no']}")

        # ── Case Qty ─────────────────────────────────────────────────
        cq_y = info_y - 18
        if ptype == 'long':
            c.setFont("Helvetica-Bold", 13)
        else:
            c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(panel_cx, cq_y, f"CASE QTY : {item['case_qty']}")

        # ── Panel-type-specific content ──────────────────────────────
        if ptype == 'long':
            # Description
            desc_y = cq_y - 18
            c.setFont("Helvetica", 7)
            desc_text = f"DESCRIPTION : {item['description']}"
            # Truncate if too long for panel
            max_chars = int(pw / 3.5)
            if len(desc_text) > max_chars:
                desc_text = desc_text[:max_chars-2] + ".."
            c.drawCentredString(panel_cx, desc_y, desc_text)

            # Panel width dimension in red (below description)
            dim_label_y = desc_y - 10
            c.saveState()
            c.setFillColor(RED)
            c.setFont("Helvetica-Bold", 7)
            dim_w_label = f'{L_in:.2f}"'
            c.drawCentredString(panel_cx, dim_label_y, dim_w_label)
            c.restoreState()

            # Dimension line for panel width
            draw_dim_h_arrow(c, panel_left + 5, panel_left + pw - 5,
                             dim_label_y - 4, "", offset=0)

            # Dimensions text
            dim_y = dim_label_y - 16
            c.setFont("Helvetica", 7)
            c.setFillColor(black)
            dim_str = f'DIMENSIONS: : {L_in}"L x {W_in}"W x {H_in}H"'
            c.drawCentredString(panel_cx, dim_y, dim_str)

            # MADE IN INDIA
            mii_y = panel_bottom + 18
            c.setFont("Helvetica-Bold", 11)
            c.drawCentredString(panel_cx, mii_y, "MADE IN INDIA")

        else:  # short panel
            # PO No
            info_x = panel_left + 10
            line_h = 12
            ly = cq_y - 16
            c.setFont("Helvetica", 7.5)
            c.drawString(info_x, ly, f"P.O NO.: {item['po_no']}")
            ly -= line_h
            c.drawString(info_x, ly, "CARTON NO.: ____OF____")
            ly -= line_h
            c.drawString(info_x, ly, f"CARTON WEIGHT : {item['carton_weight']} (LBS)")
            ly -= line_h
            cube_cuft = (L_in * W_in * H_in) / 1728.0
            c.drawString(info_x, ly, f"CUBE : {cube_cuft:.2f} (CU FT)")

            # Product drawing
            draw_func = DRAW_FUNCS.get(item['drawing'])
            if draw_func:
                dwg_cx = panel_cx
                dwg_cy = ly - 30
                dwg_size = min(pw * 0.5, panel_h * 0.2)
                draw_func(c, dwg_cx, dwg_cy, dwg_size, dwg_size)

            # MADE IN INDIA
            mii_y = panel_bottom + 18
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(black)
            c.drawCentredString(panel_cx, mii_y, "MADE IN INDIA")

    # ── RED dimension annotations ────────────────────────────────────────

    # Panel width dimensions (at top, between top flap line and panel content)
    dim_top_y = oy + flap_h + panel_h + 6
    for (poff, pw, ptype) in panel_specs:
        px1 = ox + poff + 3
        px2 = ox + poff + pw - 3
        if ptype == 'long':
            label = f'{L_in:.2f}"'
        else:
            label = f'{W_in:.2f}"'
        draw_dim_h_arrow(c, px1, px2, dim_top_y, label, offset=4)

    # Panel height dimension (on the left side, vertical)
    # Height of the main panel area (H inches)
    v_x = ox - 12
    draw_dim_v_arrow(c, v_x, oy + flap_h, oy + flap_h + panel_h,
                      f'{H_in:.2f}"', offset=-12)

    # Total height including flaps
    v_x2 = ox - 28
    draw_dim_v_arrow(c, v_x2, oy, oy + draw_h,
                      f'{total_h_in:.2f}"', offset=-12)

    # Flap depth annotations
    flap_x = ox + draw_w + 10
    draw_dim_v_arrow(c, flap_x, oy, oy + flap_h,
                      f'{flap_in:.1f}"', offset=10)
    draw_dim_v_arrow(c, flap_x, oy + flap_h + panel_h, oy + draw_h,
                      f'{flap_in:.1f}"', offset=10)

    # Total width at bottom
    draw_dim_h_arrow(c, ox, ox + draw_w, oy - 14,
                      f'TOTAL: {total_w_in:.2f}"', offset=4)

    # ── Footer info ──────────────────────────────────────────────────────
    c.setFont("Helvetica", 6)
    c.setFillColor(Color(0.5, 0.5, 0.5))
    c.drawCentredString(page_w / 2, 15,
                         f"PO#{item['po_no']} | {item['material']} - {item['finish']} | "
                         f"Box: {L_in} x {W_in} x {H_in}\" | "
                         f"FOR CLIENT APPROVAL ONLY — NOT ACTUAL SIZE")

    c.save()
    return fn


# ── Generate all PDFs ────────────────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)

for item in items:
    fn = generate_approval_pdf(item)
    L, W, H = item['box_L'], item['box_W'], item['box_H']
    print(f"✓ {fn}")
    print(f"  {item['description'][:55]}")
    print(f"  Box: {L} x {W} x {H}\" | Panels: {L}\"+{W}\"+{L}\"+{W}\" = {2*L+2*W}\"")
    print()

print(f"All {len(items)} approval PDFs generated in: {OUTPUT_DIR}")
