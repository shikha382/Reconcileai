# Granite local experiment: measured evaluation

**Current status:** grounded-statement integration improved output acceptance to
60/60 across two 30-request runs. This is not an accuracy score. Independent
human quality validation is still pending, and missing-record explanations are
under-explained. Keep the feature local-only. Historical failed results below
are retained so the improvement is auditable.

## Initial result (before grounded-statement improvement)

**Implementation works as a guarded local experiment. Model-quality gate FAILED.**
Do not enable this on Railway or claim production readiness, finance accuracy,
or 90% accurate explanations. No deployment, push, credentials or paid service
was used. An independent human quality review remains outstanding.

## Environment and method

- Base: GitHub master `daa56af06a539b653477ae96db9e4844cf39b086`;
  uncommitted local implementation on `codex/granite-explanation`.
- Model: Ollama `granite4:3b`, model ID `89962fcc7523`, 2.1 GB package.
- Mac M1 / 8 GB; Ollama reported 2.3 GB runner memory, GPU, 2048 context.
  A system-memory observation reported 19% free; this is not continuous memory
  monitoring and does not establish absence of sustained memory pressure.
- Fixed 2048 context, 256 output tokens, temperature 0, non-streaming schema,
  60-second keep-alive, 120-second overall timeout, fixed loopback destination.
- Ten exceptions selected from the real **synthetic** 300-record pipeline run,
  repeated three times: rejected fee trap, clean match, missing transaction,
  ambiguous match, duplicate, partial settlement, over-settlement,
  under-settlement, refund mismatch and timing mismatch.
- Raw final outputs and exact fact snapshots: `granite-evaluation-results.json`.
  These are synthetic evaluation artifacts, not production logs.

## Final measured results

| Measurement | Result |
| --- | --- |
| Actual local model requests | 30 |
| Accepted Granite responses | 9/30 (30%) |
| Deterministic fallbacks | 21/30 (70%) |
| Accepted scenarios | Missing transaction, refund mismatch, timing mismatch; three repetitions each |
| Overall median response | 8.429 s |
| Warm responses | 29; load time below 200 ms |
| Warm median / nearest-rank p95 | 8.410 s / 11.812 s |
| Cold response | One sample: 9.343 s total; 3.399 s loading |
| Independent human-reviewed accuracy | Not established |
| 27/30 accurate-and-clear AI responses | **Not met**; only nine model responses passed guardrails |

Timing includes validation and any fallback construction, not just token
generation. Some CPU regression tests overlapped this run, so the latency is a
local observed result, not an isolated hardware benchmark or service guarantee.
No cold p95 or generation-throughput claim is made from one cold sample.

## Evidence review and limitations

Codex inspected every final response against its recorded facts. The nine
accepted answers preserve the supplied amounts and final decisions. Missing-record
answers distinguish the supported hypothesis from the still-unresolved case.
Refund/timing answers retain the existing safe-to-resolve decision. This is an
agent evidence review, **not independent human validation or a statistical
accuracy estimate**. JSON `human_review` fields remain null intentionally.

The other seven scenarios fell back on every repetition. Problems included:

- Treating hypothesis verification as verification of the entire reconciliation.
- Describing settlement amounts as fees.
- Presenting residual as raw expected-minus-observed, ignoring explained adjustments.
- Including policy-ID digits as unsupported numeric claims.
- Conservative rejection of an otherwise valid clean-match residual sentence.

Some rejected prose is genuinely misleading; some rejections are conservative
false positives. Do not interpret the 70% fallback rate as a 70% hallucination
rate. Do not count deterministic fallbacks as successful Granite answers.

Pilot development results are retained separately in `granite-pilot-results.json`.
That earlier 30-request run had 30 structurally accepted responses, but evidence
review found semantic scope errors. This demonstrated why schema success is not
accuracy. Earlier interrupted smoke experiments also explored no-number output;
they produced placeholders/Unicode substitutions and were abandoned. The final
version instead validates quoted decimal amounts and rejects ambiguous verification
claims. No silent model change was made.

## Regression and safety evidence

- Clean baseline: 862 backend tests, 22 frontend tests, production build passed.
- New backend test module covers disabled/production access, peer/host/origin/
  forwarded-header restrictions, unknown exceptions, body/query rejection,
  model absence, stopped Ollama, invalid output, amount/decision checks,
  concurrency and cancellation. A read-only test checks unchanged payment rows,
  audit-event count and stored decision representation after explanations.
- Frontend: 27 tests passed, including five new panel tests for click-only
  inference, fallback labelling, unavailable/retry, cancellation/late responses,
  and keyed-navigation clearing.
