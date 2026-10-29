# STAR–RSM Invoice Reconciliation

A portable OpenAI agent plugin that reconciles a STAR session-log CSV against an RSM invoice export at the session level.

It is designed to make invoice differences actionable: it reports missing sessions, session-count mismatches, exact and nonzero amount differences, and suspected duplicate STAR session slots. It never silently suppresses small discrepancies.

## Highlights

- Matches sessions by student ID and service date, not fragile service labels.
- Pairs same-count sessions by amount rank and reports count mismatches without guessing.
- Flags likely hour-rounding differences while retaining them as discrepancies.
- Checks suspected duplicate STAR slots using student, date, therapist, and session time.
- Runs locally with Python's standard library and processes only files the user provides.

## Package layout

```text
plugin.json
.agents/plugins/marketplace.json
plugins/star-rsm-invoice-reconciliation/
├── SKILL.md
├── agents/openai.yaml
└── scripts/reconcile.py
```

`plugin.json` is the portable Agent Plugins manifest. The marketplace entry makes the repository usable as a local or Git-backed plugin source for supported ChatGPT desktop and Codex clients.

## Use the reconciler

Run the included script with exports for one invoice:

```bash
python3 plugins/star-rsm-invoice-reconciliation/scripts/reconcile.py \
  --star path/to/star-session-log.csv \
  --rsm path/to/rsm-invoice.xls
```

The RSM `.xls` export is expected to contain its HTML table format. The script prints structured JSON; the accompanying skill turns those results into a concise reconciliation summary.

## Install from this repository

After cloning the repository, add its marketplace in a supported client:

```bash
codex plugin marketplace add https://github.com/punitraizada/star-rsm-invoice-reconciliation.git --sparse .agents/plugins
```

Then install **STAR–RSM Invoice Reconciliation** from the marketplace and start a new chat. Mention the skill directly as `$star-rsm-invoice-reconciliation`, or ask Codex or ChatGPT to reconcile a STAR and RSM invoice.

## Privacy

The plugin does not include credentials, client exports, or network access. Keep real invoice files outside the repository and review them under your organization's data-handling policies.

## Publishing

This repository is a public source package and marketplace. To list the plugin in the universal ChatGPT and Codex Plugins Directory, submit the package through OpenAI's plugin submission process.
