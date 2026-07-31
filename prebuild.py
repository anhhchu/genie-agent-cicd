#!/usr/bin/env python3
"""Resolve catalog/schema from databricks.yml and write substituted files to build/.

Parses catalog and schema directly from databricks.yml for the given target,
falling back to the top-level variable defaults if the target doesn't override them.

Source files use ${catalog} and ${schema} as placeholders — never edit build/ directly.

Files written to build/:
  build/metric-view.yaml               catalog/schema substituted
  build/create_metric_view.sql         generated from build/metric-view.yaml
  build/tpcds_retail.geniespace.json   catalog/schema substituted

Usage:
    python3 prebuild.py                  # uses default target (dev)
    python3 prebuild.py --target prod
    databricks bundle deploy [--target prod]
    databricks bundle run metric_view [--target prod]
"""
import argparse, os, re, sys

BASE  = os.path.dirname(os.path.abspath(__file__))
SRC   = os.path.join(BASE, "src")
BUILD = os.path.join(BASE, "build")
VIEW  = "tpcds_retail_sales_metrics"


def resolve_variables(target: str) -> tuple[str, str]:
    text = open(os.path.join(BASE, "databricks.yml")).read()

    def extract(block: str, key: str) -> str | None:
        m = re.search(rf"^\s+{key}:\s*(\S+)", block, re.MULTILINE)
        return m.group(1) if m else None

    # Top-level variable defaults
    catalog = re.search(r"catalog:\s*\n\s+description:.*?\n\s+default:\s*(\S+)", text)
    schema  = re.search(r"schema:\s*\n\s+description:.*?\n\s+default:\s*(\S+)", text)
    catalog = catalog.group(1) if catalog else ""
    schema  = schema.group(1) if schema else ""

    # Target-level overrides — find the target block and extract its variables
    target_block = re.search(
        rf"^\s+{re.escape(target)}:\s*\n((?:[ \t]+.*\n?)*)", text, re.MULTILINE
    )
    if target_block:
        block = target_block.group(1)
        catalog = extract(block, "catalog") or catalog
        schema  = extract(block, "schema")  or schema

    if not catalog or not schema or catalog.startswith("<") or schema.startswith("<"):
        print(f"Error: catalog/schema not fully configured for target '{target}' in databricks.yml.", file=sys.stderr)
        sys.exit(1)
    return catalog, schema


def substitute(text: str, catalog: str, schema: str) -> str:
    return text.replace("${catalog}", catalog).replace("${schema}", schema)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="dev")
    args = parser.parse_args()

    catalog, schema = resolve_variables(args.target)
    os.makedirs(BUILD, exist_ok=True)

    # metric-view.yaml → build/metric-view.yaml
    yaml_out = substitute(open(os.path.join(SRC, "metric-view.yaml")).read(), catalog, schema)
    with open(os.path.join(BUILD, "metric-view.yaml"), "w") as f:
        f.write(yaml_out)

    # build/create_metric_view.sql — generated from substituted YAML
    sql = f"CREATE OR REPLACE VIEW {catalog}.{schema}.{VIEW}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{yaml_out}\n$$\n"
    with open(os.path.join(BUILD, "create_metric_view.sql"), "w") as f:
        f.write(sql)

    # tpcds_retail.geniespace.json → build/tpcds_retail.geniespace.json
    genie_out = substitute(open(os.path.join(SRC, "tpcds_retail.geniespace.json")).read(), catalog, schema)
    with open(os.path.join(BUILD, "tpcds_retail.geniespace.json"), "w") as f:
        f.write(genie_out)

    print(f"✓ build/ ready (target: {args.target}, {catalog}.{schema})")
    print(f"  Next: databricks bundle deploy --target {args.target} && databricks bundle run metric_view --target {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
