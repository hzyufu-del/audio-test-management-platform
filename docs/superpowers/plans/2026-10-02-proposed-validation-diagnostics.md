# Proposed Validation Diagnostics Implementation Plan

> For agentic workers: use subagent-driven-development and test-driven-development. Root reviews the task and runs complete offline verification.

**Goal:** Repair the confirmed diagnostic gap and clarify the legal output contract without relaxing the Proposed method or replaying Pilot-v1.

**Architecture:** Keep a bounded allowlisted validation summary in memory. An explicit Pilot-only option writes it to a new ignored audit file, outside business database fields and existing outcomes. Clarify the existing Prompt and version it as test-design-v3.

**Tech Stack:** Python, Pydantic, Flask/SQLAlchemy, pytest, Ruff.

## Global Constraints

- Zero real Provider requests; all generation tests inject FakeClient.
- Preserve every existing Pilot-v1 byte and the old report; external archive labels only.
- Preserve original instance files, formal dataset hashes, Schema, Baseline, evaluation criteria and migration head.
- Do not save raw invalid content, input/context/message from Pydantic errors, exception strings, headers, credentials or full prompts.
- One Provider call per attempt; max_retries=0; no semantic repair, retries or requirement-specific branches.
- Do not commit/push the Step 3-C work or old/new experiment results in this task.

## Evidence before implementation

- Smoke Run 2 succeeded under v2; Pilot Run 1/2 failed with real usage and finish_reason=stop, no validated snapshot/session/drafts.
- All three used v2 hash 47204e231b71bac5f94010b88e406f35bdf66e2f21d7cd1e06d28b9e6dfb3cf1.
- safe_error collapses JSON, Schema and safety rejection into one category. Historical field-level errors cannot be recovered.
- v2 example is legal; narrower quantity/text guidance is compatible. Missing explicit module, nonblank/null/nested-extra and limitation-item constraints justify generic clarification, not a claim about the actual old response.

## Task 1: Safe diagnostics, generic Prompt clarification and regression tests

**Files:** create app/services/test_design/diagnostics.py, dependency-free test_design_contract.py, tests/test_validation_diagnostics.py and tests/test_prompt_v3_contract.py; modify deepseek_provider.py, test_design_service.py, prompts.py, experiment/adapters.py, experiment/framework.py, scripts/run_pilot.py and affected current-version assertions in tests.

**Interfaces:** Provider.last_validation_summary is an optional safe dictionary containing stage, error_categories, field_paths, error_count and schema_error_codes. A sanitizer reconstructs only supported keys, fixed codes and known Schema path segments. Unknown extra-field names are replaced by a fixed marker. No summary field is added to GenerationRun.

- [x] Write tests and run RED before changing production code; save output to the new Step 3-C audit directory.
- [x] Extract validation errors without input/context/url; serialize only code, sanitized location and count. Distinguish json_invalid from other Schema errors.
- [x] Set/reset safe stages for API, truncation, absent content, Schema, safety and persistence paths. Safety summaries name only fixed rejection classes, not matched values.
- [x] Add --validation-diagnostics, default false; dry-run remains side-effect free. In new Pilot runs export only Proposed summaries to audit/<attempt>.validation.json, with existing attempt/run association tags. Sanitize again at export. No diagnostic is backfilled into old evidence.
- [x] Keep original Schema and fence compatibility. Clarify no null/extra keys, required nonblank strings except empty-string precondition, module length, limitation strings and JSON-only response. Set PROMPT_VERSION=test-design-v3 and keep plan/Run/Session current-version metadata aligned.
- [x] Use the dependency-free shared version constant in Prompt and plan; include that source file in manifest hashes so dry-run never initializes app/config.
- [x] Test all requested drift cases and legal JSON, prompt/example/hash consistency, malicious extra-field names, no invalid raw persistence, opt-in/off export and exactly one SDK invocation.
- [x] Test two clearly synthetic candidate failure envelopes: Schema rejection and safety rejection. They are alternative explanations compatible with old metadata, not recovered Pilot payloads.
- [x] Test new virtual authentication, upload, permission and numeric-boundary contexts, independent of formal inputs/references.
- [x] Run new and relevant tests GREEN and scoped Ruff; root independently reviews the diff before final verification.

## Task 2: Documentation, complete verification and report

**Files:** root updates current method/execution documentation and writes experiment/pilot/PILOT_FAILURE_ANALYSIS.md; existing PILOT_REPORT.md is protected.

- [x] Save comparison metadata and Schema audit tables with confirmed versus unresolved conclusions.
- [x] Document the opt-in summary, new Prompt/hash, unchanged Schema/evaluation/Baseline/data and historical v2 preservation.
- [x] Run ruff check . --no-cache and all AI Design/experiment tests.
- [x] Run complete pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90 with network calls blocked; retain threshold and original tests.
- [x] Run flask --app run.py db current and db check; read-only PRAGMA integrity_check and foreign_key_check.
- [x] Verify all old Pilot/report/original-instance/formal-data digests and absence of actual credentials in new artifacts.
- [x] Write report with ready/not ready for another separately authorized technical Pilot; stop without any real request or scoring.
