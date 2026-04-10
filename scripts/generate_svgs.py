#!/usr/bin/env python3
"""
Generate actual-size SVG die-cut carton box printer sheets for CorelDraw.
All dimensions in mm (1 inch = 25.4 mm).
Each SVG represents the full flattened box surface at 1:1 scale.
"""

import os

OUTPUT_DIR = "/sessions/zealous-charming-bohr/mnt/Printing and Labeling"
IN = 25.4  # 1 inch in mm
FLAP_DEPTH = 3.0 * IN  # 3 inches for flaps (76.2mm)
STROKE_W = 0.5  # mm, die-cut line width
FOLD_DASH = "4,2"  # dashed line for fold marks

# ── Item data ──────────────────────────────────────────────────────────────
items = [
    {
        'item_no': '18236-01',
        'description': 'PAPER MACHE, 14" VASE WITH HANDLES, WHITE',
        'case_qty': '2 PCS',
        'box_L': 30.5, 'box_W': 15.5, 'box_H': 16.0,
        'po_no': '24966',
        'weight': '15',
        'cube': '4.38',
        'drawing_vb': '0 0 120 140',
        'drawing_paths': '''
            <ellipse cx="60" cy="132" rx="24" ry="4" stroke-width="1.6"/>
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
            <path d="M90 58 C102 54, 108 62, 106 72 C104 80, 98 84, 92 80" stroke-width="1.5"/>
        '''
    },
    {
        'item_no': '18236-02',
        'description': 'PAPER MACHE, 15" VASE WITH HANDLES, WHITE',
        'case_qty': '2 PCS',
        'box_L': 26.5, 'box_W': 13.5, 'box_H': 17.0,
        'po_no': '24966',
        'weight': '15',
        'cube': '3.52',
        'drawing_vb': '0 0 120 140',
        'drawing_paths': '''
            <ellipse cx="60" cy="133" rx="18" ry="4" stroke-width="1.6"/>
            <path d="M42 133 C42 128, 38 120, 30 108 C24 98, 20 88, 20 76" stroke-width="1.6"/>
            <path d="M78 133 C78 128, 82 120, 90 108 C96 98, 100 88, 100 76" stroke-width="1.6"/>
            <path d="M24 95 C40 92, 80 92, 96 95" stroke-width="1.0" opacity="0.7"/>
            <path d="M22 83 C40 80, 80 80, 98 83" stroke-width="1.0" opacity="0.7"/>
            <path d="M25 107 C40 104, 80 104, 95 107" stroke-width="1.0" opacity="0.7"/>
            <path d="M20 76 C20 65, 24 55, 32 46 C38 40, 42 36, 46 30" stroke-width="1.6"/>
            <path d="M100 76 C100 65, 96 55, 88 46 C82 40, 78 36, 74 30" stroke-width="1.6"/>
            <path d="M46 30 C45 26, 44 22, 43 18" stroke-width="1.6"/>
            <path d="M74 30 C75 26, 76 22, 77 18" stroke-width="1.6"/>
            <ellipse cx="60" cy="16" rx="18" ry="5" stroke-width="1.6"/>
            <path d="M28 55 C16 50, 12 60, 14 70 C16 78, 24 82, 30 76" stroke-width="1.5"/>
            <path d="M92 55 C104 50, 108 60, 106 70 C104 78, 96 82, 90 76" stroke-width="1.5"/>
        '''
    },
    {
        'item_no': '20655-01',
        'description': '24" PAPER MACHE JUG WITH HANDLES, WHITE',
        'case_qty': '1 PC',
        'box_L': 17.0, 'box_W': 17.0, 'box_H': 26.5,
        'po_no': '24966',
        'weight': '13',
        'cube': '4.43',
        'drawing_vb': '0 0 100 150',
        'drawing_paths': '''
            <ellipse cx="50" cy="143" rx="18" ry="4" stroke-width="1.5"/>
            <path d="M32 143 C32 138, 28 130, 22 118 C16 106, 14 94, 14 82" stroke-width="1.5"/>
            <path d="M68 143 C68 138, 72 130, 78 118 C84 106, 86 94, 86 82" stroke-width="1.5"/>
            <path d="M14 82 C14 70, 18 58, 26 48 C32 42, 36 36, 40 28" stroke-width="1.5"/>
            <path d="M86 82 C86 70, 82 58, 74 48 C68 42, 64 36, 60 28" stroke-width="1.5"/>
            <path d="M40 28 C39 22, 38 18, 37 14" stroke-width="1.5"/>
            <path d="M60 28 C61 22, 62 18, 63 14" stroke-width="1.5"/>
            <ellipse cx="50" cy="12" rx="14" ry="4.5" stroke-width="1.5"/>
            <path d="M22 56 C12 52, 8 60, 10 68 C12 74, 18 76, 22 72" stroke-width="1.4"/>
            <path d="M78 56 C88 52, 92 60, 90 68 C88 74, 82 76, 78 72" stroke-width="1.4"/>
        '''
    },
    {
        'item_no': '20656',
        'description': 'S/3 14/18/22" PAPER MACHE BOWLS, WHITE',
        'case_qty': '1 SET',
        'box_L': 24.0, 'box_W': 24.0, 'box_H': 12.5,
        'po_no': '24966',
        'weight': '20',
        'cube': '4.16',
        'drawing_vb': '0 0 160 75',
        'drawing_paths': '''
            <path d="M10 20 C10 50, 30 65, 80 65 C130 65, 150 50, 150 20" stroke-width="1.6"/>
            <ellipse cx="80" cy="18" rx="72" ry="12" stroke-width="1.5"/>
            <path d="M58 65 L58 70 L102 70 L102 65" stroke-width="1.3"/>
            <path d="M28 22 C28 42, 42 54, 80 54 C118 54, 132 42, 132 22" stroke-width="1.2" opacity="0.6"/>
            <path d="M44 24 C44 38, 54 46, 80 46 C106 46, 116 38, 116 24" stroke-width="1.0" opacity="0.4"/>
        '''
    }
]