- Final backend suite: **891 passed** (862 existing + 29 new).
- Production build passed; emitted JS does not contain the panel heading.
- Both existing Playwright journeys passed against the real local app,
  including rejection of the synthetic INR 9.83 fee trap.
- Manual Chrome check: an exception's button produced a real Granite answer
  through Vite, FastAPI and Ollama; the original final decision stayed unresolved.
  Enter activated Retry and Cancel; cancellation announced its state. The panel
  was visually checked at desktop and 390 x 844 mobile width, then the viewport
  override was reset. This is not a comprehensive accessibility audit.
- Development dependency audit reports four existing findings (two moderate,
  two high). Production-only npm audit reports zero. No dependency upgrades or
  lockfile changes were made for this feature.

Keep this feature opt-in and local-only. The section below records the subsequent
quality iteration; the original failures above are retained, not overwritten.

## Grounded-statement improvement

The model now paraphrases four explicit, server-authored statements derived
from the same verified snapshot: classification, AI-hypothesis verification,
existing policy outcome and approval flag. It no longer receives money or raw
policy codes. The authoritative amounts remain visible in the existing UI.
No financial policy or validator restriction was relaxed, no model was swapped,
and no new service or dependency was added. The deterministic fallback now
explicitly labels its verification field as **hypothesis verification**.

Results on the original ten scenarios, three repetitions each:

- Actual requests: 30; accepted model responses: **30/30**; fallbacks: **0/30**.
- Warm responses: 29; warm median **2.726 s**, nearest-rank p95 **3.497 s**.
- Raw outputs and adapter source hash: `granite-grounded-results.json`.
- This is successful output validation, **not 100% accuracy**. These are the
  same development examples that informed the prompt improvement, not holdout data.
- Codex evidence review found no amount/decision contradiction in the accepted
  outputs. The missing-record answer is accurate but under-explained: it only
  says the case remains unresolved, omitting the category and hypothesis detail.
  Treat its three repetitions as weak explanations rather than claiming a
  perfect usefulness score. An independent human review is still pending.

An alternate-record evaluation uses nine different records (second record in
each category), retaining the original INR 9.83 trap as a fixed safety regression.
This is a narrow same-dataset check, not an unseen category or real-world test.

Alternate results (`granite-alternate-results.json`): **30/30 accepted**, zero
fallbacks; all 30 were warm, median **3.637 s**, nearest-rank p95 **5.586 s**.
The generated text matches the first-run meanings because monetary values are
now intentionally excluded from model input. Changing amounts is therefore not
an independent arithmetic-reasoning test. The smaller prompt asks only for a
paraphrase of verified states; the model no longer explains numeric calculations
or diagnoses new root causes. That deliberate scope reduction is part of the
improvement, not a general model-performance claim.

Codex reviewed all 60 responses against the recorded states. No critical policy
or amount contradictions were found in that review. Across both runs, six
missing-record responses omit useful classification/hypothesis context and
remain weak. Do not convert the 60 accepted outputs into a 100% accuracy claim,
or claim the independent 90%-quality gate has passed. All `human_review` fields
remain null. Both result files contain exact facts, raw output and adapter hashes.

One follow-up source fix maps an unavailable/degraded investigation to
`INCOMPLETE`, not `NOT_NEEDED`, even if it produced no hypotheses. A new regression
test covers this edge case; it did not occur in either 30-request dataset run.
Those result files identify the pre-edge-fix adapter hash; their non-degraded
snapshot values and model prompt are unchanged by that fix.

Follow-up checks: the final full backend suite passed **896/896**; 34 focused
backend checks also passed, including grounded-input
construction and the degraded-investigation edge case. Frontend tests passed
27/27 in single-worker mode, both existing browser journeys passed, and the
production build passed. A prior concurrent frontend run had two wait-timeout
failures in unchanged Overview/WorkQueue tests while inference and backend
tests were running; the single-worker rerun passed without changing assertions
or timeout limits. The pre-existing expected ErrorBoundary fixture still logs
its intentional error while passing.

This establishes integration behavior, not product value: the plain verified
statements could themselves be displayed without a model. No evidence yet shows
the model paraphrase improves user comprehension over deterministic wording.

Final manual browser check used a new synthetic duplicate exception. The real
API/Ollama response read: "The recorded classification is duplicate. An AI
hypothesis was checked and rejected. The existing policy requires human review.
Automatic resolution is not authorized." The UI displayed the unchanged human-review
decision separately. Observed response time for this additional smoke request
was 6.7 seconds; it is not included in the two 30-request evaluation totals.
