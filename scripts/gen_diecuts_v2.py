#!/usr/bin/env python3
"""
Generate actual-size SVG die-cut carton box printer sheets (v2).
Improvements over v1:
  - Solid-filled handling symbols (matching actual ISO symbols)
  - UPC-A barcodes on panels (long=bottom-left, short=bottom-right)
  - Improved SAGEBROOK HOME brand treatment
  - Product-specific line drawings for all 8 items
  - Compliance notes per SKU
All dimensions in mm (1 inch = 25.4 mm).
"""

import os, math, base64

OUTPUT_DIR = "/sessions/zealous-charming-bohr/mnt/Printing and Labeling"
ASSETS_DIR = "/sessions/zealous-charming-bohr/extracted_assets"
IN = 25.4
FLAP_DEPTH = 3.0 * IN
STROKE_W = 0.5
FOLD_DASH = "4,2"

# ── Load actual assets as base64 ─────────────────────────────────────────
def load_image_b64(filename):
    """Load an image file and return its base64 data URI."""
    path = os.path.join(ASSETS_DIR, filename)
    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('ascii')
    ext = os.path.splitext(filename)[1].lower()
    mime = 'image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/png'
    return f"data:{mime};base64,{data}"

# Pre-load the actual handling symbols and brand logo
HANDLING_SYMBOLS_B64 = load_image_b64("warning_p0_img2.jpeg")   # 537×202px — 3 ISO symbols
BRAND_LOGO_B64 = load_image_b64("protocol_p0_img1.jpeg")        # 2000×500px — SH Sagebrook Home logo

# ── UPC-A Barcode Generator ───────────────────────────────────────────────
UPC_ENCODING = {
    'L': {  # Left-side encoding (odd parity)
        '0': '0001101', '1': '0011001', '2': '0010011', '3': '0111101', '4': '0100011',
        '5': '0110001', '6': '0101111', '7': '0111011', '8': '0110111', '9': '0001011'
    },
    'R': {  # Right-side encoding (even parity)
        '0': '1110010', '1': '1100110', '2': '1101100', '3': '1000010', '4': '1011100',
        '5': '1001110', '6': '1010000', '7': '1000100', '8': '1001000', '9': '1110100'
    }
}

def upc_barcode_svg(upc_str, x, y, bar_w=0.33, bar_h=22, font_size=4):
    """Generate a UPC-A barcode as SVG at position (x,y). upc_str should be 12 digits."""
    upc = upc_str.strip()[:12].ljust(12, '0')
    svg = f'<g transform="translate({x},{y})">\n'
    # Encode
    bits = '101'  # Start guard
    for i in range(6):
        bits += UPC_ENCODING['L'][upc[i]]
    bits += '01010'  # Center guard
    for i in range(6, 12):
        bits += UPC_ENCODING['R'][upc[i]]
    bits += '101'  # End guard
    # Draw bars
    bx = 0
    for bit in bits:
        if bit == '1':
            svg += f'  <rect x="{bx}" y="0" width="{bar_w}" height="{bar_h}" fill="#000"/>\n'
        bx += bar_w
    total_w = len(bits) * bar_w
    # Human-readable digits
    svg += f'  <text x="{total_w/2}" y="{bar_h + font_size + 1}" text-anchor="middle" font-family="Inter, Arial, monospace" font-size="{font_size}" font-weight="600" fill="#000">{upc}</text>\n'
    svg += '</g>\n'
    return svg, total_w

def item_label_above_barcode(item_no, x, y, width, font_size=3.5):
    """Small item number label above the barcode."""
    svg = f'<rect x="{x}" y="{y}" width="{width}" height="{font_size+3}" fill="#8BC34A" rx="1"/>\n'
    svg += f'<text x="{x + width/2}" y="{y + font_size + 1}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="{font_size}" font-weight="700" fill="#000">ITEM NO. {item_no}</text>\n'
    return svg

