#!/usr/bin/env python3
"""Export the Labelforge OpenAPI schema to a JSON file.

Usage:
    python scripts/export_openapi.py              # writes to api/schema.json
    python scripts/export_openapi.py -o custom.json  # custom output path

The frontend can then generate TypeScript types from the schema:
    npx openapi-typescript api/schema.json -o src/lib/types.ts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Labelforge OpenAPI schema")
    parser.add_argument(
        "-o", "--output",
        default="api/schema.json",
        help="Output path for the schema JSON (default: api/schema.json)",
    )
    args = parser.parse_args()

    # Import app to get the generated OpenAPI schema
    from labelforge.app import app

    schema = app.openapi()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, default=str) + "\n")
    print(f"OpenAPI schema written to {output_path}")
    print(f"  Title: {schema['info']['title']}")
    print(f"  Version: {schema['info']['version']}")
    print(f"  Paths: {len(schema['paths'])}")
    print(f"  Schemas: {len(schema.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    main()