# ── Handling symbols as SVG groups (reusable) ─────────────────────────────
def handling_symbols_svg(x, y, sym_size=18):
    """Generate 3 handling symbols (this-side-up, fragile, keep-dry) at position x,y.
    sym_size is the size of each symbol icon in mm."""
    s = sym_size
    gap = 2  # mm between symbols

    # This-Side-Up arrows
    up_arrow = f'''<g transform="translate({x},{y})">
      <rect x="0" y="0" width="{s}" height="{s}" fill="none" stroke="#000" stroke-width="0.3"/>
      <path d="M{s*0.29} {s*0.17} L{s*0.5} {s*0.04} L{s*0.71} {s*0.17}" stroke="#000" stroke-width="0.8" fill="none" stroke-linecap="round"/>
      <line x1="{s*0.5}" y1="{s*0.04}" x2="{s*0.5}" y2="{s*0.38}" stroke="#000" stroke-width="0.8"/>
      <path d="M{s*0.29} {s*0.58} L{s*0.5} {s*0.46} L{s*0.71} {s*0.58}" stroke="#000" stroke-width="0.8" fill="none" stroke-linecap="round"/>
      <line x1="{s*0.5}" y1="{s*0.46}" x2="{s*0.5}" y2="{s*0.79}" stroke="#000" stroke-width="0.8"/>
      <text x="{s*0.5}" y="{s*0.95}" text-anchor="middle" font-size="3" font-family="Arial" font-weight="600">THIS SIDE UP</text>
    </g>'''

    # Fragile glass
    fragile = f'''<g transform="translate({x + s + gap},{y})">
      <rect x="0" y="0" width="{s}" height="{s}" fill="none" stroke="#000" stroke-width="0.3"/>
      <path d="M{s*0.17} {s*0.92} L{s*0.83} {s*0.92}" stroke="#000" stroke-width="0.6"/>
      <path d="M{s*0.25} {s*0.92} L{s*0.25} {s*0.67} L{s*0.5} {s*0.42} L{s*0.5} {s*0.08}" stroke="#000" stroke-width="0.6" fill="none"/>
      <path d="M{s*0.75} {s*0.92} L{s*0.75} {s*0.67} L{s*0.5} {s*0.42}" stroke="#000" stroke-width="0.6" fill="none"/>
      <path d="M{s*0.33} {s*0.08} L{s*0.67} {s*0.08}" stroke="#000" stroke-width="0.6"/>
      <line x1="{s*0.35}" y1="{s*0.25}" x2="{s*0.65}" y2="{s*0.55}" stroke="#000" stroke-width="0.4" opacity="0.5"/>
      <line x1="{s*0.65}" y1="{s*0.25}" x2="{s*0.35}" y2="{s*0.55}" stroke="#000" stroke-width="0.4" opacity="0.5"/>
    </g>'''

    # Keep dry (umbrella)
    keep_dry = f'''<g transform="translate({x + 2*(s + gap)},{y})">
      <rect x="0" y="0" width="{s}" height="{s}" fill="none" stroke="#000" stroke-width="0.3"/>
      <path d="M{s*0.5} {s*0.08} L{s*0.5} {s*0.75}" stroke="#000" stroke-width="0.6"/>
      <path d="M{s*0.17} {s*0.42} C{s*0.17} {s*0.08}, {s*0.83} {s*0.08}, {s*0.83} {s*0.42}" stroke="#000" stroke-width="0.6" fill="none"/>
      <path d="M{s*0.5} {s*0.75} C{s*0.42} {s*0.75}, {s*0.38} {s*0.83}, {s*0.38} {s*0.88}" stroke="#000" stroke-width="0.5" fill="none"/>
      <line x1="{s*0.33}" y1="{s*0.17}" x2="{s*0.25}" y2="{s*0.25}" stroke="#000" stroke-width="0.4"/>
      <line x1="{s*0.58}" y1="{s*0.12}" x2="{s*0.5}" y2="{s*0.2}" stroke="#000" stroke-width="0.4"/>
    </g>'''

    # Dimension label below all symbols
    total_w = 3*s + 2*gap
    dim_label = f'<text x="{x + total_w/2}" y="{y + s + 5}" text-anchor="middle" font-size="4" font-family="Arial" font-weight="700">1" × 3.15"</text>'

    return up_arrow + fragile + keep_dry + dim_label


