# Export Labeling Automation System — Detailed Architecture

**AI-Powered Carton Box Printer Sheet Generation**
**Version 2.0 — Generic Architecture for Any Exporter-Importer Pair**
**Updated: Includes Warning/Compliance Labels, Checklists, Barcodes, and Carton Mockup Support**

---

## 1. Executive Summary

This document defines the architecture for an AI-powered system that automates the full export labeling workflow for export businesses. The system ingests Purchase Orders (PO), Proforma Invoices (PI), Client Protocols, Warning Label Specifications, Document Checklists, and Carton Mockup References from any combination of exporter and importer, then produces actual-size SVG die-cut printer sheets and determines all required compliance/warning labels — ready for the carton printer's CorelDraw workflow.

The core design principles are: (1) **the output format is fixed per importer, but the input formats vary wildly** — handled through adaptive AI-powered document ingestion on the input side and rigid template-driven rendering on the output side; and (2) **which warning/compliance labels apply to each SKU is determined automatically** by a rules engine that maps product attributes (material, type, weight, destination) to the importer's label requirements.

---

## 2. Problem Statement

Export labeling is a manual, repetitive, error-prone process. A typical exporter processes hundreds of SKUs per order across multiple importers, each with different brand guidelines, panel layouts, handling symbol requirements, and data fields. Today, a human team:

1. Reads POs (which arrive in different formats per importer)
2. Creates Proforma Invoices with carton specifications
3. Reads the client's protocol document for branding and layout rules
4. Manually designs die-cut printer sheets in CorelDraw — one per SKU
5. Draws product line illustrations by hand or from reference images
6. Reviews, revises, and sends files to the carton printer

This process takes 2–5 hours per order and is susceptible to data-entry errors, missed fields, inconsistent formatting, and deadline pressure.

---

## 3. System Overview

The system is organized into **four processing layers**, a **persistent data layer**, and two operational flows — **onboarding** (one-time per importer) and **production** (per order).

