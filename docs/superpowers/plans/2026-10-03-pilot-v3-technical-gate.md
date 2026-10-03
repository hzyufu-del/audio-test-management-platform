# Pilot-v3 final technical gate execution plan

**Goal:** Verify a new four-request Pilot through generation, persistence, export, source validation and anonymous presentation.

**Architecture:** Keep the existing Baseline and Proposed adapters and frozen methods. Add only explicit Pilot-v3 version support and manifest labels before the baseline commit. Use a new ignored preflight directory and an exclusive new run directory. A one-shot controller caps SDK calls and HTTP POST dispatches at four and rejects duplicate attempt dispatches.

**Constraints:** Proposed `test-design-v3`; Baseline `baseline-v1`; no Prompt, Schema, scoring, formal requirements or formal reference changes. Same `deepseek-v4-pro`, endpoint, 8000 max tokens, 60 second timeout, thinking disabled, no temperature sent, SDK retries 0. Two original fictional requirements, AB/BA order, one attempt per pair. No push, rerun, Pilot-v4, formal experiment or human scoring.

## Preflight and baseline

- [ ] Review the initial diff, v2 report and preserved evidence. Explain the cross-field timestamp/log-level false positive and retained credential/source validation.
- [ ] Add tests for v3 loading, immutable four-attempt order and manifest labels; observe the missing-version failure, then minimally enable v3.
- [ ] Add an adapter counterexample with a wrong draft generation source; generation must remain succeeded while export fails.
- [ ] Hash all historical Pilot evidence, original instance files, local configuration and formal data. Check the two formal hashes against DATASET_README v1.0.
- [ ] Run `.venv/Scripts/python.exe -m pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90`; a full-regression failure stops Pilot-v3.
- [ ] Run `.venv/Scripts/ruff.exe check . --no-cache`, Flask `db current`, Flask `db check`, and read-only database integrity/foreign-key checks.
- [ ] Stage only reviewed source/tests/docs. Scan staged contents in memory for actual credentials. Commit a local baseline; require a clean source tree. Record the full SHA as `pilot_v3_base_commit`.

## Preparation and execution

- [ ] Create query/paging and state-transition Demo requirements with independent local loader reference fixtures; do not use formal references as input.
- [ ] Run the CLI dry run without loading `.env`, constructing a Provider or creating the run directory. Verify two requirements, two methods, four planned requests and AB/BA order.
- [ ] Freeze safe parameters, input/source/message hashes, controller, conversion rules and private anonymous mapping. Probe the controller using MockTransport with real sockets disabled.
- [ ] Recheck all protection hashes and the baseline. Execute the controller exactly once with explicit `--execute`; retain all failures and do not edit code between requests.

## Postflight

- [ ] Preserve primary artifacts before creating derived presentation files.
- [ ] Re-read the isolated SQLite in read-only mode. Verify Run/Session/Draft/snapshot/export/manifest identity and content. Count generation success and end-to-end success separately.
- [ ] Convert safe Baseline text using frozen literal transcription rules, retain missing fields and conversion provenance, and create anonymous nine-field batches without source metadata.
- [ ] Check four actual requests, zero retries, safe artifacts, unchanged historical/formal files, blank human scores and all sources/controls unchanged.
- [ ] Run Ruff and experiment tests. Write `experiment/pilot/PILOT_V3_REPORT.md` with the unique readiness field and evidence-supported results. Stop, even if ready.

The user's Step 3-E request supplies the approved design and execution authorization. This plan does not authorize any work beyond that request.