# ── Handling Symbols (Embedded Actual Image) ─────────────────────────────
def handling_symbols_block(x, y, sym_size=20):
    """Embed the ACTUAL handling symbols image (3 ISO icons) extracted from the client PDF.
    Original image is 537×202px (aspect ratio ~2.66:1).
    We scale to fit: width = sym_size * 3.2, height proportional."""
    w = sym_size * 3.2
    h = w * (202 / 537)  # maintain aspect ratio
    return f'<image x="{x}" y="{y}" width="{w}" height="{h}" xlink:href="{HANDLING_SYMBOLS_B64}" href="{HANDLING_SYMBOLS_B64}" preserveAspectRatio="xMidYMid meet"/>\n'


# ── Product Line Drawings ─────────────────────────────────────────────────
DRAWINGS = {
    'vase_handles': {
        'vb': '0 0 120 140',
        'paths': '''<ellipse cx="60" cy="132" rx="24" ry="4" stroke-width="1.6"/>
<path d="M36 132 C36 125, 34 115, 30 105 C26 95, 22 85, 22 78" stroke-width="1.6"/>
<path d="M84 132 C84 125, 86 115, 90 105 C94 95, 98 85, 98 78" stroke-width="1.6"/>
<path d="M22 78 C22 72, 22 66, 25 60 C28 54, 32 48, 38 44" stroke-width="1.6"/>
<path d="M98 78 C98 72, 98 66, 95 60 C92 54, 88 48, 82 44" stroke-width="1.6"/>
<path d="M38 44 C42 41, 46 38, 48 34 C50 30, 50 27, 50 24" stroke-width="1.6"/>
<path d="M82 44 C78 41, 74 38, 72 34 C70 30, 70 27, 70 24" stroke-width="1.6"/>
<path d="M50 24 C49 20, 47 16, 44 13" stroke-width="1.6"/>
<path d="M70 24 C71 20, 73 16, 76 13" stroke-width="1.6"/>
<ellipse cx="60" cy="12" rx="17" ry="4.5" stroke-width="1.6"/>
<path d="M30 58 C18 54, 12 62, 14 72 C16 80, 22 84, 28 80" stroke-width="1.5"/>
<path d="M90 58 C102 54, 108 62, 106 72 C104 80, 98 84, 92 80" stroke-width="1.5"/>'''
    },
    'jug_handles': {
        'vb': '0 0 100 150',
        'paths': '''<ellipse cx="50" cy="143" rx="18" ry="4" stroke-width="1.5"/>
<path d="M32 143 C32 138, 28 130, 22 118 C16 106, 14 94, 14 82" stroke-width="1.5"/>
<path d="M68 143 C68 138, 72 130, 78 118 C84 106, 86 94, 86 82" stroke-width="1.5"/>
<path d="M14 82 C14 70, 18 58, 26 48 C32 42, 36 36, 40 28" stroke-width="1.5"/>
<path d="M86 82 C86 70, 82 58, 74 48 C68 42, 64 36, 60 28" stroke-width="1.5"/>
<path d="M40 28 C39 22, 38 18, 37 14" stroke-width="1.5"/>
<path d="M60 28 C61 22, 62 18, 63 14" stroke-width="1.5"/>
<ellipse cx="50" cy="12" rx="14" ry="4.5" stroke-width="1.5"/>
<path d="M22 56 C12 52, 8 60, 10 68 C12 74, 18 76, 22 72" stroke-width="1.4"/>
<path d="M78 56 C88 52, 92 60, 90 68 C88 74, 82 76, 78 72" stroke-width="1.4"/>'''
    },
    'bowls_s3': {
        'vb': '0 0 160 75',
        'paths': '''<path d="M10 20 C10 50, 30 65, 80 65 C130 65, 150 50, 150 20" stroke-width="1.6"/>
<ellipse cx="80" cy="18" rx="72" ry="12" stroke-width="1.5"/>
<path d="M58 65 L58 70 L102 70 L102 65" stroke-width="1.3"/>
<path d="M28 22 C28 42, 42 54, 80 54 C118 54, 132 42, 132 22" stroke-width="1.2" opacity="0.6"/>
<path d="M44 24 C44 38, 54 46, 80 46 C106 46, 116 38, 116 24" stroke-width="1.0" opacity="0.4"/>'''
    },
    'wood_riser': {
        'vb': '0 0 140 100',
        'paths': '''<!-- Rectangular platform top surface (perspective) -->
<path d="M20 55 L70 35 L120 55 L70 75 Z" stroke-width="1.5" fill="none"/>
<!-- Platform thickness -->
<path d="M20 55 L20 62 L70 82 L120 62 L120 55" stroke-width="1.5" fill="none"/>
<line x1="70" y1="75" x2="70" y2="82" stroke-width="1.3"/>
<!-- Wood grain lines on top -->
<path d="M35 50 L70 40 L105 50" stroke-width="0.6" opacity="0.4"/>
<path d="M30 58 L70 45 L110 58" stroke-width="0.6" opacity="0.4"/>
<!-- Handle arch -->
<path d="M55 35 C55 10, 85 10, 85 35" stroke-width="1.8" fill="none"/>
<!-- Legs -->
<line x1="25" y1="62" x2="25" y2="92" stroke-width="2"/>
<line x1="115" y1="62" x2="115" y2="92" stroke-width="2"/>
<line x1="70" y1="82" x2="70" y2="95" stroke-width="1.5"/>'''
    },
    'fluted_bowl': {
        'vb': '0 0 140 80',
        'paths': '''<!-- Bowl outer rim with fluted/scalloped edge -->
<ellipse cx="70" cy="22" rx="62" ry="14" stroke-width="1.5"/>
<!-- Scallop details on rim -->
<path d="M12 26 C18 20, 24 20, 30 26" stroke-width="0.8" opacity="0.5"/>
<path d="M30 26 C36 20, 42 20, 48 26" stroke-width="0.8" opacity="0.5"/>
<path d="M48 26 C54 20, 60 20, 66 26" stroke-width="0.8" opacity="0.5"/>
<path d="M66 26 C72 20, 78 20, 84 26" stroke-width="0.8" opacity="0.5"/>
<path d="M84 26 C90 20, 96 20, 102 26" stroke-width="0.8" opacity="0.5"/>
<path d="M102 26 C108 20, 114 20, 120 26" stroke-width="0.8" opacity="0.5"/>
<!-- Bowl body curving down -->
<path d="M12 28 C12 48, 30 62, 70 62 C110 62, 128 48, 128 28" stroke-width="1.5"/>
<!-- Small foot rim -->
<path d="M48 62 L48 68 L92 68 L92 62" stroke-width="1.3"/>'''
    },
    'knobby_bowl': {
        'vb': '0 0 130 90',
        'paths': '''<!-- Bowl rim -->
<ellipse cx="65" cy="20" rx="55" ry="13" stroke-width="1.5"/>
<!-- Bowl body with knobby/bumpy texture -->
<path d="M12 24 C12 48, 30 62, 65 62 C100 62, 118 48, 118 24" stroke-width="1.5"/>
<!-- Knobs/bumps on exterior -->
<circle cx="20" cy="38" r="4" stroke-width="1" fill="none" opacity="0.6"/>
<circle cx="32" cy="48" r="4.5" stroke-width="1" fill="none" opacity="0.6"/>
<circle cx="48" cy="55" r="4" stroke-width="1" fill="none" opacity="0.6"/>
<circle cx="65" cy="58" r="4.5" stroke-width="1" fill="none" opacity="0.6"/>
<circle cx="82" cy="55" r="4" stroke-width="1" fill="none" opacity="0.6"/>
<circle cx="98" cy="48" r="4.5" stroke-width="1" fill="none" opacity="0.6"/>
<circle cx="110" cy="38" r="4" stroke-width="1" fill="none" opacity="0.6"/>
<!-- Footed base -->
<path d="M45 62 L45 72 C45 78, 85 78, 85 72 L85 62" stroke-width="1.3" fill="none"/>'''
    },
    'tall_handle_vase': {
        'vb': '0 0 100 160',
        'paths': '''<!-- Tall vase: narrow at base, widest at mid-body, tapers to narrow neck -->
<ellipse cx="50" cy="152" rx="16" ry="4" stroke-width="1.5"/>
<path d="M34 152 C34 146, 30 138, 26 128 C22 118, 20 108, 20 96" stroke-width="1.5"/>
<path d="M66 152 C66 146, 70 138, 74 128 C78 118, 80 108, 80 96" stroke-width="1.5"/>
<!-- Widest part -->
<path d="M20 96 C20 82, 22 68, 28 56 C32 48, 36 42, 40 36" stroke-width="1.5"/>
<path d="M80 96 C80 82, 78 68, 72 56 C68 48, 64 42, 60 36" stroke-width="1.5"/>
<!-- Neck -->
<path d="M40 36 C39 30, 38 24, 37 18" stroke-width="1.5"/>
<path d="M60 36 C61 30, 62 24, 63 18" stroke-width="1.5"/>
<!-- Flared rim -->
<ellipse cx="50" cy="16" rx="14" ry="4.5" stroke-width="1.5"/>
<!-- Handles -->
<path d="M24 64 C12 58, 8 68, 10 78 C12 86, 20 90, 26 84" stroke-width="1.4"/>
<path d="M76 64 C88 58, 92 68, 90 78 C88 86, 80 90, 74 84" stroke-width="1.4"/>'''
    }
}

