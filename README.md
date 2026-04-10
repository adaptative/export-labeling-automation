# Export Labeling Automation

An agentic AI system that automates the end-to-end preparation of export carton labels for Nakoda Art and Craft — from parsing purchase orders, proforma invoices, importer protocols and warning-label requirements, to generating printer-ready carton die-cut SVGs and client approval PDFs.

This repository contains the proof-of-concept scripts, extracted input artifacts, generated outputs for Purchase Order **PO#25364**, and the full system design document for building the production application.

## What's inside

```
export-labeling-automation/
├── scripts/                 # POC generators (Python, reportlab-based)
│   ├── gen_diecuts_v2.py           # Actual-size carton die-cut SVGs (mm units)
│   ├── gen_approval_pdfs.py        # Client approval PDFs with red dimension annotations
│   ├── gen_solution_doc.py         # Full 40-page solution design PDF
│   ├── gen_architecture.py         # System architecture diagram
│   └── generate_svgs.py            # Earlier SVG generator (kept for reference)
├── assets/
│   └── extracted/           # Handling symbols, brand logo, and warning assets
│                            # extracted from importer protocol PDFs
├── outputs/
│   ├── diecuts/             # 8 SKU die-cut SVGs (open in CorelDraw at 1:1 scale)
│   ├── approvals/           # 8 SKU client approval PDFs (red dim arrows)
│   └── docs/                # Solution design PDF + architecture diagram
├── docs/
│   └── System_Architecture_Document.md
├── requirements.txt
├── LICENSE                  # MIT
└── README.md
```

## The problem

Every export purchase order requires a matching carton label that merges inputs from four or five separate documents: the PO, the proforma invoice, the importer's packaging protocol, their warning-label requirements, and the importer's QA checklist. Today this is done manually in CorelDraw, one SKU at a time, with the operator copy-pasting SKU numbers, UPC barcodes, carton dimensions, item descriptions, country of origin, and handling symbols while cross-checking compliance rules (Prop 65, FDA Non-Food, TSCA, Team Lift, etc.). A single PO with 8–13 items typically takes half a day and is a common source of costly rework when a warning label is missed or a dimension is transcribed wrong.

## The proposed system

A multi-agent pipeline orchestrated with LangGraph, with 14 specialized agents covering intake, document parsing (PO / PI / protocol / warning labels / checklists), product image processing, fusion and validation, compliance rule evaluation, line-drawing generation, die-cut composition, approval-PDF composition, final validation, and an interactive Human-in-the-Loop chatbot for cases where documents are missing or a critical decision is needed. The full design, data schemas, Postgres DDL, REST/WebSocket API, 16-week implementation roadmap, and risks are in `outputs/docs/Export_Labeling_Automation_Solution_Design.pdf`.

## POC outputs

The POC scripts were run against PO#25364 (8 SKUs). The generated die-cut SVGs embed the exact handling symbols and company logo extracted from the importer's protocol PDF (not AI-generated approximations), use actual millimeter units, and open correctly in CorelDraw at 1:1 scale for printing. The approval PDFs match the reference format from `SAGEBROOK HOME 13 ITEM.pdf`, including the red dimension arrows and the `1"` / `3.15"` handling-symbol size callouts.

## Running the POC

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Generate die-cut SVGs for all 8 SKUs
python scripts/gen_diecuts_v2.py

# Generate client approval PDFs for all 8 SKUs
python scripts/gen_approval_pdfs.py

# Rebuild the solution design document
python scripts/gen_solution_doc.py
```

Outputs are written to `outputs/diecuts/`, `outputs/approvals/`, and `outputs/docs/` respectively.

## Status

Proof of concept. Die-cut and approval PDF generators are working end-to-end for PO#25364. The production system described in the solution design document is not yet implemented.

## License

MIT — see [LICENSE](LICENSE).