```
┌──────────────────────────────────────────────────────────────────┐
│                         INPUT SOURCES                            │
│  Purchase Order  │  Proforma Invoice  │  Protocol  │  Images     │
└────────┬─────────┴──────────┬─────────┴─────┬──────┴─────┬───────┘
         │                    │               │            │
┌────────▼────────────────────▼───────────────▼────────────▼───────┐
│              LAYER 1: DOCUMENT INGESTION                         │
│  Multi-Format Parser  │  AI Field Extractor  │  Image Processor  │
└────────┬────────────────────┬───────────────────────┬────────────┘
         │                    │                       │
┌────────▼────────────────────▼───────────────────────▼────────────┐
│                    DATA LAYER                                     │
│  PO Data  │  PI Data  │  Product Images  │  Importer Profile DB  │
└────────┬────────────────────┬───────────────────────┬────────────┘
         │                    │                       │
┌────────▼────────────────────▼───────────────────────▼────────────┐
│              LAYER 2: DATA FUSION & VALIDATION                   │
│  Merge PO+PI by SKU  │  Validate fields  │  Handle missing data │
└────────┬────────────────────┬───────────────────────┬────────────┘
         │                    │                       │
┌────────▼────────────────────▼───────────────────────▼────────────┐
│              LAYER 3: AI GENERATION ENGINE                        │
│  Line Drawing Gen  │  Die-Cut Composer  │  Text & Symbol Render  │
└────────┬────────────────────┬───────────────────────┬────────────┘
         │                    │                       │
┌────────▼────────────────────▼───────────────────────▼────────────┐
│              LAYER 4: OUTPUT & DELIVERY                           │
│  SVG Output Manager  │  Human Review Dashboard  │  Delivery API  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Input Documents — Characteristics & Challenges

### 4.1 Purchase Order (PO)

**Source:** Importer (buyer) sends to exporter.
**Formats:** PDF (most common), Excel, EDI, XML — varies per importer, and even per order from the same importer.
**Contains:** Item numbers, UPC/GTIN barcodes, product descriptions, product dimensions, net weights, case quantities, shipping instructions, compliance notes, and often embedded product photographs.
**Challenge:** No two importers use the same PO format. Field names, column positions, page layouts, and data groupings differ completely. Some POs are machine-generated (clean tabular data); others are PDFs with mixed text and images requiring vision-based parsing.

### 4.2 Proforma Invoice (PI)

**Source:** Exporter creates after receiving PO.
**Format:** Excel — controlled by the exporter, so the format is consistent within one exporting agency.
**Contains:** Carton outer dimensions (L×W×H), total cartons per SKU, CBM per carton and total, inner/outer pack counts, exporter item codes, product finish remarks, country of origin.
**Challenge:** Each exporter has their own PI template. The system needs to be configured once per exporter, then all PIs from that exporter follow the same structure.

### 4.3 Client Protocol

**Source:** Importer provides as a reference document (usually at the start of the business relationship).
**Format:** PDF with annotated photographs and diagrams — often bilingual (English + Chinese/Hindi).
**Contains:** Brand name treatment (font, size, spacing, trademark symbol), tagline, handling symbol specifications (which symbols, size in inches), panel layout rules (what goes on long sides vs short sides), label placement instructions ("ALL 4 SIDES"), packing standards, and sometimes showroom-specific requirements.
**Challenge:** Protocols use annotated images as the primary communication mechanism. The system must use **vision AI** to interpret these — reading callouts, arrows, boxed instructions overlaid on photographs.

### 4.4 Warning & Compliance Label Specifications

**Source:** Importer provides as part of their supplier documentation package.
**Format:** PDF with visual examples and text specifications.
**Contains:** The actual warning label designs, exact text, size requirements, and application rules for different product categories.
**Examples from real importers:**

- **PROP 65 Warning Label** — California-specific, required for items containing lead/lead compounds (MDF, plywood). Two variants: general product and furniture-specific, each with different URLs (P65Warnings.ca.gov/product vs /furniture).
- **FDA Non-Food Use Warning** — For functional-looking items that aren't food-safe (trays, bowls, jugs). Different wording for ceramic ("Not for Food Use – Food Consumed from this Vessel May be Harmful") vs non-ceramic ("For Decoration Only. Not Intended for Food Use."). Ceramic items require BOTH permanent marking AND stick-on label. Minimum font size: 3.2mm.
- **TSCA Warning Label** — For items with MDF/plywood shipping to USA.
- **Flameless Candle Warning** — For candle holders, hurricanes, votives, lanterns.
- **Candle Warning for Wax** — For candle items with actual wax.
- **Anti-tip Warning** — For shelves, consoles, cabinets. Required in 3 languages.
- **Law Tag Label** — For upholstered items including pillows. Required in 3 languages.
- **Plastic Bag Warning** — Multilingual (English + French) suffocation warning for plastic packaging.
- **Team Lift / Heavy Object Caution** — For cartons over 28 lbs (team lift) or 50 lbs (heavy caution).
- **Fragile Label** — Handling symbols required on all 4 sides.
- **Carton Part Count Label** — For multi-carton shipments ("CARTON: 1 of 2"), typically 6"×2", red background with white text.

**Challenge:** Each importer has their own set of warnings with specific wording, sizing, and visual design. The rules for WHICH labels apply depend on product attributes that must be inferred from the PO description and material specifications.

### 4.5 Document Checklist (Label Applicability Rules)

**Source:** Importer provides as a master reference document.
**Format:** PDF — a structured checklist mapping product attributes to required labels/documents.
**Contains:** A complete list of all possible labels and compliance requirements, each with a trigger condition describing which product types, materials, weights, or destinations require that label.
**Example trigger rules:**

| Label | Trigger Condition |
|---|---|
| TSCA Warning | Material contains MDF/plywood AND shipping to USA |
| PROP 65 Warning | Material contains MDF/plywood AND shipping to California |
| Law Tag | Upholstered items (incl. pillows) AND shipping to USA |
| Flameless Candle Warning | Product is candle holder, hurricane, votive, or lantern |
| Non-Food Use (Ceramic) | Ceramic items that could be mistaken as food vessels |
| Non-Food Use (Non-Ceramic) | Metal/glass/wood items that look functional but aren't food-safe |
| Anti-Tip Warning | Shelves, consoles, cabinets (3 languages) |
| Team Lift | Carton weight > 28 lbs |
| Heavy Object Caution | Carton weight > 50 lbs |
| Plastic Bag Warning | Items packed with plastic bags |
| Fragile | All fragile items (all 4 sides) |
| Carton Part Count | Products shipping in 2+ cartons per unit |
| UL/CUL marks | All lamp products |
| Window Box with Photo | All wall items including artworks |
| Eco-Friendly Hangtag | All ecomix products |

**Challenge:** The system must parse these rules and automatically determine which labels apply to each SKU based on PO data (material, product type, weight, destination). This is a classification problem that requires understanding product descriptions.

### 4.6 Carton Mockup References

**Source:** Importer provides as visual reference — either 3D renders or photographs of actual printed cartons.
**Format:** Images (JPEG, PNG) or PDF.
**Contains:** Shows how the final printed carton looks when assembled — all panels visible in 3D perspective, showing the spatial relationship between long sides, short sides, barcodes, handling symbols, and brand elements.
**Use:** Used during onboarding to validate the system's output against the client's visual expectations. Also reveals details that may not be explicit in the protocol — such as barcode placement (e.g., bottom-left on long side, bottom-right on short side), relative font sizes in context, and the overall visual density/spacing of the layout.
**Key insight from carton mockup analysis:** Barcodes (UPC-A with item number label) ARE printed directly on the carton surface — not just on sticker labels. The long side has a barcode at bottom-left; the short side has a barcode at bottom-right. This was not evident from the die-cut printer sheets alone.

### 4.7 Product Images

**Source:** Extracted from PO PDFs (embedded images), or uploaded separately by the exporter.
**Format:** JPEG, PNG — any raster format.
**Use:** The AI generates SVG line drawings (outline sketches) of each product for placement on the short-side panels of the die-cut. There is no pre-existing library of drawings — each is generated fresh by analyzing the product photograph.

### 4.8 Reference Printer Sheets (Onboarding Only)

**Source:** Actual die-cut layouts from past orders, prepared by the human team.
**Format:** PDF, CorelDraw files, or scanned images.
**Use:** Used exclusively during onboarding to teach the system the importer's exact output format. The AI analyzes these to extract: panel arrangement, font choices, text sizes, symbol placement, spacing rules, and overall composition style. Once the importer profile is built, these reference sheets are no longer needed.

---

## 4A. Document Classification Matrix

The system must handle a wide variety of documents from importers. Each document type is classified by when it's used (onboarding vs per-order), how it's parsed, and what it feeds into.

| Document Type | When Used | Format | Parser | Feeds Into |
|---|---|---|---|---|
| **Purchase Order (PO)** | Per order | PDF/Excel/EDI | AI Field Extractor | Order Data (items, UPCs, descriptions) |
| **Proforma Invoice (PI)** | Per order | Excel | Column-mapped Parser | Order Data (carton dims, CBM, weights) |
| **Client Protocol** | Onboarding (once) | PDF with images | Vision AI Analyzer | Importer Profile (brand, layout, symbols) |
| **Warning Label Specs** | Onboarding (once) | PDF | Warning Label Parser | Compliance Rules DB (label templates) |
| **Document Checklist** | Onboarding (once) | PDF | Checklist Rule Extractor | Compliance Rules DB (trigger conditions) |
| **Carton Mockup** | Onboarding (once) | Image/PDF | Vision AI Analyzer | Importer Profile (visual validation ref) |
| **Reference Printer Sheets** | Onboarding (once) | PDF/CDR/Image | Vision AI Analyzer | Importer Profile (output template) |
| **Product Images** | Per order (auto) | JPEG/PNG | Image Processor | Line Drawing Generator |
| **Handling Symbol Artwork** | Onboarding (once) | SVG/PNG/PDF | Image Vectorizer | Importer Profile (symbol library) |

**Key distinction:** Onboarding documents are processed once and stored in the Importer Profile. Per-order documents are processed for every new PO. The system auto-detects document type on upload and routes to the appropriate parser.

---

## 5. Component Architecture — Detailed Design

### 5.1 Layer 1: Document Ingestion

#### 5.1.1 Multi-Format Document Parser

**Purpose:** Convert any input document into a structured intermediate representation, regardless of its original format.

**Capabilities:**

- PDF text extraction using pymupdf (fitz) — handles both text-based and image-based PDFs
- PDF image extraction — pulls embedded product photographs with position metadata
- Excel/CSV parsing using pandas with auto-detection of header rows and data boundaries
- OCR pipeline (Tesseract or cloud OCR) as fallback for scanned documents
- EDI/XML parser for importers using electronic data interchange
- Document type auto-classification: given a file, determine whether it's a PO, PI, Protocol, or reference sheet

**Output:** Raw parsed content organized as:
```json
{
  "doc_type": "PO",
  "source_format": "PDF",
  "pages": [
    {
      "page_num": 1,
      "text_blocks": [...],
      "tables": [...],
      "images": [{"index": 0, "format": "jpeg", "data": "base64...", "bbox": [...]}]
    }
  ]
}
```

#### 5.1.2 Adaptive Field Extractor (AI-Powered)

**Purpose:** Map the raw parsed content from any document format into a standardized data schema. This is the most critical AI component — it must handle PO formats it has never seen before.

**Approach:** Uses a Large Language Model (LLM) with structured output to:

1. Receive the raw parsed content (text blocks, tables, images)
2. Understand the document's structure through contextual reasoning
3. Extract fields into a standard schema with confidence scores
4. Flag ambiguous or missing fields for human review

**Standard PO Schema (output):**
```json
{
  "po_number": "24966",
  "importer": "Sagebrook Home",
  "items": [
    {
      "item_no": "18236-01",
      "upc": "195437112737",
      "gtin": "00195437112737",
      "description": "Paper Mache, 14\" Vase with Handles, White",
      "product_dims": {"L": 12.0, "W": 8.5, "H": 14.0, "unit": "inch"},
      "net_weight": {"value": 4.5, "unit": "lbs"},
      "case_qty": 2,
      "total_ordered": 1200,
      "product_images": ["img_0.jpg"],
      "extraction_confidence": 0.95
    }
  ]
}
```

**Standard PI Schema (output):**
```json
{
  "exporter": "Nakoda Art and Craft",
  "pi_number": "NACSBH290126",
  "items": [
    {
      "item_no": "18236-01",
      "carton_dims": {"L": 30.5, "W": 15.5, "H": 16.0, "unit": "inch"},
      "carton_cbm": 0.125,
      "total_cartons": 600,
      "inner_pack": 1,
      "outer_pack": 2,
      "country_of_origin": "India",
      "remarks": "White finish"
    }
  ]
}
```

**Confidence-Based Routing:**

| Confidence | Action |
|---|---|
| ≥ 0.90 | Auto-accept, proceed to fusion |
| 0.70 – 0.89 | Highlight for quick human review |
| < 0.70 | Route to human data-entry queue |

#### 5.1.3 Product Image Processor

**Purpose:** Extract, clean, and index product images for downstream line-drawing generation.

**Pipeline:**
1. Extract all images from PO PDF using pymupdf
2. Classify each image: product photo vs logo vs decorative element
3. Remove backgrounds (isolate product on transparent/white background)
4. Assess image quality (resolution, clarity, angle suitability for line drawing)
5. Match to SKU using page position and surrounding text context
6. Store in product image index: `{item_no} → [image_path, quality_score]`

#### 5.1.4 Warning Label & Checklist Parser

**Purpose:** Ingest the importer's warning label specifications and document checklists, building a structured compliance rules database.

**Pipeline:**

1. **Checklist Parsing:** Read the document checklist (e.g., "SBH PO Documents Checklist") and extract each label requirement as a structured rule:
   ```json
   {
     "label_id": "prop65_product",
     "label_name": "PROP 65 Warning Label",
     "trigger": {
       "material_contains": ["MDF", "plywood"],
       "destination": ["California"]
     },
     "placement": "on_product_and_carton",
     "label_template_id": "prop65_product_v1"
   }
   ```

2. **Warning Label Template Extraction:** Read the warning label specification PDFs and extract:
   - Exact warning text (verbatim — legal compliance requires word-for-word accuracy)
   - Visual design: dimensions (e.g., 4×3"), colors, font sizes, border styles
   - Label artwork as SVG templates (e.g., the Prop65 yellow triangle, the Team Lift pictogram)
   - Variants: e.g., Prop65 has "product" vs "furniture" versions with different URLs
   - Application method: printed on carton, stick-on label, permanent marking, hangtag

3. **Material-Based Rule Extraction:** From FDA/Non-Food warnings, extract material-specific logic:
   ```json
   {
     "label_id": "fda_nonfood_ceramic",
     "trigger": {
       "material": ["ceramic"],
       "product_type_resembles_food_vessel": true
     },
     "warning_text": "Not for Food Use – Food Consumed from this Vessel May be Harmful",
     "application_methods": ["permanent_marking_AND_sticker"],
     "min_font_size_mm": 3.2
   }
   ```

4. **Multi-Carton Rule Extraction:** Parse rules about carton part count labels:
   - Trigger: items shipping in 2+ cartons per unit
   - Label design: "CARTON : 1 of 2" (red background, white text, 6"×2")
   - Requires knowing the number of cartons per unit from PI data

**Output:** A structured ComplianceRulesDB stored within the Importer Profile (see §5.2.1).

#### 5.1.5 Protocol Analyzer (AI-Powered, Vision)

**Purpose:** Extract brand rules and layout specifications from the client protocol — a one-time operation per importer.

**Approach:** Uses a multimodal LLM (vision + text) to:

1. Read each page of the protocol, including annotated photographs
2. Identify brand elements: name, trademark symbol, tagline, font family, font weight, letter spacing
3. Identify panel layout rules: what content goes on long sides vs short sides
4. Identify handling symbol requirements: which symbols, size, placement
5. Identify data field requirements: which fields appear on which panels
6. Extract any special instructions (showroom-specific labels, color coding)

**Output → Importer Profile (see §5.2):**
```json
{
  "brand": {
    "name": "SAGEBROOK HOME",
    "trademark": "™",
    "font": "Playfair Display",
    "weight": 500,
    "letter_spacing": "3px",
    "tagline": "Style That Makes a Statement",
    "tagline_font": "Crimson Text",
    "tagline_style": "italic"
  },
  "panel_layout": {
    "long_side": ["brand", "item_no", "case_qty", "description", "dimensions", "barcode_upc", "origin"],
    "short_side": ["brand", "item_no", "case_qty", "po_no", "carton_no", "weight", "cube", "product_drawing", "barcode_upc", "origin"],
    "barcode_config": {
      "long_side_placement": "bottom_left",
      "short_side_placement": "bottom_right",
      "barcode_type": "UPC-A",
      "include_item_no_label": true
    }
  },
  "handling_symbols": {
    "symbols": ["this_side_up", "fragile", "keep_dry"],
    "size": "1in × 3.15in",
    "placement": "top_right"
  },
  "output_specs": {
    "units": "mm",
    "flap_depth_inches": 3.0,
    "stroke_width_mm": 0.5,
    "fold_line_style": "dashed",
    "cut_line_style": "solid"
  }
}
```

### 5.2 Data Layer

#### 5.2.1 Importer Profile Database

**This is the single most important data structure in the system.** Each importer (buyer) has exactly one profile that defines everything about how their carton labels look. This profile is:

- **Created once** during onboarding (from protocol + reference printer sheets)
- **Fixed** for all subsequent orders from this importer
- **Versioned** — if the importer updates their protocol, a new version is created

**Profile Schema:**
```
ImporterProfile
├── importer_id: string (unique)
├── importer_name: string
├── brand_config: BrandConfig
│   ├── name, trademark, font, weight, spacing
│   ├── tagline, tagline_font, tagline_style
│   └── logo_svg: optional SVG
├── panel_layout: PanelLayout
│   ├── long_side_fields: ordered list of field types
│   ├── short_side_fields: ordered list of field types
│   ├── field_font_sizes: map of field → size
│   └── field_positions: relative positioning rules
├── handling_symbols: HandlingConfig
│   ├── symbols: list of symbol types
│   ├── symbol_style: enum (outline, solid_filled)
│   ├── dimensions: {width, height}
│   └── placement: enum (top_right, top_left, etc.)
├── barcode_config: BarcodeConfig
│   ├── type: enum (UPC-A, EAN-13, ITF-14)
│   ├── long_side_placement: enum (bottom_left, bottom_right, none)
│   ├── short_side_placement: enum (bottom_left, bottom_right, none)
│   ├── include_item_label: boolean
│   └── size: {width, height}
├── svg_template: SVGTemplateConfig
│   ├── units: enum (mm, inch)
│   ├── flap_depth: number
│   ├── stroke_widths: {cut, fold, panel_border}
│   ├── line_styles: {cut: solid, fold: dashed}
│   ├── margin_rules: spacing and padding
│   └── font_embed_mode: enum (text, curves)
├── compliance_rules: ComplianceRulesDB          ◀ NEW
│   ├── rules: list of ComplianceRule
│   │   ├── rule_id: string
│   │   ├── label_name: string
│   │   ├── trigger_conditions: TriggerCondition
│   │   │   ├── material_contains: list of strings (e.g., ["MDF","plywood"])
│   │   │   ├── product_type_in: list of strings (e.g., ["candle_holder","lantern"])
│   │   │   ├── destination_in: list of strings (e.g., ["California","USA"])
│   │   │   ├── weight_gt_lbs: number (e.g., 28, 50)
│   │   │   ├── multi_carton: boolean
│   │   │   └── custom_condition: string (free-text for AI evaluation)
│   │   ├── label_template: LabelTemplate
│   │   │   ├── warning_text: string (verbatim legal text)
│   │   │   ├── dimensions: {width, height, unit}
│   │   │   ├── artwork_svg: optional SVG string
│   │   │   ├── colors: {background, text, border}
│   │   │   └── min_font_size_mm: number
│   │   ├── application_method: enum (print_on_carton, sticker, hangtag,
│   │   │                             permanent_marking, sticker_AND_permanent)
│   │   ├── placement: string (e.g., "all_4_sides", "on_product", "inside_carton")
│   │   └── languages: list of strings (e.g., ["en","fr","es"])
│   └── universal_rules: list (rules that apply to ALL orders)
│       └── e.g., "Fragile label on all 4 sides", "SBH Carton Marks"
├── warning_label_templates: map of label_id → SVG/PDF artwork
├── carton_mockup_reference: optional image (3D carton photo for validation)
├── origin_text: string (e.g., "MADE IN INDIA")
├── special_rules: list of SpecialRule
│   └── e.g., "showroom-specific labels", "color coding per product line"
├── version: integer
├── created_at: timestamp
└── last_modified: timestamp
```

#### 5.2.2 Exporter Profile

Each exporter has a profile that defines their PI format, so the system knows how to parse it.

```
ExporterProfile
├── exporter_id: string
├── exporter_name: string
├── pi_format: PIFormatConfig
│   ├── file_type: enum (xlsx, csv)
│   ├── header_row: integer
│   ├── column_mapping: map of standard_field → column_name_or_index
│   └── sheet_name_pattern: regex (for multi-sheet workbooks)
└── default_country_of_origin: string
```

#### 5.2.3 Order Data Store

Per-order extracted and fused data:

```
OrderData
├── order_id: string
├── po_number: string
├── importer_id: FK → ImporterProfile
├── exporter_id: FK → ExporterProfile
├── items: list of CartonDataRecord
│   ├── item_no: string
│   ├── description: string
│   ├── case_qty: string (e.g., "2 PCS", "1 SET")
│   ├── product_dims: {L, W, H, unit}
│   ├── carton_dims: {L, W, H, unit}
│   ├── carton_cbm: number
│   ├── total_cartons: integer
│   ├── net_weight: number
│   ├── gross_weight: number (may be estimated)
│   ├── cube_cuft: number
│   ├── product_images: list of image paths
│   ├── line_drawing_svg: SVG string (generated)
│   ├── upc: string
│   ├── gtin: string
│   ├── product_material: string (e.g., "ceramic", "paper mache", "metal")
│   ├── product_category: string (e.g., "vase", "lantern", "shelf")
│   ├── destination_state: string (e.g., "California", "New York")
│   ├── applicable_warnings: list of ApplicableWarning     ◀ NEW
│   │   ├── rule_id: FK → ComplianceRule
│   │   ├── label_name: string
│   │   ├── application_method: string
│   │   ├── label_svg: string (rendered label artwork)
│   │   └── confidence: float (AI confidence in trigger match)
│   ├── barcode_data: BarcodeData                           ◀ NEW
│   │   ├── upc_a: string
│   │   ├── gtin_14: string
│   │   └── barcode_svg: string (pre-rendered barcode SVG)
│   └── data_source_map: map of field → source (PO/PI/Protocol/Estimated)
├── validation_report: ValidationReport
├── status: enum (ingested, validated, generated, reviewed, delivered)
└── timestamps: map of status → timestamp
```

### 5.3 Layer 2: Data Fusion & Validation

#### 5.3.1 Data Fusion Engine

**Purpose:** Combine data from PO and PI into unified CartonDataRecords, enriched with importer profile rules.

**Process:**

1. **SKU Matching:** Match PO items to PI line items by item number. Handle variations (dashes, leading zeros, alternate codes) using fuzzy matching with human confirmation for ambiguous matches.

2. **Field Merging Priority:**
   | Field | Primary Source | Fallback | Notes |
   |---|---|---|---|
   | Item Number | PO | PI | Canonical from PO |
   | Description | PO | — | As stated by importer |
   | Product Dimensions | PO | — | Product size, not carton |
   | Carton Dimensions | PI | — | Outer carton size |
   | Case Quantity | PO | PI | PO is authoritative |
   | Total Ordered | PO | — | — |
   | Total Cartons | PI | Calculated | = total_ordered / case_qty |
   | CBM | PI | Calculated | = L×W×H in meters |
   | Cube (CU FT) | PI | Calculated | = CBM × 35.3147 |
   | Net Weight | PO | PI | — |
   | Gross Weight | PI | Estimated | See §5.3.3 |
   | UPC/GTIN | PO | — | — |
   | Country of Origin | PI | Exporter default | — |
   | Product Images | PO (extracted) | Uploaded | — |

3. **Panel Dimension Calculation:**
   - Long panel width = carton L
   - Short panel width = carton W
   - Panel height = carton H
   - Flap depth = from importer profile (typically 3")
   - Total die-cut width = 2×L + 2×W
   - Total die-cut height = flap + H + flap
   - Convert all to output units (mm) for SVG

4. **Derived Field Computation:**
   - Cube in cubic feet = (L × W × H) / 1728 (when L,W,H in inches)
   - CBM = (L × W × H) × 0.0000164 (when in inches)

#### 5.3.2 Validation & QC Engine

**Validation Rules:**

| Rule | Check | Severity |
|---|---|---|
| Item match | PO item# exists in PI | Critical |
| Carton ≥ Product | Carton L,W,H ≥ product L,W,H | Warning |
| UPC check digit | Validate UPC-A check digit algorithm | Critical |
| Weight sanity | Gross weight > net weight | Warning |
| CBM consistency | Calculated CBM ≈ stated CBM (±5%) | Warning |
| Required fields | All fields needed by importer profile are present | Critical |
| Image availability | Product image exists for each SKU | Warning |
| Quantity math | Total cartons × case qty = total ordered | Critical |

**Output:** Validation report with pass/fail per rule, severity, and suggested fixes.

#### 5.3.3 Missing Data Handler

The most common missing field is **carton gross weight** (includes product + packing material). This is typically not in any input document and requires human input or estimation.

**Estimation Strategies:**

1. **Historical average:** For repeat products, use gross weight from previous orders
2. **Category-based formula:** e.g., for "Paper Mache" products: gross_weight ≈ net_weight × 1.3 + (carton_volume × material_density_factor)
3. **Manual entry queue:** Flag for human input with pre-filled estimate
4. **Learning over time:** As humans correct estimates, improve the formula per product category

#### 5.3.4 Compliance Rules Engine (NEW)

**Purpose:** Automatically determine which warning labels, compliance stickers, hangtags, and special markings apply to each SKU in the order. This replaces the manual checkbox process where the exporter fills out the importer's document checklist.

**How it works:**

1. **Product Attribute Classification (AI-Powered):**
   For each SKU, the AI analyzes the PO description and extracts product attributes:
   ```json
   {
     "item_no": "18236-01",
     "material": ["paper_mache"],
     "product_type": "vase",
     "functional_resemblance": ["vessel", "container"],
     "is_food_vessel_lookalike": true,
     "is_ceramic": false,
     "contains_mdf_plywood": false,
     "is_upholstered": false,
     "is_lamp": false,
     "is_candle_related": false,
     "is_furniture": false,
     "is_wall_item": false,
     "uses_plastic_packaging": true,
     "multi_carton": false,
     "gross_weight_lbs": 15
   }
   ```
   The AI uses the product description, material field, and product category to infer these attributes. For ambiguous cases (e.g., is a "paper mache jug" a food vessel lookalike?), the system flags for human confirmation.

2. **Rule Evaluation:**
   Each compliance rule from the Importer Profile is evaluated against the product attributes:
   ```
   FOR each SKU in order:
     FOR each rule in importer.compliance_rules:
       IF rule.trigger_conditions MATCH sku.attributes:
         ADD rule to sku.applicable_warnings
         SET confidence based on attribute extraction confidence
   ```

3. **Destination-Aware Evaluation:**
   Some rules depend on the shipping destination (e.g., Prop65 only for California). The system reads the PO shipping address or asks the exporter to confirm the destination state.

4. **Output — Per-SKU Compliance Manifest:**
   ```json
   {
     "item_no": "18236-01",
     "applicable_warnings": [
       {
         "label": "Non-Food Use (Non-Ceramic)",
         "text": "For Decoration Only. Not Intended for Food Use.",
         "method": "sticker_or_hangtag",
         "confidence": 0.88,
         "reason": "Paper mache vase resembles food vessel"
       },
       {
         "label": "Plastic Bag Warning",
         "text": "WARNING: This bag is not a toy...",
         "method": "print_on_plastic_bag",
         "confidence": 0.95,
         "reason": "Items packed with plastic wrap"
       },
       {
         "label": "Fragile",
         "method": "handling_symbol_all_4_sides",
         "confidence": 1.0,
         "reason": "Universal rule for this importer"
       }
     ],
     "not_applicable": [
       "TSCA (no MDF/plywood)",
       "Prop65 (no MDF/plywood)",
       "Law Tag (not upholstered)",
       "Flameless Candle (not candle related)",
       "Anti-Tip (not furniture)",
       "Team Lift (weight 15 lbs < 28 threshold)"
     ]
   }
   ```

5. **Human Review of Compliance Decisions:**
   The compliance manifest is presented in the review dashboard with:
   - Green checkmarks for high-confidence applicable labels
   - Yellow flags for medium-confidence items requiring confirmation
   - A complete "not applicable" list so the reviewer can catch any missed labels
   - One-click override to add/remove any label

**Why this matters:** Missing a compliance label can result in shipment rejection at customs, retailer chargebacks, or legal liability. The rules engine ensures nothing is missed, while the human review provides a safety net.

#### 5.3.5 Barcode Generator (NEW)

**Purpose:** Generate print-ready barcode SVGs for each SKU, for placement on carton panels.

**Process:**
1. Read UPC-A code from PO data (12-digit)
2. Validate check digit
3. Generate barcode as SVG using standard UPC-A encoding
4. Add human-readable digits below bars
5. Add item number label above barcode
6. Size according to importer profile's barcode_config
7. Generate GTIN-14 / ITF-14 variant if required by importer

**Output:** Pre-rendered barcode SVG fragments stored in the CartonDataRecord, ready for placement by the Die-Cut Composer.

### 5.4 Layer 3: AI Generation Engine

#### 5.4.1 Product Line Drawing Generator

**Purpose:** Create clean SVG vector outline drawings of products from photographs. This is an AI-creative task with no pre-existing library.

**Architecture:**

```
Product Photo → Vision AI Analysis → Shape Description → SVG Path Generation → Style Normalization
```

**Step 1 — Vision AI Analysis:**
- Input: Product photograph (cleaned, background removed)
- Model: Multimodal LLM (e.g., Claude, GPT-4V) or specialized vision model
- Output: Structured description of the product's shape:
  ```json
  {
    "product_type": "vase",
    "overall_shape": "tall, bulbous lower body tapering to narrow neck with flared rim",
    "key_features": ["two curved handles at shoulder", "horizontal ridges on body", "footed base"],
    "symmetry": "bilateral",
    "proportions": {"width_to_height": 0.6, "neck_to_body": 0.25}
  }
  ```

**Step 2 — SVG Path Generation:**
- Uses the shape description to generate SVG `<path>` elements
- Builds the drawing from structural components: base → body → neck → rim → handles/features
- Uses Bezier curves for organic shapes, straight lines for geometric products
- Output is a viewBox-normalized SVG fragment

**Step 3 — Style Normalization:**
- Apply consistent stroke width (1.5–1.8px in viewBox coordinates)
- Black stroke, no fill (line drawing style)
- Proportional sizing to fit the drawing container in the short-side panel
- Optional: match style to reference drawings from importer profile

**Caching:** Generated drawings are cached per product (by item number) so repeat orders don't require regeneration.

#### 5.4.2 Die-Cut Layout Composer

**Purpose:** Assemble the complete actual-size SVG die-cut layout for one carton/SKU.

**This component is TEMPLATE-DRIVEN**, not AI-driven. It reads the importer profile and follows its rules deterministically.

**Process:**

1. Read the CartonDataRecord for the SKU
2. Read the ImporterProfile for the order's importer
3. Calculate physical dimensions:
   - Panel widths in mm (L × 25.4, W × 25.4)
   - Panel height in mm (H × 25.4)
   - Flap depth from profile
   - Total SVG canvas size
4. Draw structural elements:
   - Outer cut line (solid)
   - Fold lines (dashed) at flap boundaries and panel boundaries
   - Panel borders
5. For each panel (Long1, Short1, Long2, Short2):
   - Call the Text & Symbol Renderer with the panel type and data
   - Place the returned SVG content within the panel bounds
6. Add dimension annotations (red italic text showing panel sizes)
7. Output final SVG with real-world units (`width="Xmm" height="Ymm"`)

**Handling Different Box Shapes:**

| Box Shape | Condition | Panel Behavior |
|---|---|---|
| Rectangular | L ≠ W | Long panels wider than short panels |
| Square | L = W | All 4 panels equal width |
| Tall | H > L and H > W | Panels are portrait-oriented |
| Short/flat | H < L and H < W | Panels are landscape-oriented |

The composer handles all cases by simply using the actual dimensions — no special logic needed.

#### 5.4.3 Text & Symbol Renderer

**Purpose:** Render all text content and handling symbols as SVG elements within each panel.

**Text Rendering Approach:**
- All text is rendered as SVG `<text>` elements with specified font families
- Font metrics (character widths) are used to calculate line breaks and centering
- For CorelDraw compatibility, the SVG specifies font-family names that the printer must have installed (e.g., "Playfair Display", "Inter")
- Optional: convert text to `<path>` curves for font-independent output (increases file size but eliminates font dependency)

**Handling Symbol Library:**
- Built-in SVG definitions for standard international handling symbols:
  - This Side Up (ISO 780 arrows)
  - Fragile/Handle with Care (wine glass)
  - Keep Dry (umbrella)
  - Do Not Stack (crossed-out box)
  - Temperature sensitive (thermometer)
- Each symbol is a reusable SVG `<symbol>` or `<g>` element
- Size and placement controlled by importer profile

### 5.5 Layer 4: Output & Delivery

#### 5.5.1 SVG Output Manager

**Responsibilities:**

- Generate one SVG file per SKU per carton configuration
- Batch mode: generate all SVGs for an entire PO in one run
- File naming convention: `DieCut_{PO}_{ItemNo}.svg`
- Output format options:
  - SVG (primary — for CorelDraw import)
  - PDF (for email preview and archival)
  - PNG/JPEG preview (for dashboard display)
- Version control: each generation run is versioned; previous versions are archived
- Metadata embedding: SVG includes comments with generation timestamp, data sources, and version

#### 5.5.2 Human Review Dashboard

**A web-based interface for quality control before files go to the printer.**

**Features:**

- **Order queue:** List of pending orders with status (generated, in review, approved, sent)
- **Side-by-side view:** AI-generated SVG alongside reference sheets from the same importer
- **Field-level inspection:** Click any field on the die-cut to see its data source (PO line #, PI cell, etc.)
- **Edit mode:** Correct any field value; the SVG regenerates in real-time
- **Product drawing review:** View the AI drawing alongside the source photo; request regeneration with different parameters
- **Batch approval:** For experienced operators, approve entire POs with one click after a quick scan
- **Rejection & feedback:** Reject with annotated notes; feedback is stored and used to improve AI extraction

#### 5.5.3 Delivery & Integration

**Output delivery options:**

- **Email:** Send SVG files as attachments to the carton printer
- **FTP/SFTP:** Upload to printer's file server
- **Cloud folder:** Sync to shared Google Drive / Dropbox / OneDrive
- **API webhook:** Trigger downstream systems (ERP, WMS) when sheets are generated

**Integration points:**

- **Inbound webhook:** Receive PO notifications from ERP to auto-trigger the pipeline
- **Email ingestion:** Monitor a dedicated inbox for incoming PO PDFs; auto-ingest
- **ERP API:** Pull order data directly from ERP systems (SAP, Oracle, custom)
- **Audit trail:** Complete log of every action: who uploaded what, what was extracted, what was changed, who approved, when it was sent

---

## 6. Onboarding Flow — Adding a New Importer

This is the one-time setup process when an exporter begins working with a new importer (buyer).

### Step 1: Collect Reference Materials

The exporter provides:
- 2–5 actual printer sheets from past orders with this importer
- The importer's protocol document
- Any brand guidelines or font files
- **Warning label specifications** (all warning label PDFs from the importer)
- **Document checklist** (the master list mapping product types to required labels)
- **Carton mockup images** (photos or 3D renders of printed cartons for visual validation)
- Any regulatory documents (FDA warnings, Prop65 text, TSCA requirements)

### Step 2: AI Analyzes Reference Sheets

The Protocol Analyzer:
- Uses vision AI to read each reference printer sheet
- Identifies: panel arrangement, font choices, text sizes, symbol types, symbol placement, spacing
- Extracts the implicit "template" — the consistent structure across all reference sheets
- Outputs a draft ImporterProfile

### Step 3: AI Analyzes Protocol Document

The Protocol Analyzer:
- Reads every page of the protocol, interpreting annotated images
- Extracts brand configuration (name, font, tagline, trademark)
- Identifies panel content rules (what goes on long vs short sides)
- Maps handling symbol requirements
- Cross-validates against the template extracted from reference sheets

### Step 3b: AI Parses Warning Labels & Checklist (NEW)

The Warning Label & Checklist Parser:
- Reads the document checklist and extracts each label requirement as a structured rule with trigger conditions
- Reads all warning label specification PDFs and extracts exact text, dimensions, visual design
- Builds the ComplianceRulesDB with trigger conditions mapped to product attributes
- Stores warning label artwork as SVG templates for later rendering
- Cross-references: if the checklist mentions "Fragile label — all 4 sides" and the handling symbols config already includes fragile, they are linked rather than duplicated

### Step 3c: Carton Mockup Analysis (NEW)

The Vision AI analyzes carton mockup images to:
- Confirm barcode placement (e.g., bottom-left on long side, bottom-right on short side)
- Verify handling symbol style (outline vs solid filled icons)
- Check relative proportions and spacing that may not be explicit in the protocol
- Store the mockup as a reference for the human review dashboard

### Step 4: Human Reviews & Adjusts

A human operator reviews the generated ImporterProfile:
- Verifies font mappings (especially if the protocol specifies fonts by visual example rather than name)
- Confirms panel layout rules
- Adjusts any misinterpreted spacing or sizing
- Tests the profile by generating a sample die-cut from a known past order
- Compares the AI output against the actual reference sheet from that order

### Step 5: Profile Saved & Locked

Once validated, the profile is locked and versioned:
- All future orders from this importer use this profile
- Changes require explicit versioning (e.g., if the importer updates their branding)
- The profile includes metadata: who configured it, when, and which reference sheets were used

---

## 7. Production Flow — Processing an Order

This is the per-order automated pipeline.

### Step 1: Receive PO + PI

- PO arrives via email, API, or manual upload
- PI is created by the exporter and uploaded
- System auto-detects the importer from PO header/format
- Selects the correct ImporterProfile

### Step 2: Extract, Fuse & Classify

- Document Parser + AI Field Extractor process the PO
- PI Parser processes the PI using the exporter's column mapping
- Product images extracted from PO PDF
- Data Fusion Engine merges PO + PI data by SKU
- **Compliance Rules Engine classifies each SKU** — determines applicable warning labels based on material, product type, weight, and destination
- Barcode Generator creates UPC-A SVGs for each SKU
- Validation Engine runs all checks
- Missing data flagged (e.g., gross weight)
- **Compliance manifest generated per SKU** — lists all required labels with confidence scores

### Step 3: Generate Line Drawings

- For each SKU, the Line Drawing Generator:
  - Checks cache for existing drawing
  - If not cached: analyzes product photo → generates SVG outline
  - Human can review/regenerate if needed

### Step 4: Compose Die-Cut SVGs

- For each SKU, the Die-Cut Composer:
  - Reads the CartonDataRecord
  - Reads the ImporterProfile
  - Generates the actual-size SVG
  - Embeds all text, symbols, and product drawing

### Step 5: Review & Approve

- Generated SVGs appear in the dashboard
- Reviewer checks: data accuracy, layout correctness, drawing quality
- **Compliance manifest reviewed** — reviewer confirms/overrides which warning labels apply per SKU
- **Barcode verified** — UPC digits checked against PO
- Side-by-side comparison with carton mockup reference (if available)
- Approve, request revision, or manually edit
- Approved SVGs are stamped with reviewer ID and timestamp

### Step 6: Deliver to Printer

- Approved SVGs are delivered via configured channel (email, FTP, cloud)
- Audit log records delivery
- Order status updated to "delivered"

---

## 8. Technology Stack — Recommended

| Component | Technology | Why |
|---|---|---|
| **LLM / Vision AI** | Claude API (Anthropic) | Strongest multimodal capabilities for document understanding, structured extraction, and vision-based protocol analysis |
| **PDF Processing** | pymupdf (fitz) | Fast, reliable PDF text and image extraction; no Java dependency |
| **Excel Processing** | pandas + openpyxl | Industry standard for Excel parsing in Python |
| **SVG Generation** | Pure Python (string templates or svgwrite) | SVG is XML — direct generation gives full control; no rendering engine needed |
| **OCR (fallback)** | Tesseract OCR or Google Vision API | For scanned documents that pymupdf can't extract text from |
| **Backend** | Python (FastAPI) | Async API framework; native Python ecosystem for AI/ML libraries |
| **Database** | PostgreSQL + JSON columns | Relational + flexible JSON for profile schemas and extracted data |
| **File Storage** | S3-compatible (AWS S3, MinIO) | Scalable storage for SVGs, source documents, and product images |
| **Task Queue** | Celery + Redis | Async processing for document ingestion and SVG generation |
| **Dashboard** | React + Tailwind CSS | Modern web UI for the review dashboard |
| **Deployment** | Docker + Kubernetes | Containerized services, scalable under load |
| **Monitoring** | Prometheus + Grafana | Track extraction accuracy, generation times, approval rates |

---

## 9. Data Flow Diagram — Single Order

```
PO (PDF) ──→ [PDF Parser] ──→ Raw Text + Images
                                    │
                                    ▼
                             [AI Field Extractor]
                                    │
                                    ▼
                              PO Data (JSON) ──────────────┐
                                                           │