# ── Item Data from PI (PO#25364) ──────────────────────────────────────────
items = [
    {
        'item_no': '18236-08', 'nac_code': 'BE18236-0',
        'description': '15X12" PAPER MACHE VASE WITH HANDLES, TAUPE',
        'case_qty': '2 PCS', 'total_qty': 600, 'total_cartons': 300,
        'box_L': 26.5, 'box_W': 13.5, 'box_H': 17.0,
        'cbm': 0.0997, 'upc': '677478725232', 'gtin': '60677478725234',
        'po_no': '25364', 'drawing': 'vase_handles',
        'material': 'Paper Mache', 'finish': 'Taupe',
        'warnings': ['Non-Food Use (vessel shape)', 'Fragile (all 4 sides)']
    },
    {
        'item_no': '20655-01', 'nac_code': 'PM0444',
        'description': '24" PAPER MACHE JUG WITH HANDLES, WHITE',
        'case_qty': '1 PC', 'total_qty': 500, 'total_cartons': 500,
        'box_L': 17.0, 'box_W': 17.0, 'box_H': 26.5,
        'cbm': 0.1255, 'upc': '677478677166', 'gtin': '60677478677168',
        'po_no': '25364', 'drawing': 'jug_handles',
        'material': 'Paper Mache', 'finish': 'White',
        'warnings': ['Non-Food Use (vessel shape)', 'Fragile (all 4 sides)']
    },
    {
        'item_no': '20656-03', 'nac_code': 'BE20656',
        'description': 'S/3 14/18/22" PAPER MACHE BOWLS, TAUPE',
        'case_qty': '1 SET', 'total_qty': 300, 'total_cartons': 300,
        'box_L': 24.0, 'box_W': 24.0, 'box_H': 12.5,
        'cbm': 0.1180, 'upc': '677478725201', 'gtin': '60677478725203',
        'po_no': '25364', 'drawing': 'bowls_s3',
        'material': 'Paper Mache', 'finish': 'Taupe',
        'warnings': ['Non-Food Use (vessel shape)', 'Fragile (all 4 sides)']
    },
    {
        'item_no': '20657', 'nac_code': '18102391',
        'description': '16" RECLAIMED WOOD RISER WITH HANDLE, BROWN',
        'case_qty': '12 PCS', 'total_qty': 804, 'total_cartons': 67,
        'box_L': 28.5, 'box_W': 18.0, 'box_H': 20.0,
        'cbm': 0.1681, 'upc': '677478677197', 'gtin': '60677478677199',
        'po_no': '25364', 'drawing': 'wood_riser',
        'material': 'Reclaimed Wood', 'finish': 'Brown',
        'warnings': ['Fragile (all 4 sides)']
    },
    {
        'item_no': '20755-01', 'nac_code': '4448',
        'description': '12" FLUTED PAPER MACHE BOWL, BROWN',
        'case_qty': '4 PCS', 'total_qty': 600, 'total_cartons': 150,
        'box_L': 15.0, 'box_W': 15.0, 'box_H': 16.0,
        'cbm': 0.0590, 'upc': '677478722644', 'gtin': '60677478722646',
        'po_no': '25364', 'drawing': 'fluted_bowl',
        'material': 'Paper Mache', 'finish': 'Brown',
        'warnings': ['Non-Food Use (vessel shape)', 'Fragile (all 4 sides)']
    },
    {
        'item_no': '21496-02', 'nac_code': 'N/A',
        'description': '12X12" PAPER MACHE KNOBBY FOOTED BOWL, BROWN',
        'case_qty': '2 PCS', 'total_qty': 400, 'total_cartons': 200,
        'box_L': 14.0, 'box_W': 14.0, 'box_H': 12.0,
        'cbm': 0.0385, 'upc': '677478694903', 'gtin': '60677478694905',
        'po_no': '25364', 'drawing': 'knobby_bowl',
        'material': 'Paper Mache', 'finish': 'Brown',
        'warnings': ['Non-Food Use (vessel shape)', 'Fragile (all 4 sides)']
    },
    {
        'item_no': '21496-04', 'nac_code': 'BE21496-01',
        'description': '12X12" PAPER MACHE KNOBBY FOOTED BOWL, TAUPE',
        'case_qty': '2 PCS', 'total_qty': 800, 'total_cartons': 400,
        'box_L': 14.0, 'box_W': 14.0, 'box_H': 12.0,
        'cbm': 0.0385, 'upc': '677478725188', 'gtin': '60677478725180',
        'po_no': '25364', 'drawing': 'knobby_bowl',
        'material': 'Paper Mache', 'finish': 'Taupe',
        'warnings': ['Non-Food Use (vessel shape)', 'Fragile (all 4 sides)']
    },
    {
        'item_no': '21498-06', 'nac_code': 'BE21498-02',
        'description': '26X15" PAPER MACHE HANDLE VASE, TAUPE',
        'case_qty': '1 PC', 'total_qty': 300, 'total_cartons': 300,
        'box_L': 17.5, 'box_W': 17.5, 'box_H': 28.5,
        'cbm': 0.1430, 'upc': '677478725287', 'gtin': '60677478725289',
        'po_no': '25364', 'drawing': 'tall_handle_vase',
        'material': 'Paper Mache', 'finish': 'Taupe',
        'warnings': ['Non-Food Use (vessel shape)', 'Fragile (all 4 sides)']
    },
]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def brand_block(cx, y, scale=1.0):
    """Embed the ACTUAL Sagebrook Home brand logo extracted from the client protocol PDF.
    Original image is 2000×500px (aspect ratio 4:1).
    Default rendered width ~80mm, scaled proportionally."""
    logo_w = 80 * scale
    logo_h = logo_w * (500 / 2000)  # maintain aspect ratio
    logo_x = cx - logo_w / 2
    logo_y = y - logo_h * 0.7  # offset so vertical center aligns near y
    return f'<image x="{logo_x}" y="{logo_y}" width="{logo_w}" height="{logo_h}" xlink:href="{BRAND_LOGO_B64}" href="{BRAND_LOGO_B64}" preserveAspectRatio="xMidYMid meet"/>\n'


