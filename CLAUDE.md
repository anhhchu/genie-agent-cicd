# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A reference implementation for managing a **Databricks Genie Agent** and **Unity Catalog metric view** as code using [Databricks Asset Bundles (DAB)](https://docs.databricks.com/en/dev-tools/bundles/index.html). The demo dataset is TPC-DS retail sales.

## Key commands

```bash
# Resolve catalog/schema from databricks.yml and write substituted files to build/
# Must run before every bundle deploy — source files use ${catalog}/${schema} placeholders
python3 prebuild.py --target dev
python3 prebuild.py --target prod

# Deploy bundle (Genie Agent + metric view job) to dev (default)
databricks bundle deploy

# Deploy to production
databricks bundle deploy --target prod

# Run the metric view creation job (first deploy, or after metric-view changes)
databricks bundle run metric_view
databricks bundle run metric_view --target prod

# Import an existing Genie Agent from a workspace into the bundle
databricks bundle generate genie-space --existing-id <SPACE_ID> --key <name>

# Re-sync from workspace (pull UI changes back to source)
databricks bundle generate genie-space --existing-id <SPACE_ID> --key tpcds_retail
```

## Architecture

```
src/metric-view.yaml          ← UC metric view source of truth (edit this)
      │
      │  python prebuild.py
      ▼
src/create_metric_view.sql    ← generated; committed to git; DAB deploys it
      │
      │  databricks bundle run metric_view
      ▼
UC Metric View  ←──────────  Genie Agent
                                  ▲
                  src/tpcds_retail.geniespace.json
```

Two resources managed by the bundle (declared in `resources/`):
- **UC Metric View** — a `CREATE OR REPLACE VIEW … WITH METRICS LANGUAGE YAML` job (`resources/metric_view.job.yml`) that runs `src/create_metric_view.sql`
- **Genie Agent** — declared in `resources/tpcds_retail.genie_space.yml`, content stored in `src/tpcds_retail.geniespace.json`

## Files to edit vs. files that are generated

| File | Status | How to change |
|------|--------|--------------|
| `src/metric-view.yaml` | Source of truth | Edit directly |
| `build/create_metric_view.sql` | **Generated** (gitignored) | Run `prebuild.py --target <target>` |
| `build/tpcds_retail.geniespace.json` | **Generated** (gitignored) | Run `prebuild.py --target <target>` |
| `src/tpcds_retail.geniespace.json` | Source of truth | Edit directly |
| `resources/tpcds_retail.genie_space.yml` | Config (title, warehouse, path) | Edit directly |
| `databricks.yml` | Bundle config, targets, variables | Edit to add targets or resources |

## Genie Agent JSON structure

`src/tpcds_retail.geniespace.json` sections:

```
instructions.text_instructions[0].content    — agent behaviour rules
instructions.sql_snippets.filters            — default filter snippets
instructions.sql_snippets.measures           — custom measure expressions
instructions.sql_snippets.expressions        — date/period expressions
instructions.example_question_sqls           — example Q&A shown to users
benchmarks.questions                         — evaluation benchmark Q&A + ground truth SQL
data_sources.tables[0].column_configs        — entity matching + format assistance
```

## Adding a second Genie Agent

```bash
databricks bundle generate genie-space --existing-id <SPACE_ID_B> --key <space_b>
```

Then add `resources/<space_b>.genie_space.yml` to the `include` list in `databricks.yml`.

## Prerequisites

- Databricks CLI v1.10+ (`brew install databricks/tap/databricks`)
- Authenticated: `databricks auth login --profile DEFAULT`
- Python 3.9+

## Variable defaults

Defined in `databricks.yml`. `catalog` and `schema` have top-level defaults; `warehouse_id` has no default and must be set per target via a name lookup. The lookup resolves against the target workspace at deploy time, so dev and prod can reference different warehouse names independently.
