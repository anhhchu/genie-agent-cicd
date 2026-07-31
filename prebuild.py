#!/usr/bin/env python3
"""Resolve catalog/schema from databricks.yml and regenerate derived files.

Reads catalog and schema from the target's resolved variables via:
    databricks bundle validate --target <target> --output json

Files updated:
  src/metric-view.yaml          updated source: field in-place
  src/create_metric_view.sql    regenerated from metric-view.yaml (do not edit)
  src/tpcds_retail.geniespace.json  catalog.schema substituted throughout

Usage:
    python push_metric_view.py                  # uses default target (dev)
    python push_metric_view.py --target prod
    databricks bundle deploy [--target prod]
    databricks bundle run metric_view [--target prod]
"""
import argparse, json, os, re, subprocess, sys

BASE   = os.path.dirname(os.path.abspath(__file__))
YAML   = os.path.join(BASE, "src", "metric-view.yaml")
SQL    = os.path.join(BASE, "src", "create_metric_view.sql")
GENIE  = os.path.join(BASE, "src", "tpcds_retail.geniespace.json")
VIEW   = "tpcds_retail_sales_metrics"


def resolve_variables(target: str) -> tuple[str, str]:
    cmd = ["databricks", "bundle", "validate", "--target", target, "--output", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)
    if result.returncode != 0:
        print(f"Error: databricks bundle validate failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    variables = data.get("variables", {})
    catalog = variables.get("catalog", {}).get("value")
    schema  = variables.get("schema", {}).get("value")
    if not catalog or not schema:
        print("Error: could not resolve 'catalog' or 'schema' from bundle variables.", file=sys.stderr)
        sys.exit(1)
    return catalog, schema


def update_metric_view_yaml(catalog: str, schema: str) -> None:
    text = open(YAML).read()
    text = re.sub(
        r"^(source:\s*).*$",
        f"source: {catalog}.{schema}.tpcds_all_sales",
        text,
        flags=re.MULTILINE,
    )
    with open(YAML, "w") as f:
        f.write(text)


def generate_sql(catalog: str, schema: str) -> None:
    yaml_content = open(YAML).read()
    fqn = f"{catalog}.{schema}.{VIEW}"
    sql = f"CREATE OR REPLACE VIEW {fqn}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{yaml_content}\n$$\n"
    with open(SQL, "w") as f:
        f.write(sql)


def update_geniespace_json(old_catalog: str, old_schema: str, catalog: str, schema: str) -> None:
    text = open(GENIE).read()
    # Replace any prior fully-qualified catalog.schema references
    old_prefix = re.escape(f"{old_catalog}.{old_schema}.")
    text = re.sub(old_prefix, f"{catalog}.{schema}.", text)
    with open(GENIE, "w") as f:
        f.write(text)


def current_fqn_prefix() -> tuple[str, str] | None:
    text = open(YAML).read()
    m = re.search(r"^source:\s*(\S+)\.(\S+)\.tpcds_all_sales", text, re.MULTILINE)
    if m:
        return m.group(1), m.group(2)
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="dev")
    args = parser.parse_args()

    catalog, schema = resolve_variables(args.target)
    old_catalog, old_schema = current_fqn_prefix()

    update_metric_view_yaml(catalog, schema)
    generate_sql(catalog, schema)

    if old_catalog and old_schema and (old_catalog != catalog or old_schema != schema):
        update_geniespace_json(old_catalog, old_schema, catalog, schema)
        print(f"✓ updated {os.path.relpath(GENIE, BASE)}: {old_catalog}.{old_schema} → {catalog}.{schema}")

    print(f"✓ regenerated {os.path.relpath(SQL, BASE)} (target: {args.target}, {catalog}.{schema})")
    print(f"  Next: databricks bundle deploy --target {args.target} && databricks bundle run metric_view --target {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