def generate_long_panel_content(item, cx, panel_top, panel_w_mm, panel_h_mm, show_dim_annotations=True):
    """Generate SVG content for a LONG (description) panel."""
    mid_x = cx
    content = ""

    # Dimension annotations (red, italic) - only on first pair
    if show_dim_annotations:
        content += f'<text x="{mid_x}" y="{panel_top + 10}" text-anchor="middle" font-size="5" font-family="Arial" font-weight="700" fill="#d32f2f" font-style="italic">{panel_w_mm/IN:.1f}"</text>\n'
        content += f'<text x="{cx - panel_w_mm/2 + 4}" y="{panel_top + panel_h_mm/2}" text-anchor="middle" font-size="5" font-family="Arial" font-weight="700" fill="#d32f2f" font-style="italic" transform="rotate(-90, {cx - panel_w_mm/2 + 4}, {panel_top + panel_h_mm/2})">{panel_h_mm/IN:.1f}"</text>\n'

    # Handling symbols (top-right corner)
    sym_x = cx + panel_w_mm/2 - 62
    sym_y = panel_top + 5
    content += handling_symbols_svg(sym_x, sym_y, sym_size=18)

    # Brand: SAGEBROOK HOME™
    brand_y = panel_top + 45
    content += f'<text x="{mid_x}" y="{brand_y}" text-anchor="middle" font-family="Playfair Display, Georgia, serif" font-size="14" font-weight="500" letter-spacing="3" fill="#000">SAGEBROOK HOME™</text>\n'
    content += f'<text x="{mid_x}" y="{brand_y + 12}" text-anchor="middle" font-family="Crimson Text, Georgia, serif" font-size="8" font-style="italic" fill="#222">Style That Makes a Statement</text>\n'

    # Item info centered
    info_y = panel_top + panel_h_mm * 0.38
    content += f'<text x="{mid_x}" y="{info_y}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="11" font-weight="800" fill="#000">ITEM NO.: {item["item_no"]}</text>\n'
    content += f'<text x="{mid_x}" y="{info_y + 14}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="10" font-weight="800" fill="#000">CASE QTY : {item["case_qty"]}</text>\n'

    # Description
    desc_y = info_y + 32
    content += f'<text x="{mid_x}" y="{desc_y}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="7.5" font-weight="600" fill="#222">DESCRIPTION : {item["description"]}</text>\n'

    # Dimensions
    dim_str = f'{item["box_L"]}"L x {item["box_W"]}"W x {item["box_H"]}"H'
    content += f'<text x="{mid_x}" y="{desc_y + 14}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="7.5" font-weight="600" fill="#222">DIMENSIONS : {dim_str}</text>\n'

    # MADE IN INDIA at bottom
    content += f'<text x="{mid_x}" y="{panel_top + panel_h_mm - 10}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="10" font-weight="800" fill="#000">MADE IN INDIA</text>\n'

    return content


