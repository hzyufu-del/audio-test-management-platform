# AI Test Design Assistant V1

## Feature positioning

AI Test Design Assistant V1 turns a bounded mock, demo, or sample requirement
into structured test points and editable TestCase drafts. AI output is a draft:
it does not auto-create a formal TestCase, execute a test, or determine whether
a real device works. The feature is a portfolio-scale assistant for human
testers, not a production requirement-management or autonomous testing system.

## Data flow

```text
Mock/demo/sample Requirement Text
        -> strict input validation
        -> TestDesignProvider
        -> strict Pydantic output validation
        -> deterministic local quality scoring
        -> TestDesignSession + pending TestCaseDraft rows
        -> human edit and review
        -> accept -> formal TestCase
        -> reject -> retained audit state only
```

Provider and schema failures happen before persistence. A successful generation
writes the Session and every Draft in one database transaction.

## Provider architecture

`TestDesignProvider.generate(TestDesignContext)` is separate from the existing
TestCase review provider. The context contains only the bounded title and
untrusted requirement text. It never contains database IDs, credentials,
local paths, logs, API keys, or internal configuration. The application owns
the fixed `test-design-v1` prompt version, validation, scoring, persistence,
and review workflow.

## Mock and DeepSeek

`MockTestDesignProvider` is the default. It is fully offline, deterministic,
and varies its output for connection, audio, power, network, OTA recovery,
and multi-device compatibility keywords. It always covers normal, negative,
and boundary scenarios.

`DeepSeekTestDesignProvider` is optional. It reuses the existing OpenAI-
compatible SDK configuration, reads its key only from local environment-backed
configuration, requests JSON output, disables model reasoning output, maps SDK
failures to safe messages, and still passes every response through the same
strict schema. `AI_ENABLED=false` prevents this external path; CI never needs a
real key or real network request.

## Strict output schema

Pydantic v2 models use `extra="forbid"`, bounded strings and lists, safe
suggested-code characters, project priority values, the existing `checklist`
case type, and explicit scenario enums. Malformed JSON, missing fields, extra
fields, empty required text, excessive list sizes, or unknown enum values are
rejected. The database stores only the validated structure, never the complete
Provider response, reasoning, or chain-of-thought.

## Deterministic quality scoring

The application calculates the final 0-100 score locally:

| Dimension | Points |
| --- | ---: |
| Structure completeness | 25 |
| Normal scenario | 15 |
| Negative scenario | 15 |
| Boundary scenario | 15 |
| Precondition quality | 10 |
| Executable steps | 10 |
| Observable expected result | 10 |

The detail page shows the total, each dimension, missing scenarios, and
deduction reasons. A low score is a review warning, not an automatic accept or
reject decision. Editing a pending Draft recomputes and persists the score in
the same transaction, so list and detail views stay consistent. A
model-reported score is neither requested nor trusted.

## Human review workflow

A pending Draft can be edited only through the allowlisted fields:
suggested code, title, module, priority, case type, scenario type,
precondition, steps, and expected result. Internal IDs, timestamps, status,
and the accepted TestCase link are not user-editable. The tester must confirm
the source requirement, fixture/device state, executable steps, and observable
result before acceptance.

## Accept and reject rules

Accept requires a pending Draft and an existing Session Version. The service
revalidates the current human-edited values and checks the Version-scoped
TestCase code. Creating the formal TestCase, marking the Draft accepted, saving
`accepted_test_case_id`, and recalculating Session status happen in one
transaction. A duplicate code or database failure rolls everything back.
Second acceptance is rejected.

Reject changes pending to rejected, creates no TestCase, and retains the Draft
as audit history. Rejected Drafts cannot be directly accepted or edited in V1.
The Session status comes from one deterministic function:

- all pending: `generated`
- pending plus any reviewed Draft: `partially_reviewed`
- no pending and at least one accepted: `accepted`
- all rejected: `rejected`

## Prompt-injection protection

Requirement Text is always untrusted data. Known instruction-like phrases are
recorded as a risk warning rather than treated as authority. The fixed provider
instructions require the model to ignore requests to change rules, reveal a
prompt or configuration, output credentials, alter the schema, or create
records. Input cannot select the Provider, change `test-design-v1`, modify
quality rules, or bypass the human acceptance transaction. Pages do not expose
the full fixed prompt.

## Data boundary

Only mock, demo, or sample requirements are accepted. Do not enter real company
names, internal projects, customer data, credentials, logs, screenshots,
device identifiers, local paths, or confidential requirements. Provider
context contains only title and requirement text. Stored data contains the
validated test points, limitations, drafts, provider name/model metadata,
prompt version, and local quality score.

Before an external Provider call, a deterministic safety gate rejects
credential assignments, token/key patterns, private-key material, absolute
local paths, raw multi-line log payloads, and explicit real
production/customer data. Validated Provider output passes the same gate
before any database write, so structurally valid secret, configuration, or
fixed-prompt leakage is rejected.

## Failure and rollback

Provider, JSON, or schema failures create no Session. Generation persistence
uses one transaction for the Session and all Drafts. Acceptance uses one
transaction for the TestCase and audit link. SQLAlchemy errors trigger rollback
and are converted to safe user messages; raw Provider content, SQL details,
configuration, and secrets are not displayed.

## Demo flow

1. Open **AI Test Design** and start a Session.
2. Select the matching mock Project and Version.
3. Enter a sample audio, connection, battery, OTA, or network requirement.
4. Review grouped test points, the local quality score, and limitations.
5. Edit one pending Draft.
6. Accept it and follow the formal TestCase link.
7. Confirm a second accept is rejected.
8. Reject another Draft and confirm no TestCase is created.
9. Try instruction-like text and confirm only a safe risk warning appears.

The seed provides one deterministic mock Session with normal, negative, and
boundary pending Drafts. Re-running `init-db` does not duplicate them.

## Limitations

V1 does not run tests, click a UI, use Appium, inspect images/audio, generate
pytest code, provide JWT/Swagger/WebSocket features, use RAG or a vector
database, or grant complex permissions. It does not confirm coverage against a
complete requirement set or validate real hardware behavior. Compatibility,
recovery, security, and edge scenarios still require human supplementation.

V1 exposes no Session deletion route or service operation, so supported
workflows preserve pending, accepted, and rejected Draft review history.
Direct administrative Session deletion is outside the supported V1 workflow:
the schema cascades its Draft rows but preserves any accepted formal TestCase.
Such deletion must therefore be an explicit database-administration decision,
not a silent application action.

## Interview talking points

- Provider abstraction isolates deterministic CI behavior from an optional
  external model.
- Strict Pydantic validation defines the trust boundary before persistence.
- Local scoring is explainable, repeatable, and independent of model claims.
- Session and Draft models preserve provenance and review status.
- Acceptance is an explicit human gate and an atomic database transaction.
- Prompt-injection text remains data and cannot control Provider, schema,
  scoring, prompt version, or TestCase creation.
- Mock/demo/sample-only data keeps the portfolio demonstration honest.
