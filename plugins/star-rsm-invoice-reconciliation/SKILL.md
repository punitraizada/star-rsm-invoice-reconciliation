---
name: star-rsm-invoice-reconciliation
description: Reconcile one STAR session-log CSV against the corresponding RSM invoice `.xls` export, identify suspected duplicate STAR sessions, total gaps, missing sessions, session-count mismatches, and every nonzero amount difference. Use when asked to reconcile, cross-check, or explain differences between STAR and RSM invoice or session amounts.
---

# STAR–RSM Invoice Reconciliation

## Overview

Compare the two systems at the session level without hiding small discrepancies. Use `scripts/reconcile.py` to produce structured results, then provide a concise, actionable explanation.

## Gather inputs

1. Require an invoice ID before starting. If it is missing, ask: “Which invoice ID should I reconcile?”
2. Request both exports for that exact invoice. Do not log in, browse, or download them.
   - **STAR session log CSV:** In STAR’s Open Invoices page, find the invoice and download its session log CSV: `https://star.electronic-therapy.com/cc_invoice_listing.php?status=1`.
   - **RSM invoice export:** Open that invoice’s RSM details page and choose **Export → XLS**.
3. Stop until both files are attached. Confirm they refer to the same invoice and that the visible invoice total agrees with the summed line items where the export provides one.

## Reconcile

Run:

```bash
python3 scripts/reconcile.py --star <STAR-session-log.csv> --rsm <RSM-invoice.xls>
```

Run the script from this skill’s directory or provide its absolute path. It uses only Python’s standard library; RSM’s `.xls` export is parsed as its HTML table format.

Match by **student ID + service date**. Do not use service name as a key: STAR and RSM label equivalent services differently. When both sides have the same number of sessions for one student/date, pair amounts from largest to smallest. When counts differ, report the count mismatch instead of guessing a pairing.

Treat every nonzero amount difference as a discrepancy. RSM’s `Grand Total` is the comparable value; do not recompute it from subcolumns. Keep likely hours-rounding differences visible, while noting that RSM may round hours to two decimals before multiplying.

### Check for duplicate STAR sessions on the first pass

Inspect `duplicate_star_sessions` before explaining missing sessions or count mismatches. The script flags repeated **student ID + service date + therapist + start time + end time** slots, even when the service labels or amounts differ. These are suspected duplicates requiring review, not confirmed duplicate billings. Check them even when the invoice totals agree.

For each flagged slot, show the student ID, therapist, full date, shared start/end time, and **every STAR session ID, service/cancellation label, and amount** in the initial response. Compare the STAR and RSM counts and amount sets for that student/date, including RSM’s `No Show?` status. Explicitly call out conflicting attended-service and no-show/cancellation entries occupying the same slot. If times or therapist are missing or unusable, state that the duplicate check is incomplete; do not infer a shared time from the date alone. RSM may not export times, so do not claim its entry shares the STAR time unless supplied.

Known workflow, supplied by the user: **users may delete a duplicate session in RSM, but that deletion sends no message back to STAR**, leaving the extra STAR session in place. When duplicate STAR slots coincide with fewer RSM entries, explain this as a likely cause to check. The exports alone do not prove which session was deleted or which entry is valid. Identify the STAR IDs to review against the session documentation or RSM deletion history if available; do not select an entry for deletion solely from the amount or status. Reconcile all original rows without silently deduplicating or modifying either system.

Attribute the dollar gap at the student/date level without guessing a session pairing when counts differ. Do not count a duplicate flag and its count mismatch as separate dollar impacts, or add the same student/date gap more than once when it contains multiple duplicate slots.

## Present results

Do not paste raw JSON. Summarize in this order:

1. Give the invoice ID, both totals, dollar gap, and session counts.
2. Lead with suspected duplicate STAR slots, prioritizing those associated with the largest student/date gaps. Include session IDs and the shared date/time immediately, the related count mismatch, and the possible RSM-deletion explanation above.
3. List other sessions present only in one system, ordered by dollar impact, then remaining count mismatches with both sets of amounts. Refer back to already explained duplicate groups instead of repeating them.
4. Separate amount differences likely caused by hours rounding from differences requiring investigation.
5. State the exact-match count and the specific session IDs and checks needed to resolve the discrepancies.

If there are more than 15 discrepancies, summarize the pattern and offer the full list. Flag a recurring date shift, a suspiciously large recurring gap, or an apparent mismatch between STAR cancellation suffixes and RSM’s `No Show?` status.

The JSON includes `totals`, `duplicate_star_sessions`, `exact_matches`, `amount_mismatches`, `count_mismatches`, `only_in_star`, and `only_in_rsm`. `duplicate_star_sessions.count` counts suspected duplicate slots; `unchecked_session_count` counts STAR rows whose slot could not be checked. Count mismatches include full STAR and RSM row summaries for the initial explanation. Use the row data to identify student ID, session ID where available, date/time, service/status, and amount.