def generate_short_panel_content(item, cx, panel_top, panel_w_mm, panel_h_mm, show_dim_annotations=True):
    """Generate SVG content for a SHORT (logistics + drawing) panel."""
    mid_x = cx
    content = ""

    # Dimension annotations
    if show_dim_annotations:
        content += f'<text x="{mid_x}" y="{panel_top + 10}" text-anchor="middle" font-size="5" font-family="Arial" font-weight="700" fill="#d32f2f" font-style="italic">{panel_w_mm/IN:.1f}"</text>\n'
        content += f'<text x="{cx - panel_w_mm/2 + 4}" y="{panel_top + panel_h_mm/2}" text-anchor="middle" font-size="5" font-family="Arial" font-weight="700" fill="#d32f2f" font-style="italic" transform="rotate(-90, {cx - panel_w_mm/2 + 4}, {panel_top + panel_h_mm/2})">{panel_h_mm/IN:.1f}"</text>\n'

    # Handling symbols
    sym_x = cx + panel_w_mm/2 - 62
    sym_y = panel_top + 5
    content += handling_symbols_svg(sym_x, sym_y, sym_size=18)

    # Brand (slightly smaller)
    brand_y = panel_top + 42
    content += f'<text x="{mid_x}" y="{brand_y}" text-anchor="middle" font-family="Playfair Display, Georgia, serif" font-size="11" font-weight="500" letter-spacing="2" fill="#000">SAGEBROOK HOME™</text>\n'
    content += f'<text x="{mid_x}" y="{brand_y + 10}" text-anchor="middle" font-family="Crimson Text, Georgia, serif" font-size="7" font-style="italic" fill="#222">Style That Makes a Statement</text>\n'

    # Item info
    info_y = panel_top + panel_h_mm * 0.30
    content += f'<text x="{mid_x}" y="{info_y}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="9" font-weight="800" fill="#000">ITEM NO.: {item["item_no"]}</text>\n'
    content += f'<text x="{mid_x}" y="{info_y + 12}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="8" font-weight="800" fill="#000">CASE QTY : {item["case_qty"]}</text>\n'

    # Logistics block (left-aligned within panel)
    log_x = cx - panel_w_mm * 0.35
    log_y = info_y + 28
    line_h = 10
    content += f'<text x="{log_x}" y="{log_y}" font-family="Inter, Arial, sans-serif" font-size="7" font-weight="600" fill="#222">P.O NO.: {item["po_no"]}</text>\n'
    content += f'<text x="{log_x}" y="{log_y + line_h}" font-family="Inter, Arial, sans-serif" font-size="7" font-weight="600" fill="#222">CARTON NO.: _____ OF _____</text>\n'
    content += f'<text x="{log_x}" y="{log_y + 2*line_h}" font-family="Inter, Arial, sans-serif" font-size="7" font-weight="600" fill="#222">CARTON WEIGHT : {item["weight"]} (LBS)</text>\n'
    content += f'<text x="{log_x}" y="{log_y + 3*line_h}" font-family="Inter, Arial, sans-serif" font-size="7" font-weight="600" fill="#222">CUBE : {item["cube"]} (CU FT)</text>\n'

    # Product line drawing
    dwg_w = min(panel_w_mm * 0.5, 55)  # drawing width in mm
    dwg_h = min(panel_h_mm * 0.25, 60)  # drawing height in mm
    dwg_x = mid_x - dwg_w/2
    dwg_y = log_y + 4*line_h + 5

    content += f'<svg x="{dwg_x}" y="{dwg_y}" width="{dwg_w}" height="{dwg_h}" viewBox="{item["drawing_vb"]}" fill="none" stroke="#000" stroke-linecap="round" stroke-linejoin="round">\n'
    content += item['drawing_paths']
    content += '\n</svg>\n'

    # MADE IN INDIA at bottom
    content += f'<text x="{mid_x}" y="{panel_top + panel_h_mm - 10}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="10" font-weight="800" fill="#000">MADE IN INDIA</text>\n'

    return content


def generate_svg(item):
    """Generate a complete actual-size SVG die-cut layout for one item."""
    L = item['box_L'] * IN  # Long side in mm
    W = item['box_W'] * IN  # Short side in mm
    H = item['box_H'] * IN  # Height in mm
    flap = FLAP_DEPTH

    # Total dimensions of the flattened die-cut
    total_w = 2 * L + 2 * W
    total_h = flap + H + flap

    # Add margin around the die-cut for title and bleed
    margin_top = 25  # mm for title
    margin_bottom = 10
    margin_lr = 10

    svg_w = total_w + 2 * margin_lr
    svg_h = total_h + margin_top + margin_bottom

    # Starting coordinates of the die-cut box
    bx = margin_lr
    by = margin_top

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{svg_w}mm" height="{svg_h}mm"
     viewBox="0 0 {svg_w} {svg_h}">

  <!-- White background -->
  <rect width="{svg_w}" height="{svg_h}" fill="#fff"/>

  <!-- Title: Item No : Box Dimensions -->
  <text x="{svg_w/2}" y="{margin_top - 8}" text-anchor="middle"
        font-family="Inter, Arial, sans-serif" font-size="14" font-weight="900" fill="#d32f2f">
    {item['item_no']} : {item['box_L']} X {item['box_W']} X {item['box_H']} INCH
  </text>

  <!-- ═══════════════ DIE-CUT OUTLINE ═══════════════ -->
  <!-- Outer rectangle (cut line) -->
  <rect x="{bx}" y="{by}" width="{total_w}" height="{total_h}"
        fill="none" stroke="#000" stroke-width="{STROKE_W}"/>

  <!-- Top flap fold line -->
  <line x1="{bx}" y1="{by + flap}" x2="{bx + total_w}" y2="{by + flap}"
        stroke="#000" stroke-width="{STROKE_W}" stroke-dasharray="{FOLD_DASH}"/>

  <!-- Bottom flap fold line -->
  <line x1="{bx}" y1="{by + flap + H}" x2="{bx + total_w}" y2="{by + flap + H}"
        stroke="#000" stroke-width="{STROKE_W}" stroke-dasharray="{FOLD_DASH}"/>

