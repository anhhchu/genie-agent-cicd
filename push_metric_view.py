#!/usr/bin/env python3
"""Regenerate src/create_metric_view.sql from the YAML source of truth.

Source of truth : src/metric-view.yaml       (edit this)
Generated       : src/create_metric_view.sql  (committed; DAB deploys this)

Run this whenever metric-view.yaml changes, then commit both files and deploy:
    python push_metric_view.py
    databricks bundle deploy
    databricks bundle run metric_view
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
YAML = os.path.join(BASE, "src", "metric-view.yaml")
SQL  = os.path.join(BASE, "src", "create_metric_view.sql")
VIEW = "serverless_stable_dvmvgw_catalog.genie.tpcds_retail_sales_metrics"


def main() -> int:
    yaml = open(YAML).read()
    sql  = f"CREATE OR REPLACE VIEW {VIEW}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{yaml}\n$$\n"
    with open(SQL, "w") as f:
        f.write(sql)
    print(f"✓ regenerated {os.path.relpath(SQL, BASE)} from {os.path.relpath(YAML, BASE)}")
    print("  Next: databricks bundle deploy && databricks bundle run metric_view")
    return 0


if __name__ == "__main__":
    sys.exit(main())
