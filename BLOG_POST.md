# Managing Databricks Genie Agent as Code with Databricks Asset Bundles

Databricks AI/BI Genie is a powerful natural-language analytics interface that lets business users ask questions in plain English and get answers backed by governed data. But as Genie Agents grow more sophisticated — with carefully crafted instructions, SQL filter snippets, example queries, and evaluation benchmarks — a new problem emerges: how do you manage all of that configuration reliably across environments?

If your team is editing agent instructions directly in the Genie UI, you have no version history, no code review, and no reliable path to promote changes from dev to production. One wrong update and there's no rollback.

In this post I'll show how to solve that using **Databricks Asset Bundles (DAB)** to manage a Genie Agent and its underlying Unity Catalog metric view entirely as code.

---

## The problem with UI-only Genie Agent management

A production-grade Genie Agent is more than a chatbot. It contains:

- **Text instructions** — rules governing how the agent interprets questions, resolves ambiguity, and formats responses
- **SQL filter snippets** — pre-built filters users can reference naturally ("show me US revenue")
- **Example queries** — Q&A pairs that teach the agent how to respond to common questions
- **Benchmark questions** — ground truth SQL used to evaluate answer quality
- **Column configs** — controls which columns get entity matching (so "germany" resolves to `Germany` in the Country dimension)

When all of this lives only in the UI, you get:

- No audit trail for who changed what and when
- No peer review before changes hit production
- No reliable way to promote the exact same configuration from dev to prod
- No rollback if a bad instruction update breaks query behaviour

The fix: treat the Genie Agent like any other piece of software — in source control, reviewed, and deployed through a pipeline.

---

## Solution overview: Databricks Asset Bundles

Databricks Asset Bundles (DAB) is Databricks' infrastructure-as-code framework. It supports jobs, pipelines, dashboards, and — as of CLI v1.10 — **Genie spaces** as first-class resources.

The approach has two key pieces:

1. **UC Metric View** — the semantic layer that backs the Genie Agent, defined in YAML
2. **Genie Agent** — the agent configuration (instructions, snippets, benchmarks), exported from the workspace and committed as JSON

Both are versioned in git and deployed via `databricks bundle deploy`.

---

## Architecture

```
                ┌─────────────────────────┐
   Edit YAML    │   src/metric-view.yaml  │  ← UC metric view source of truth
       │        └────────────┬────────────┘
       │                     │ push_metric_view.py
       ▼                     ▼
  src/create_metric_view.sql  ←  generated (committed to git)
       │
       │  databricks bundle deploy
       ▼
  UC Metric View  ←──────────  Genie Agent
                                    ▲
                     src/<space>.geniespace.json
                     (instructions, SQL snippets, benchmarks)
```

The metric view YAML is the single source of truth for dimensions and measures. A small Python script wraps it in the `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$` envelope and writes the SQL file. The Genie Agent config lives in a `.geniespace.json` file exported directly from the workspace using the CLI.

---

## Repository structure

```
genie-agent-cicd/
├── databricks.yml                        # bundle config, targets (dev/prod)
├── push_metric_view.py                   # generates src/create_metric_view.sql from YAML
│
├── resources/
│   ├── metric_view.job.yml               # job: CREATE OR REPLACE metric view
│   └── tpcds_retail.genie_space.yml      # Genie Agent resource definition
│
└── src/
    ├── metric-view.yaml                  # metric view source of truth (edit this)
    ├── create_metric_view.sql            # generated — do not edit directly
    └── tpcds_retail.geniespace.json      # Genie Agent content (edit directly)
```