'''

    # Panel boundaries (vertical fold lines through full height)
    # Layout: Long1 | Short1 | Long2 | Short2
    panel_edges = [L, L + W, 2*L + W]
    for px in panel_edges:
        svg += f'  <line x1="{bx + px}" y1="{by}" x2="{bx + px}" y2="{by + total_h}" stroke="#000" stroke-width="{STROKE_W}" stroke-dasharray="{FOLD_DASH}"/>\n'

    svg += '\n  <!-- ═══════════════ PANEL CONTENT ═══════════════ -->\n\n'

    # Panel definitions: (offset_x, width, type)
    panels = [
        (0,           L, 'long',  True),
        (L,           W, 'short', True),
        (L + W,       L, 'long',  False),
        (L + W + W,   W, 'short', False),  # Wait, this should be 2L+W
    ]
    # Corrected:
    panels = [
        (0,             L, 'long',  True),   # Panel 1: Long
        (L,             W, 'short', True),   # Panel 2: Short
        (L + W,         L, 'long',  False),  # Panel 3: Long
        (2*L + W,       W, 'short', False),  # Panel 4: Short
    ]

    panel_top = by + flap
    panel_h = H

    for (offset, width, ptype, show_ann) in panels:
        cx = bx + offset + width / 2
        if ptype == 'long':
            svg += generate_long_panel_content(item, cx, panel_top, width, panel_h, show_ann)
        else:
            svg += generate_short_panel_content(item, cx, panel_top, width, panel_h, show_ann)

    # Flap labels (light grey text)
    for i, (offset, width, _, _) in enumerate(panels):
        flap_cx = bx + offset + width / 2
        # Top flap
        svg += f'  <text x="{flap_cx}" y="{by + flap/2 + 2}" text-anchor="middle" font-size="4" font-family="Arial" fill="#bbb">TOP FLAP</text>\n'
        # Bottom flap
        svg += f'  <text x="{flap_cx}" y="{by + flap + H + flap/2 + 2}" text-anchor="middle" font-size="4" font-family="Arial" fill="#bbb">BOTTOM FLAP</text>\n'

    # Dimension labels outside the die-cut
    # Total width arrow
    svg += f'''
  <!-- Overall dimension labels -->
  <text x="{bx + total_w/2}" y="{by + total_h + margin_bottom - 2}" text-anchor="middle"
        font-size="5" font-family="Arial" font-weight="700" fill="#666">
    TOTAL WIDTH: {total_w/IN:.1f}" ({total_w:.0f}mm) — TOTAL HEIGHT: {total_h/IN:.1f}" ({total_h:.0f}mm)
  </text>
'''

    svg += '\n</svg>\n'
    return svg


# ── Generate all SVGs ─────────────────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)

for item in items:
    svg_content = generate_svg(item)
    filename = f"DieCut_{item['item_no']}.svg"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(svg_content)

    # Calculate actual dimensions for reporting
    L = item['box_L'] * IN
    W = item['box_W'] * IN
    H = item['box_H'] * IN
    total_w = 2*L + 2*W
    total_h = FLAP_DEPTH + H + FLAP_DEPTH

    print(f"✓ {filename}")
    print(f"  Box: {item['box_L']}\" × {item['box_W']}\" × {item['box_H']}\"")
    print(f"  SVG actual size: {total_w:.0f} × {total_h:.0f} mm ({total_w/IN:.1f}\" × {total_h/IN:.1f}\")")
    print(f"  Panels: Long={L:.0f}mm ({item['box_L']}\"), Short={W:.0f}mm ({item['box_W']}\"), Height={H:.0f}mm ({item['box_H']}\")")
    print()

print("All SVG files generated in:", OUTPUT_DIR)