def long_panel(item, cx, top, pw, ph, show_ann=True):
    """Long side panel: brand, item#, case qty, description, dimensions, barcode, origin."""
    svg = ""
    # Dimension annotations
    if show_ann:
        svg += f'<text x="{cx}" y="{top+10}" text-anchor="middle" font-size="5" font-family="Arial" font-weight="700" fill="#d32f2f" font-style="italic">{pw/IN:.1f}"</text>\n'
        svg += f'<text x="{cx - pw/2 + 5}" y="{top+ph/2}" text-anchor="middle" font-size="5" font-family="Arial" font-weight="700" fill="#d32f2f" font-style="italic" transform="rotate(-90,{cx - pw/2 + 5},{top+ph/2})">{ph/IN:.1f}"</text>\n'
    # Handling symbols top-right
    svg += handling_symbols_block(cx + pw/2 - 68, top + 5, 20)
    # Brand
    svg += brand_block(cx, top + 48)
    # Item info
    iy = top + ph*0.35
    svg += f'<text x="{cx}" y="{iy}" text-anchor="middle" font-family="Inter, Arial" font-size="11" font-weight="800" fill="#000">ITEM NO: {esc(item["item_no"])}</text>\n'
    svg += f'<text x="{cx}" y="{iy+14}" text-anchor="middle" font-family="Inter, Arial" font-size="10" font-weight="800" fill="#000">CASE QTY:  {esc(item["case_qty"])}</text>\n'
    # Description
    dy = iy + 32
    svg += f'<text x="{cx}" y="{dy}" text-anchor="middle" font-family="Inter, Arial" font-size="7.5" font-weight="600" fill="#222">DESC: {esc(item["description"])}</text>\n'
    dim_str = f'{item["box_L"]}"L x {item["box_W"]}"W x {item["box_H"]}"H'
    svg += f'<text x="{cx}" y="{dy+14}" text-anchor="middle" font-family="Inter, Arial" font-size="7.5" font-weight="600" fill="#222">DIMENSIONS: {dim_str}</text>\n'

    # Barcode bottom-left
    bc_x = cx - pw/2 + 8
    bc_y = top + ph - 42
    svg += item_label_above_barcode(item['item_no'], bc_x, bc_y - 7, 32, 3)
    bc_svg, bc_w = upc_barcode_svg(item['upc'], bc_x, bc_y, 0.33, 20, 3.5)
    svg += bc_svg

    # MADE IN INDIA
    svg += f'<text x="{cx}" y="{top + ph - 8}" text-anchor="middle" font-family="Inter, Arial" font-size="10" font-weight="800" fill="#000">MADE IN INDIA</text>\n'
    return svg