The full example is on GitHub: [github.com/anhhchu/genie-agent-cicd](https://github.com/anhhchu/genie-agent-cicd)

---

## Step 1: Define your UC metric view in YAML

The metric view YAML defines dimensions, measures, and their synonyms. Synonyms are critical — they teach the Genie Agent which natural-language terms map to which columns.

```yaml
# src/metric-view.yaml
version: 1.1

source: serverless_stable_dvmvgw_catalog.genie.tpcds_all_sales

dimensions:
  - name: Channel
    expr: channel
    comment: "Sales channel: Store, Catalog, or Web"
    synonyms:
      - sales channel
      - division
      - segment

  - name: Category
    expr: category
    synonyms:
      - product category
      - department

measures:
  - name: Total Sales
    expr: SUM(net_paid)
    comment: "Total revenue after discounts, before tax"
    synonyms:
      - revenue
      - net sales
      - sales

  - name: Profit Margin
    expr: "SUM(net_profit) / NULLIF(SUM(net_paid), 0)"
    comment: "Net profit as a fraction of total sales (0.15 = 15%)"
    synonyms:
      - margin
      - profitability
```

When you're done editing, a small script wraps it in the DDL statement:

```bash
python push_metric_view.py
# ✓ regenerated src/create_metric_view.sql from src/metric-view.yaml
```

The generated SQL is committed to git alongside the YAML. Both are deployed by the bundle.

---

## Step 2: Export your Genie Agent from the workspace

If you already have a Genie Agent configured in the UI, the CLI can export it directly into your bundle. First, find the space ID in the browser URL:

```
https://<workspace>.cloud.databricks.com/genie/spaces/<SPACE_ID>
```

Then run:

```bash
databricks bundle generate genie-space \
  --existing-id <SPACE_ID> \
  --key tpcds_retail
```

This generates two files:

- `src/tpcds_retail.geniespace.json` — the full agent configuration
- `resources/tpcds_retail.genie_space.yml` — the DAB resource definition

The `.geniespace.json` file is structured JSON — not a raw blob — so every section is directly editable:

```json
{
  "version": 2,
  "instructions": {
    "text_instructions": [
      {
        "id": "...",
        "content": ["# Agent Instructions\r\n", "..."]
      }
    ],
    "sql_snippets": {
      "filters": [...],
      "measures": [...],
      "expressions": [...]
    },
    "example_question_sqls": [...]
  },
  "benchmarks": {
    "questions": [...]
  },
  "data_sources": {
    "tables": [
      {
        "identifier": "...",
        "column_configs": [...]
      }
    ]
  }
}
```

---

## Step 3: Configure the bundle for multiple environments

`databricks.yml` defines targets for each environment. A single `--target` flag promotes the exact same configuration to a different workspace with a different catalog:

```yaml
bundle:
  name: genie_agent_cicd

include:
  - resources/metric_view.job.yml
  - resources/tpcds_retail.genie_space.yml

variables:
  warehouse_id:
    lookup:
      warehouse: Serverless Starter Warehouse

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: DEFAULT
    variables:
      catalog: dev_catalog
      schema: genie

  prod:
    mode: production
    workspace:
      profile: PROD
    variables:
      catalog: prod_catalog
      schema: genie
```

---

## Step 4: Deploy

```bash
# Deploy Genie Agent + metric view job to dev
databricks bundle deploy

# Apply the metric view DDL
databricks bundle run metric_view

# Promote to prod
databricks bundle deploy --target prod
databricks bundle run metric_view --target prod
```

That's it. The Genie Agent and metric view are now live in the target workspace.

---

## Day-2 workflows

### Updating the Genie Agent instructions

Edit `src/tpcds_retail.geniespace.json` — for example, to add a new SQL filter snippet:

```json
"sql_snippets": {
  "filters": [
    {
      "id": "...",
      "display_name": "Store channel only",
      "sql": ["`channel` = 'Store'"],
      "synonyms": ["in-store", "brick and mortar"]
    }
  ]
}
```

Then:

```bash
databricks bundle deploy
```

No script needed — DAB reads `geniespace.json` directly and pushes the change.

### Updating a dimension or measure

Edit `src/metric-view.yaml`, regenerate, and deploy:

```bash
python push_metric_view.py
databricks bundle deploy
databricks bundle run metric_view
```

### Pulling UI changes back into source control

If someone made changes directly in the Genie UI (it happens), re-export:

```bash
databricks bundle generate genie-space \
  --existing-id <SPACE_ID> \
  --key tpcds_retail
```

Review the diff with `git diff` before committing.

---

## Managing multiple Genie Agents

Each agent uses its own `--key`, so multiple agents coexist in the same bundle without conflict:

```bash
databricks bundle generate genie-space \
  --existing-id <SPACE_ID_B> \
  --key finance_agent
```

Add the new resource to `databricks.yml`:

```yaml
include:
  - resources/metric_view.job.yml
  - resources/tpcds_retail.genie_space.yml
  - resources/finance_agent.genie_space.yml
```

Each agent's files are completely independent — `src/finance_agent.geniespace.json` and `resources/finance_agent.genie_space.yml`.

---

## Why this pattern works

**The metric view YAML is human-friendly.** Dimensions, measures, and synonyms are readable and diff well in pull requests. A reviewer can see exactly which synonym was added or which measure expression changed.

**The `.geniespace.json` is structured JSON, not a blob.** When DAB introduced the `genie-space` resource type, it made the agent config a proper file rather than a stringified JSON-inside-JSON. Every section — instructions, snippets, benchmarks, column configs — is a first-class JSON object you can edit and review.

**`bundle deploy` is the single deploy mechanism.** No custom scripts for pushing to the workspace, no manual API calls, no forgetting to update the etag. DAB handles state management, environment promotion, and workspace targeting.

**The separation is clean.** The metric view (semantic layer) and the agent config (behaviour layer) are in separate files with separate edit workflows. Changing a synonym doesn't require touching the agent instructions. Adding a benchmark question doesn't require regenerating SQL.

---

## Get started

The full working example is available on GitHub:

**[github.com/anhhchu/genie-agent-cicd](https://github.com/anhhchu/genie-agent-cicd)**

It includes the TPC-DS retail sales Genie Agent and metric view as a ready-to-deploy example. Clone it, swap in your workspace and catalog, import your own Genie Agent with `bundle generate`, and you have a CI/CD-ready Genie Agent in minutes.
