---
name: pbc-package
description: Maps audit PBC request lists to support files, identifies gaps, drafts auditor responses, and assembles audit-ready evidence packages. Use when the user provides a PBC request list and a folder of support files and asks to match support to requests, identify missing items, flag duplicates or orphaned files, or draft responses to the auditor.
---

# PBC Package Assembly

Maps a "prepared by client" (PBC) audit request list to a folder of support files, identifies gaps, drafts responses to the auditor. Best run in Cowork — folder of files is the natural input.

## Required inputs

- **PBC request list** — XLSX, CSV, or PDF. Must include request number, description, period, owner (ideally), and priority/due date (ideally).
- **Support folder** — path to a folder containing supporting files (PDF, XLSX, CSV, DOCX, etc.). Subfolders allowed.

## Workflow

1. **Parse the PBC list.** Normalize into one record per request:
   - `request_id`, `description`, `period`, `requested_format` (document/spreadsheet/narrative), `owner`, `priority`, `due_date`

2. **Inventory the support folder.** Run `scripts/file_inventory.py`. For each file:
   - `path`, `name`, `extension`, `size_bytes`, `modified`
   - `summary` — 1-line description of contents (filename + first meaningful text snippet from the file)

3. **Match files to requests.** Run `scripts/match_pbc.py`. Confidence-scored matching using:
   - filename similarity to request description
   - content summary similarity to request description
   - period match (if files have datestamps in name/content)
   - file type match (a "schedule" request should match a spreadsheet, not a PDF narrative)

   Each potential match has a 0.0–1.0 confidence score.

4. **Classify each request.** Apply `materiality.pbc_match_confidence_threshold` (default 0.70):
   - `COMPLETE` — at least one match ≥ threshold
   - `PARTIAL` — has matches below threshold, or has one match where the request appears to want multiple items
   - `MISSING` — no candidate files
   - `MANAGEMENT_RESPONSE_REQUIRED` — request is for narrative or explanation, not a document (detected by keywords: "explain", "describe", "narrative", "memo", "policy")

5. **Identify orphaned files and duplicates.**
   - **Orphans** — files in the folder that didn't match any request. List them — they may be misnamed, extras, or from prior periods.
   - **Duplicates** — multiple files claiming to satisfy the same request. List for preparer to choose the right one.

6. **Draft auditor responses for `COMPLETE` requests.** Single sentence:
   - "Item #{request_id} ({description}) provided in `{filename}` (see Tab `{sheet_name}` if applicable)."

7. **Generate controller gap list.** Sorted by `priority` then `due_date`. Each `MISSING` and `PARTIAL` request gets:
   - what's missing or partial
   - who owns the request
   - what the preparer needs to find or create

8. **Output workbook tabs**:
   - `Cover` — period, audit firm, status, totals
   - `PBC_Source` — raw request list
   - `File_Inventory` — files in the support folder with summaries
   - `Matches` — every request with matched files, confidences, status
   - `Orphan_Files` — folder files that matched nothing
   - `Duplicates` — multiple files for the same request
   - `Gap_List` — sorted action list for the controller
   - `Draft_Responses` — one row per `COMPLETE` request with a draft response
   - `Evidence` — every match's source path and how the match was scored
   - `Review_Notes`

## Invariants

- **Never claim a file supports a request unless the match confidence exceeds threshold.** Below threshold is `PARTIAL` with a reviewer note, not `COMPLETE`.
- **Never invent a file location.** If you didn't see a file, don't reference it.
- **Orphans and duplicates are surfaced, never hidden.** The point is to make the package auditable, not impressive.

## When to say "I don't know"

- Support folder appears to be from a different period than the PBC list → stop and ask.
- More than 50% of files cannot be content-summarized (binary blobs, password-protected PDFs) → flag the inventory step as incomplete.
- Multiple files seem equally likely to satisfy a request and no metadata distinguishes them → list as `DUPLICATE`, ask the preparer to choose.
