#!/usr/bin/env python3
"""Resolve catalog/schema from databricks.yml and write substituted files to build/.

Parses catalog and schema directly from databricks.yml for the given target,
falling back to the top-level variable defaults if the target doesn't override them.

Source files use ${catalog} and ${schema} as placeholders — never edit build/ directly.

Files written to build/:
  build/tpcds_retail.geniespace.json   catalog/schema substituted
  build/.build_target                  records which target was built (safety check)

Note: The metric view SQL is no longer pre-generated here. The job now uses a
notebook task (src/create_metric_view.py) that reads src/metric-view.yaml and
substitutes catalog/schema from job parameters at runtime.

Usage:
    python3 prebuild.py                  # uses default target (dev)
    python3 prebuild.py --target prod
    python3 prebuild.py --verify prod    # verify build matches target (for CI)
    databricks bundle deploy [--target prod]
    databricks bundle run metric_view [--target prod]
"""
import argparse, os, re, sys

BASE  = os.path.dirname(os.path.abspath(__file__))
SRC   = os.path.join(BASE, "src")
BUILD = os.path.join(BASE, "build")
MARKER = os.path.join(BUILD, ".build_target")


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


def verify_marker(expected_target: str) -> int:
    """Check that build/ was generated for the expected target. Returns 0 on match, 1 on mismatch."""
    if not os.path.exists(MARKER):
        print(f"Error: build/ not found. Run: python3 prebuild.py --target {expected_target}", file=sys.stderr)
        return 1
    actual = open(MARKER).read().strip()
    if actual != expected_target:
        print(
            f"Error: build/ was generated for target '{actual}', but deploying to '{expected_target}'.\n"
            f"  Fix: python3 prebuild.py --target {expected_target}",
            file=sys.stderr,
        )
        return 1
    print(f"\u2713 build/ matches target '{expected_target}'")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="dev")
    parser.add_argument("--verify", metavar="TARGET",
                        help="Verify build/ matches TARGET without regenerating (for CI)")
    args = parser.parse_args()

    # Verify-only mode (for CI pre-deploy checks)
    if args.verify:
        return verify_marker(args.verify)

    catalog, schema = resolve_variables(args.target)
    os.makedirs(BUILD, exist_ok=True)

    # tpcds_retail.geniespace.json -> build/tpcds_retail.geniespace.json
    genie_out = substitute(open(os.path.join(SRC, "tpcds_retail.geniespace.json")).read(), catalog, schema)
    with open(os.path.join(BUILD, "tpcds_retail.geniespace.json"), "w") as f:
        f.write(genie_out)

    # Write marker so deploy can verify target consistency
    with open(MARKER, "w") as f:
        f.write(args.target + "\n")

    print(f"\u2713 build/ ready (target: {args.target}, {catalog}.{schema})")
    print(f"  Next: databricks bundle deploy --target {args.target} && databricks bundle run metric_view --target {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