def short_panel(item, cx, top, pw, ph, show_ann=True):
    """Short side panel: brand, item#, case qty, logistics, product drawing, barcode, origin."""
    svg = ""
    if show_ann:
        svg += f'<text x="{cx}" y="{top+10}" text-anchor="middle" font-size="5" font-family="Arial" font-weight="700" fill="#d32f2f" font-style="italic">{pw/IN:.1f}"</text>\n'
        svg += f'<text x="{cx - pw/2 + 5}" y="{top+ph/2}" text-anchor="middle" font-size="5" font-family="Arial" font-weight="700" fill="#d32f2f" font-style="italic" transform="rotate(-90,{cx - pw/2 + 5},{top+ph/2})">{ph/IN:.1f}"</text>\n'
    # Handling symbols
    svg += handling_symbols_block(cx + pw/2 - 68, top + 5, 20)
    # Brand (smaller)
    svg += brand_block(cx, top + 44, scale=0.8)
    # Item info
    iy = top + ph*0.28
    svg += f'<text x="{cx}" y="{iy}" text-anchor="middle" font-family="Inter, Arial" font-size="9" font-weight="800" fill="#000">ITEM NO: {esc(item["item_no"])}</text>\n'
    svg += f'<text x="{cx}" y="{iy+11}" text-anchor="middle" font-family="Inter, Arial" font-size="8" font-weight="800" fill="#000">CASE QTY:  {esc(item["case_qty"])}</text>\n'
    # Logistics
    lx = cx - pw*0.35
    ly = iy + 26
    lh = 9
    cube_cuft = (item['box_L'] * item['box_W'] * item['box_H']) / 1728.0
    svg += f'<text x="{lx}" y="{ly}" font-family="Inter, Arial" font-size="7" font-weight="600" fill="#222">PO NO: {item["po_no"]}</text>\n'
    svg += f'<text x="{lx}" y="{ly+lh}" font-family="Inter, Arial" font-size="7" font-weight="600" fill="#222">CARTON NO: _____ OF _____</text>\n'
    svg += f'<text x="{lx}" y="{ly+2*lh}" font-family="Inter, Arial" font-size="7" font-weight="600" fill="#222">CARTON WEIGHT: _____ LBS</text>\n'
    svg += f'<text x="{lx}" y="{ly+3*lh}" font-family="Inter, Arial" font-size="7" font-weight="600" fill="#222">CUBIC FEET: {cube_cuft:.1f} CU FT</text>\n'

    # Product drawing
    dwg = DRAWINGS[item['drawing']]
    dwg_w = min(pw * 0.45, 50)
    dwg_h = min(ph * 0.22, 55)
    dwg_x = cx - dwg_w/2
    dwg_y = ly + 4*lh + 5
    svg += f'<svg x="{dwg_x}" y="{dwg_y}" width="{dwg_w}" height="{dwg_h}" viewBox="{dwg["vb"]}" fill="none" stroke="#000" stroke-linecap="round" stroke-linejoin="round">\n'
    svg += dwg['paths']
    svg += '\n</svg>\n'

    # Barcode bottom-right
    bc_x = cx + pw/2 - 45
    bc_y = top + ph - 42
    svg += item_label_above_barcode(item['item_no'], bc_x, bc_y - 7, 32, 3)
    bc_svg, bc_w = upc_barcode_svg(item['upc'], bc_x, bc_y, 0.33, 20, 3.5)
    svg += bc_svg

    # MADE IN INDIA
    svg += f'<text x="{cx}" y="{top + ph - 8}" text-anchor="middle" font-family="Inter, Arial" font-size="10" font-weight="800" fill="#000">MADE IN INDIA</text>\n'
    return svg


