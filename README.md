# Genie Agent CI/CD — Databricks Asset Bundle

A reference implementation for managing a **Databricks Genie Agent** and **Unity Catalog metric view** as code using [Databricks Asset Bundles (DAB)](https://docs.databricks.com/en/dev-tools/bundles/index.html).

This example uses the TPC-DS retail sales dataset to demonstrate the pattern without proprietary data. The same structure applies to any Genie Agent backed by a UC metric view.

## Why manage Genie Agent as code?

- **Version control** — track every change to instructions, SQL snippets, and benchmarks in git
- **Code review** — peer review agent behaviour changes before they reach production
- **Multi-environment promotion** — deploy to dev, staging, and prod with a single command and a `--target` flag
- **Reproducibility** — re-create the exact same agent configuration on any workspace

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
                     src/tpcds_retail.geniespace.json
                     (instructions, SQL snippets, benchmarks)
```

Two resources are managed by the bundle:
1. **UC Metric View** — dimensions, measures, and joins defined in `src/metric-view.yaml`
2. **Genie Agent** — instructions, SQL filters, example queries, and benchmarks in `src/tpcds_retail.geniespace.json`

---

## Repository layout

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

---

## Prerequisites

- Databricks CLI v1.10+ — install via `brew install databricks/tap/databricks`
- Authenticated: `databricks auth login --profile DEFAULT`
- Python 3.9+

---

## Quick start

### 1. Clone and configure

```bash
git clone https://github.com/anhhchu/genie-agent-cicd
cd genie-agent-cicd
```

Edit `databricks.yml` to point to your workspace and catalog:

```yaml
targets:
  dev:
    workspace:
      host: https://<your-workspace>.cloud.databricks.com
    variables:
      catalog: <your_catalog>
      schema: <your_schema>
```

### 2. Import your existing Genie Agent (first time only)

Find your Genie Agent's space ID from the URL in the browser:
```
https://<workspace>.cloud.databricks.com/genie/spaces/<SPACE_ID>
```

Then export it into the bundle:
```bash
databricks bundle generate genie-space \
  --existing-id <SPACE_ID> \
  --key <your_space_name>
```

This generates `src/<key>.geniespace.json` and `resources/<key>.genie_space.yml`.
Add the resource file to `include` in `databricks.yml` and commit both files.

### 3. Deploy

```bash
# Genie Agent + metric view job
databricks bundle deploy

# Apply metric view (first deploy or after metric-view.yaml changes)
databricks bundle run metric_view
```

---

## Making changes

### Update the UC metric view

Edit `src/metric-view.yaml` (add/change dimensions, measures, or synonyms), then:

```bash
python push_metric_view.py          # regenerates src/create_metric_view.sql
databricks bundle deploy
databricks bundle run metric_view   # runs CREATE OR REPLACE on the workspace
```

### Update the Genie Agent

Edit `src/tpcds_retail.geniespace.json` directly — the file is structured JSON with these sections:

```
instructions.text_instructions[0].content    agent behaviour rules (list of \r\n lines)
instructions.sql_snippets.filters            default filter snippets
instructions.sql_snippets.measures           custom measure expressions
instructions.sql_snippets.expressions        date/period expressions
instructions.example_question_sqls           example Q&A shown to users
benchmarks.questions                         evaluation benchmark questions + ground truth SQL
data_sources.tables[0].column_configs        column entity matching + format assistance config
```

Then deploy:

```bash
databricks bundle deploy   # no script needed — DAB reads geniespace.json directly
```

### Update space title, description, or warehouse

Edit `resources/tpcds_retail.genie_space.yml`, then deploy.

---

## Promoting to production

```bash
databricks bundle deploy --target prod
databricks bundle run metric_view --target prod
```

---

## Multiple Genie Agents

Each Agent uses its own `--key`, producing separate files that coexist in the bundle:

```bash
# Import a second Genie Agent
databricks bundle generate genie-space \
  --existing-id <SPACE_ID_B> \
  --key <space_b>
```

Add it to `databricks.yml`:

```yaml
include:
  - resources/metric_view.job.yml
  - resources/tpcds_retail.genie_space.yml
  - resources/<space_b>.genie_space.yml
```

---

## Re-sync from workspace

If you made changes in the UI and want to pull them back into source control:

```bash
databricks bundle generate genie-space \
  --existing-id <SPACE_ID> \
  --key tpcds_retail
```

Review the diff before committing.

---

## Related resources

- [Databricks Asset Bundles](https://docs.databricks.com/en/dev-tools/bundles/index.html)
- [Genie space resources in DAB](https://docs.databricks.com/aws/en/dev-tools/bundles/resources#genie_space)
- [Unity Catalog metric views](https://docs.databricks.com/en/lakehouse-architecture/metric-views.html)
- [TPC-DS benchmark](https://www.tpc.org/tpcds/)