PI (Excel) ──→ [Excel Parser] ──→ PI Data (JSON) ─────────┤
                                                           │
                                                           ▼
                                                  [Data Fusion Engine]
                                                           │
                                                           ▼
                                                  CartonDataRecord[]
                                                           │
               ┌───────────────────┬───────────────────────┤
               ▼                   ▼                        ▼
    [Line Drawing Gen]    [Die-Cut Composer]     [Validation Engine]
           │                       │                        │
           │              ┌────────┴────────┐               │
           └──────────────▶                 ◀───────────────┘
                          │  Final SVG per  │
                          │  SKU at actual  │
                          │  size (mm)      │
                          └────────┬────────┘
                                   │
                                   ▼
                          [Human Review Dashboard]
                                   │
                                   ▼
                          [Delivery to Printer]
```

---

## 10. Scalability Considerations

### 10.1 Processing Volume

A typical mid-size exporter processes 10–30 orders per month, each with 5–50 SKUs. Peak load: ~1,500 SVGs/month. The system should handle this on a single server, but the architecture supports horizontal scaling.

### 10.2 AI Cost Management

The most expensive operations are LLM calls (field extraction and line drawing generation):
- **Field extraction:** ~1 LLM call per PO (batch all items in one prompt). Cost: ~$0.05–$0.20 per PO.
- **Line drawing generation:** ~1 call per unique product. Cost: ~$0.05–$0.15 per drawing.
- **Caching:** Line drawings are cached per product; repeat orders reuse cached drawings.
- **Protocol analysis:** ~1 call per importer onboarding. One-time cost.

### 10.3 Accuracy Targets

| Metric | Target | Measurement |
|---|---|---|
| Field extraction accuracy | ≥ 95% | % of fields auto-extracted correctly |
| Line drawing quality | ≥ 85% first-pass approval | % approved without regeneration |
| End-to-end auto-approval | ≥ 70% after 3 months | % of SVGs approved without edits |
| Processing time per order | < 5 minutes | From upload to SVGs in review queue |

---

## 11. Security & Compliance

- All uploaded documents (POs, PIs) contain commercially sensitive data — encrypted at rest and in transit
- Role-based access: operators see only their exporter's orders
- Audit trail is immutable — every action logged with timestamp and user ID
- SVG files include no sensitive data beyond what's printed on the physical carton (public-facing information)
- GDPR/data retention: configurable retention period; auto-purge of source documents after N months

---

## 12. Rollout Strategy

### Phase 1 — Proof of Concept (4–6 weeks)

- Single exporter, single importer
- Manual upload of PO + PI
- AI extraction + SVG generation
- Human review via basic web interface
- Target: generate sheets that match 90% of human-produced sheets

### Phase 2 — Multi-Importer Support (6–8 weeks)

- Onboard 3–5 additional importers
- Build onboarding workflow
- Refine AI extraction with feedback from Phase 1
- Add batch processing

### Phase 3 — Production Automation (4–6 weeks)

- Email/API-based PO ingestion
- ERP integration (if applicable)
- Automated delivery to printers
- Analytics dashboard

### Phase 4 — Scale & Optimize (ongoing)

- Add more exporters
- Fine-tune AI models with accumulated feedback
- Reduce human review rate toward 30%
- Add support for additional output formats (sticker labels, shipping marks)

---

## 13. Cost-Benefit Summary

### Current Manual Process (per order, ~15 SKUs)

| Activity | Time |
|---|---|
| Reading PO and extracting data | 30 min |
| Cross-referencing PI | 20 min |
| Designing 15 die-cut layouts in CorelDraw | 3–4 hours |
| Drawing product illustrations | 1–2 hours |
| Review and corrections | 30 min |
| **Total** | **5–7 hours** |

### Automated Process (per order, ~15 SKUs)

| Activity | Time |
|---|---|
| Upload PO + PI | 2 min |
| AI processing (automated) | 3–5 min |
| Human review and approval | 15–30 min |
| **Total** | **20–35 minutes** |

**Time savings: 85–90% per order.** For an exporter processing 20 orders/month, this saves approximately 100–120 person-hours per month.

---

*This architecture is designed to be exporter-agnostic and importer-agnostic. The system adapts to any document format through AI-powered extraction, while producing pixel-perfect output through fixed, template-driven rendering tied to each importer's profile.*