def generate_diecut(item):
    """Generate complete actual-size SVG die-cut layout."""
    L = item['box_L'] * IN
    W = item['box_W'] * IN
    H = item['box_H'] * IN
    flap = FLAP_DEPTH
    total_w = 2*L + 2*W
    total_h = flap + H + flap
    margin_top = 30
    margin_bottom = 15
    margin_lr = 10
    svg_w = total_w + 2*margin_lr
    svg_h = total_h + margin_top + margin_bottom
    bx = margin_lr
    by = margin_top

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{svg_w:.1f}mm" height="{svg_h:.1f}mm"
     viewBox="0 0 {svg_w:.1f} {svg_h:.1f}">
<rect width="{svg_w:.1f}" height="{svg_h:.1f}" fill="#fff"/>

<!-- Title -->
<text x="{svg_w/2}" y="{margin_top - 12}" text-anchor="middle" font-family="Inter, Arial" font-size="14" font-weight="900" fill="#d32f2f">{esc(item['item_no'])} : {item['box_L']} X {item['box_W']} X {item['box_H']} INCH</text>
<text x="{svg_w/2}" y="{margin_top - 3}" text-anchor="middle" font-family="Inter, Arial" font-size="6" fill="#888">{esc(item['description'])} | PO#{item['po_no']} | {item['total_cartons']} Cartons | {esc(item['material'])} - {esc(item['finish'])}</text>

<!-- Die-cut outline (cut line) -->
<rect x="{bx}" y="{by}" width="{total_w:.1f}" height="{total_h:.1f}" fill="none" stroke="#000" stroke-width="{STROKE_W}"/>

<!-- Fold lines -->
<line x1="{bx}" y1="{by+flap}" x2="{bx+total_w}" y2="{by+flap}" stroke="#000" stroke-width="{STROKE_W}" stroke-dasharray="{FOLD_DASH}"/>
<line x1="{bx}" y1="{by+flap+H}" x2="{bx+total_w}" y2="{by+flap+H}" stroke="#000" stroke-width="{STROKE_W}" stroke-dasharray="{FOLD_DASH}"/>
'''
    # Panel fold lines
    for px in [L, L+W, 2*L+W]:
        svg += f'<line x1="{bx+px:.1f}" y1="{by}" x2="{bx+px:.1f}" y2="{by+total_h:.1f}" stroke="#000" stroke-width="{STROKE_W}" stroke-dasharray="{FOLD_DASH}"/>\n'

    # Panels: Long1, Short1, Long2, Short2
    panels = [
        (0,       L, 'long',  True),
        (L,       W, 'short', True),
        (L+W,     L, 'long',  False),
        (2*L+W,   W, 'short', False),
    ]
    panel_top = by + flap
    for (offset, width, ptype, ann) in panels:
        cx = bx + offset + width/2
        if ptype == 'long':
            svg += long_panel(item, cx, panel_top, width, H, ann)
        else:
            svg += short_panel(item, cx, panel_top, width, H, ann)

    # Flap labels
    for (offset, width, _, _) in panels:
        fcx = bx + offset + width/2
        svg += f'<text x="{fcx}" y="{by+flap/2+2}" text-anchor="middle" font-size="4" font-family="Arial" fill="#ccc">TOP FLAP</text>\n'
        svg += f'<text x="{fcx}" y="{by+flap+H+flap/2+2}" text-anchor="middle" font-size="4" font-family="Arial" fill="#ccc">BOTTOM FLAP</text>\n'

    # Compliance notes at bottom
    warn_text = " | ".join(item.get('warnings', []))
    if warn_text:
        svg += f'<text x="{svg_w/2}" y="{svg_h - 4}" text-anchor="middle" font-size="4" font-family="Arial" fill="#c05621">APPLICABLE WARNINGS: {esc(warn_text)}</text>\n'

    # Overall dimensions
    svg += f'<text x="{svg_w/2}" y="{svg_h - 10}" text-anchor="middle" font-size="4.5" font-family="Arial" font-weight="600" fill="#888">TOTAL: {total_w/IN:.1f}" x {total_h/IN:.1f}" ({total_w:.0f} x {total_h:.0f} mm)</text>\n'

    svg += '</svg>\n'
    return svg


# ── Generate all SVGs ─────────────────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)

for item in items:
    svg = generate_diecut(item)
    fn = f"DieCut_v2_{item['item_no']}.svg"
    fp = os.path.join(OUTPUT_DIR, fn)
    with open(fp, 'w') as f:
        f.write(svg)

    L, W, H = item['box_L']*IN, item['box_W']*IN, item['box_H']*IN
    tw = 2*L + 2*W
    th = FLAP_DEPTH + H + FLAP_DEPTH
    print(f"✓ {fn}")
    print(f"  {item['description'][:50]}...")
    print(f"  Box: {item['box_L']}×{item['box_W']}×{item['box_H']}\" | SVG: {tw:.0f}×{th:.0f}mm ({tw/IN:.1f}\"×{th/IN:.1f}\")")
    print(f"  UPC: {item['upc']} | Cartons: {item['total_cartons']} | Drawing: {item['drawing']}")
    print()

print(f"All {len(items)} SVG files generated in: {OUTPUT_DIR}")
