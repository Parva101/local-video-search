# Project decisions

## 2026-11-06: Diagnose Gemma long-video indexing failure

Status: diagnosed; prompt fix proposed, not approved or implemented. The existing failed job has not been restarted.

The uploaded27-minute recording imported successfully. Its description job stopped after48/205 windows at384–394seconds. The saved HTTP200 reply reports finish_reason=length after1024 tokens. Its summary reaches the600-character schema limit, then emits1276 whitespace characters. Local replay reproduces the current client's rejection. Keep this error explicit; truncated JSON is not a valid description.

One separate compact-output request at the failed interval also failed with length. Do not claim the ASU gateway honored or enforced the extra vLLM setting merely because it returned200. Do not increase tokens as the only fix or relax validation. ASU documents response_format but not a compact-output control. [ASU API](https://docs.rc.asu.edu/ai/api/chat/). The underlying vLLM0.26 API defines structured-output options, but that does not establish gateway forwarding. [Primary source](https://github.com/vllm-project/vllm/blob/v0.26.0/vllm/sampling_params.py).

Propose a concise Gemma description prompt that names every JSON field and supplies a compact example with shorter target lengths. Test the exact failed interval before deploying it. If successful, version the prompt/build and create a separate full index. Preserve the old48 windows under their original policy; silently copying them into the new build would break the project's provenance rule. A shorter prompt remains a hypothesis until tested.

Private reply evidence stays in the ignored .codex-backups folder. No footage, descriptions or source images are copied into public evaluation artifacts during diagnosis. The earlier22-second smoke pass did not prove long-video reliability.

## 2026-11-06: Local upload and question flow requested

Status: approved by "build"; implemented and running locally. Final acceptance evidence: evaluation/gemma-upload-e2e-results.json.

The user wants to upload a video, have it indexed, then send text queries and inspect the answers. Reuse the existing API, worker, leased jobs, description search, source-frame verification and video playback. Add a small same-origin browser page and streamed upload endpoint; do not add a frontend framework or broker for this flow.

Propose hosted Gemma description indexing first, followed by description retrieval and source checks for the best candidate intervals. Display observations, evidence status and source timestamps. Keep visual search available through its existing API; equal-weight hybrid fusion previously lost a correct top result on the tiny smoke set, so do not make it the new default without evidence. A separate free-form answer generator is not needed to show the model's source-check answers.

Use dedicated persistent upload storage with write access limited to the API upload area. Preserve read-only access to the original library, stable source paths and existing database records. Complete uploads must trigger durable import/index work rather than depend on browser polling to create the next job. Keep the key server-side. Explain that selected frames are sent to the ASU endpoint.

Verification must cover actual browser upload, automatic indexing, a positive and negative query, timestamp playback, empty input, double submit, refresh, interruptions and regression tests. Counts, speech search and full-recording absence claims are outside this initial tested flow. See PLAN.md for approval and proof steps.

Implemented one plain HTML/CSS/JavaScript page in FastAPI, with raw streamed uploads and no new dependency. Upload ceiling:2GiB. This setup uses VISION_PROVIDER=gemma and the existing private Voyager key. Gemma and Qwen retain separate complete build specifications; the page checks the exact build key rather than only its model name.

Schema v4 persists the requested description specification on an uploaded import. The import transaction also creates its child indexing job, so tab closure cannot interrupt the handoff. Uploads use UUID-based names and byte-checked retry IDs. Partial files are removed, including stopped-process leftovers when that ID is retried. Original sources stay intact. Database and files were backed up before upgrading.

Docker cannot create a missing nested volume mountpoint under a read-only source bind. Mount uploads separately at /uploaded-media for readers and /uploads for API writes. Use the internal absolute /__uploads/ source marker. A relative prefix was rejected after review because it could shadow a real library folder; regression checks now preserve that folder. No source-provider framework or origin table was needed.

Reject all vision-endpoint redirects. A local two-server test proved the old urllib handler could forward Authorization; tests now prove no destination request for301/302/303/307/308. Keep response checks and safe error details; do not retry redirects or repair model output.

Proof:136 tests passed with real embedding models,44.57seconds,exit0; two existing SentencePiece warnings. Browser upload, double submit, refresh during indexing, two queries, responsive layout and timestamp playback passed. Restart preserved the ready index and source bytes; all three original records are unchanged. The cup was found at17.88–20.14seconds. Negative explanations remain contradictory and are stored unchanged. No benchmark gain or speech/counting capability is claimed.

## 2026-11-06: Try hosted Gemma before changing the application

Status: user approved the standalone trial with "ok elts try gemmamodel". Trial complete; production integration is proposed, not implemented.

Use the existing Docker image, source sampler, eight ordered JPEG frames, prompts, schemas and frozen robot-coffee cases. Reuse the key in the ignored .env without printing it. Call the named gemma4-31b-it model with reasoning_effort=none, helper add-ons off, strict JSON schema and a bounded 600-second timeout. Do not send the Qwen-specific chat-template settings or claim its pinned checkpoint revision for Gemma.

All five frame requests returned HTTP200 and passed the current output contracts. Both verification statuses matched the provisional expectations. Requests took 7.71–15.23 seconds, median9.29 seconds. All five frame-hash lists match prior Qwen inputs. Application source hashes still match the previously tested code; no database writes or Sol GPU jobs were needed. [Saved results](evaluation/gemma-voyager-smoke-results.json).

Read-only review confirmed these counts and limits. The trial reuses prompt instructions and output schemas, but formats numeric bounds as integers where the application uses floats. Inputs are not byte-identical prompts; retain this difference in the comparison evidence.

Keep quality findings separate from contract checks: two descriptions have empty action/object arrays; one action string is incomplete; the absent-person decision says no_match while its explanation says insufficient_evidence. Do not fix or hide these responses. One video and two provisional status labels cannot prove model superiority or useful retrieval accuracy. Gemma retrieval was not tested.

Test direct MP4 input separately from frame input. The 6,145,362-byte base64 video request failed once with HTTP413, Payload Too Large. Preserve that failure and stop this probe. The responsible limit and acceptance of smaller video_url requests are unknown. Use the independently tested ordered-frame path in the proposed integration; it is not an automatic fallback after upload failure.

Next proposed change: extend the existing client/settings and Compose with an explicit hosted-Gemma choice, separate model/index specification, hosted request parameters and gateway request trace. Keep Qwen support and old index records. Test config, protocol, errors and build separation; then measure actual Gemma retrieval and source checks. No new provider framework, dependencies, schema relaxation or native-video upload path is needed. Ask for code-edit approval as AGENTS.md requires.

## 2026-11-06: Check ASU-hosted inference before more Sol serving

Status: requested by the user; authenticated model catalog now checked. Gemma is recommended for the first hosted trial, not selected as a proven video-quality winner. No provider switch or code edit is approved by this check alone.

For current development, investigate the hosted models managed through Voyager instead of starting another Qwen serving job on Sol. ASU documents a free OpenAI-compatible API at https://openai.rc.asu.edu/v1. This can provide inference without our own serving job. [Access guide](https://docs.rc.asu.edu/ai/api/).

The authenticated catalog lists both gemma4-31b-it and qwen38-27b as BF16 with native vision and no gateway add-ons. Gemma advertises response-schema enforcement and a 131,072-token hosted context. Qwen advertises no response-schema enforcement and a 262,144-token context. Lack of schema enforcement does not mean Qwen cannot produce JSON; its replies still need local validation. The base models both support video through frame processing, but hosted video_url acceptance and eight-image input remain untested. Use a named model and disable helper add-ons for controlled comparisons. [ASU field definitions](https://docs.rc.asu.edu/ai/api/chat/).

Initial unauthenticated GET /v1/models returned401. The user then added an API key to the ignored .env. A read-only authenticated catalog request succeeded; the key was not printed or copied into the research note. No inference calls or jobs ran during this check. Runtime acceptance, latency and quality remain untested.

Published evidence is mixed. PanoVideoBench reports Gemma higher overall and Qwen higher in action/state understanding, with tied temporal reasoning. ProactEgoMem-Daily reports Gemma higher in state-interval overlap, but Qwen higher in several event-detection measures. These are panoramic and egocentric tasks, not CCTV archive retrieval. Recommend Gemma as the first hosted integration because it is competitive in these tests and advertises schema enforcement; retain Qwen as a quality comparison. Do not claim universal model superiority. [Detailed evidence and protocols](research/hosted-video-model-comparison.md).

The current client pins the Sol model ID/revision, uses Qwen chat-template settings, and has a180-second HTTP timeout. The hosted gateway documents reasoning_effort and a capacity queue of up to five minutes, so changing only the URL would be insufficient. Inspect authenticated catalog metadata first, then propose the smallest adapter change for approval. Retain the actual hosted model identity; do not claim the old pinned checkpoint revision for a hosted model. [Gateway limits](https://docs.rc.asu.edu/ai/api/limits-and-errors/).

## 2026-11-06: Add explicit Qwen descriptions and source inspection

Status: authorized by "lets do it"; implemented, 100 tests passed, and real Qwen inference checked. GPU service stopped after the test.

Keep SigLIP2 visual search. Add a separate Qwen3.6-27B description job and an explicit source-verification request. Use eight ordered actual-PTS frames per window; retain descriptions, uncertainty, frame hashes, model revision, request IDs, usage, and source intervals. Validate all structured output and reject intervals outside the inspected source. Sampling can miss brief actions; a model check does not prove an event or its absence throughout a recording.

Use the existing leased queue and database, with schema v3. Embed description summaries with pinned all-MiniLM-L6-v2 (384 dimensions); full-text search also covers listed actions and objects. This reuses installed Transformers without a new dependency. Combine dense and keyword ranks, then optionally combine visual and description ranks. Keep visual as the existing default; choose description or hybrid explicitly for controlled comparisons. No hidden route fallback.

Run Qwen through a configured authenticated OpenAI-compatible endpoint. Test: one 80 GB A100, BF16, eight images, 8192 context tokens, one concurrent request. Reduce the initial 45-minute request to 20 minutes for backfill. Use an immutable vLLM 0.20.0 CUDA 12.9 container for reproducibility. Disable Python user-site packages in preparation and serving: otherwise host-home packages shadow the container. The initial old-version result came from home packages and did not establish the ASU shared image's actual version. Build the image with node-local temporary storage; retain the completed image and model on scratch. Preparation and downloads use CPU allocations. No fine-tuning, speech, classifier, or UI in this stage.

Real verification exposed two contract failures: a match with no intervals, then repeated whitespace under the stricter interval schema. Encode status/interval consistency in the JSON schema and use the supported xgrammar compact-output setting. Record its policy in build specifications so old and new windows cannot mix. Keep validation errors and initial evaluation results; do not repair replies or relax checks. The compact runtime returned a valid cup-action interval and an absent-person result on the same frozen cases.

Freeze a small rights-cleared robot-coffee smoke set before inference. Compare the same queries and source scope across paths. This checks integration and exposes errors; it cannot support a benchmark-win claim.

Final smoke: visual 0/2, description 1/2, hybrid 0/2 at Recall@1 / temporal IoU >= 0.3 on two provisional queries. Both source checks passed. Keep the existing default; this small development set does not justify a new retrieval default. Next measure ranking and candidate recall on an independently reviewed set before training. See evaluation/qwen-coffee-smoke-results.json and evaluation/qwen-runtime-results.json.

## 2026-11-05: Prefer Voyager MCP for Sol operations

Status: confirmed user preference; read access verified.

Use the connected Voyager MCP tools first for supported account, allocation, documentation, job submission, and monitoring tasks. Reuse the established SSH key for file transfer and operations the connector does not support, within the user's authorized work. Avoid repeated manual sign-ins.

Checked through Voyager: the same two Sol allocations are visible and the active job list is empty. Its separate Sol submission token is missing, so MCP job submission is not ready. The MCP connection itself works. No token was created, printed, or stored, and no job was submitted.

ASU's current [Voyager MCP guide](https://docs.rc.asu.edu/ai/voyager-mcp) says submission needs a cluster-specific Slurm token stored under Keys > Cluster tokens and outside services (or Cluster tokens on the Slurm tab), plus the Job submission capability. Submission stops when that token expires. Existing SSH key access remains available without another password login while the key is usable.

These records distinguish agreed decisions from implementation proposals. Import and visual retrieval are implemented and tested with a real image-text model. Public benchmark gains and final event-verification accuracy remain unproven.

## 2026-11-05: Implement the visual retrieval baseline

Status: authorized by “lets do next”; implemented and tested. This is an initial baseline, not selection of the final video analysis model.

Use [SigLIP2 base](https://huggingface.co/google/siglip2-base-patch16-224), pinned revision 75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2, with its matched text encoder. Run CPU/float32 with four inference threads first. Why: this tests indexing and exact retrieval without requiring CUDA setup, while ordered video encoders remain a later controlled comparison. It does not establish motion understanding.

Sample three timestamped frames per logical window. Record actual presentation timestamps and explicit within-window selection behavior. Resize to a maximum side of 512 before native model preprocessing; pool normalized frame vectors into a normalized 768-dimensional vector. Store model, runtime, sampling, pooling, and preprocessing in each build specification. Search only ready builds in the same embedding space.

Extend the existing leased queue with visual jobs instead of adding another broker or worker service. Checkpoint each window under current ownership; publish the index only after full window completion. Use schema migration v2 and preserve v1 import records. Keep indexing explicit through the API rather than starting model work on every import.

Use exact cosine search, recording/source-relative time filters, candidate media links, and visible processing coverage. Similarity is not event verification. Index setup downloads the model once to persistent storage; inference uses local files and reports missing/failed models explicitly. Expected inference errors fail their job without stopping later imports. No automatic provider or CPU/GPU fallback is used.

Proof: 65 tests passed, including actual model inference, timestamp sampling, import regression, schema migration, stale checkpoints, resume, and filters. The live synthetic timeline retrieved all three expected color windows and remained searchable after restart. [Results and costs](evaluation/visual-smoke-results.json) are a smoke test, not a public benchmark result. Descriptions, transcripts, Decider, and video verification remain later stages.

## 2026-11-05: Implement the first import stage

Status: authorized by “lets start implementation”; implemented and checked.

Use a Python/FastAPI API, one worker, PostgreSQL 17 with pgvector 0.8.7, and FFmpeg in Docker Compose. Use psycopg directly; no ORM, message broker, or model framework is needed for import. Pin the tested Python dependency versions in constraints.txt.

Import existing source media through a read-only mount. Store content-addressed asset metadata, distinct recording occurrences, source-relative logical windows, and leased jobs. Reuse unchanged jobs. Keep repeated content at different paths as separate recordings. The first window setting is ten seconds with two-second overlap, still a baseline for later evaluation.

Bind a database to one absolute host source-root identity. Reject a changed root instead of reusing old relative source references. Alternative: multi-library namespacing; defer it until required. A separate Compose project/database handles another root now.

Use at-least-once claims, lease refresh, bounded abandoned attempts, atomic completion, and explicit retry of failed jobs. Recovery restarts the interrupted file. Detect source changes with size/mtime checks; a stored hash does not prove the bytes served later if a host replacement preserves those values.

Proof: 44 tests passed in the Linux containers against real PostgreSQL and FFmpeg. A generated sample completed import and range playback through the running API and persisted across service recreation. No semantic retrieval, classifier, or video model was run.

## 2026-11-05: Full architecture review and benchmark plan

Status: research and draft requested; architecture changes are proposals, not confirmed implementation choices.

The user asked for a full evidence-based review and allowed a different proposed direction if the research supports it. The [full draft](research/full-project-draft-plan.md) recommends keeping the local Docker/PostgreSQL foundation and testing broad retrieval followed by bounded source inspection. It prioritizes temporal evidence quality at a declared cost over an unsupported general model-ranking claim.

Alternatives reviewed: hard classifier route exclusion versus all-path retrieval or budget allocation; fixed versus multiple window lengths; frame versus ordered video embeddings; static index versus query-specific source reinspection; early tracking/agent graphs versus adding them only for measured failures.

Why the proposed direction: an excluded path, lost short event, or wrong source interval cannot be fixed by a fluent final answer. The simplest useful comparison is an all-path hybrid baseline with the same verifier and evidence budget. Decider Flash remains the selected classifier experiment; replacing its role requires review of the results and proposed default.

Proposed evaluation order: QVHighlights, then a corpus/subtitle benchmark such as TVR if media access permits, plus a separate reviewed product set. ForeSea comparison depends on obtaining its complete data and protocol. Draft numerical success gates are proposals, not user rules. No benchmark gain, download access, or runtime fit was demonstrated.

## 2026-11-05: Local distribution with Docker Compose

Status: confirmed.

Build an open-source, self-hosted video search application. A user can point it to a local directory containing one or more video files and build an index. Use Docker Compose for the local application and database setup.

Why: users should not need to configure the application dependencies or database by hand. A repeatable container setup also gives contributors a common environment.

The application setup can download container images and initialize its database. Installing Docker and any operating-system prerequisites remains a separate setup step. This decision does not authorize silent system installation.

## 2026-11-05: PostgreSQL and pgvector in one local database

Status: confirmed in the database and Docker discussion.

Store SQL records and vector embeddings in one local PostgreSQL database with pgvector. Keep the original video files in local file storage and store their references in the database.

Alternative considered: a separate vector database plus a SQL database.

Why this choice: one database keeps source references, clip times, descriptions, and embeddings together. It also reduces the number of services that users must run. No measured need for a separate vector service has been established.

Local database operation does not require a cloud database account. Model API charges, hardware needs, and container-runtime terms are separate from the database choice.

## Earlier discussion: Backend first; training later

Status: confirmed.

First build the import, indexing, search, video inspection, and evidence pipeline. Evaluate and train models after the backend works.

Why: the project must provide a useful system around the model, and the working pipeline will provide a place to compare models.

## Earlier discussion: Support different analysis models

Status: confirmed direction; model selection remains open.

The pipeline should support existing models, including closed-source models accessed through an API. Do not bind the full system to a single final analysis model. Cloud inference is optional; the local indexing architecture does not require a cloud database or hosted index.

Why: the user wants to complete the pipeline before choosing or training its final model. A change to the answer model should not itself require a new retrieval index. A change to the embedding model can require reindexing.

## Proposals still awaiting implementation approval

The details in [the backend proposal](research/backend-implementation-plan.md) remain proposals unless confirmed above. These include the application framework, worker design, exact model choices, sampling and clip settings, API routes, and evaluation thresholds. No runtime performance or benchmark improvement has been established.

## 2026-11-05: Search spoken content and supplied subtitles

Status: confirmed requirement; implementation remains proposed.

Add timestamped speech transcripts and existing subtitles/captions as a third search path alongside visual embeddings and generated visual descriptions. This supports queries such as "Find the meeting where we discussed Project XYZ."

Why: visible actions and scene descriptions do not capture the content of a spoken discussion. Keep transcript and subtitle sources distinct from generated visual descriptions, and link search results to the source recording and time interval.

The speech-recognition model and the precedence between supplied subtitles and generated transcripts remain open. No transcription accuracy or working implementation has been established.

## 2026-11-05: Decision model chooses the search path

Status: confirmed direction; implementation remains proposed.

Use a dedicated classifier or discriminative typed-decision model before retrieval to choose the search path for the user's query. This is not a general chat LLM prompted to emit routing text or JSON.

Why: spoken-topic questions and visible-event questions need different indexed evidence. Searching all paths remains a comparison baseline; the effect of routing on evidence recall has not been measured.

Proposed detail: the model receives the query, reference-image presence, and available index/modality metadata. It scores fixed route labels or independent yes/no questions for visual embeddings, generated visual-description text, and transcript/subtitle text. The backend validates these typed decisions and constructs the executable search plan from them and the existing query and explicit filters. The classifier does not generate free-form filters, query rewrites, explanations, or arbitrary plans. Selecting several paths for a mixed query is a proposal, not a separate user rule.

The route selects where to search; it does not establish evidence or generate the final answer. Record the routing decision, model, and version. Invalid typed decisions, invalid backend plans, and unavailable required modalities must be visible; do not silently switch paths. The initial classifier is selected below; thresholds, calibration, and the final model choice remain open and untested.

Clarification: the user's decision-model examples refer to dedicated decision systems such as Jev, not a prompted chat model. The user named [mammoth-1](https://huggingface.co/baselabs/mammoth-1) and [Perplexity Decider v1.2](https://huggingface.co/perplexity-ai/pplx-decider-v1.2) as open-weight candidates to inspect. Neither checkpoint is selected; access, hardware needs, and suitability for this routing task have not been established.

## 2026-11-05: Test Perplexity Decider Flash v1.2 first

Status: initial classifier selected for evaluation; not a proven production default.

Use the 4B [Perplexity Decider Flash v1.2 checkpoint](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2), exact ID `perplexity-ai/pplx-decider-flash-v1.2`, for the first routing tests. The user will decide whether to keep it after measuring performance.

Why: the local laptop has a 16 GB RTX 3080 and about 32 GB RAM. The 27B candidates exceed that GPU's BF16 weight budget. The smaller checkpoint is the initial choice to test, not a claim of measured memory fit, speed, or accuracy.

Follow [PLAN.md](PLAN.md) for readiness, model loading, and a labelled routing benchmark. Checkpoint access, runtime compatibility, CUDA operation, memory use, and routing quality remain unverified. Code implementation awaits review under AGENTS.md.

## Gemma prompt v2 and bounded evidence experiment
The old long-video failure was a truncated structured reply after a 600-character summary and whitespace loop. Explicit fields and shorter requested text passed the failed interval plus two neighbors without changing schema or token caps. Give the new prompt a separate build identity; never mix its windows with v1. Build full new index and retain old evidence.
For chat.md follow-up, test distinct-time candidate selection and one denser source inspection within the same verifier call budget. Keep ranked baseline and full traces. Do not add graph memory or a trained router before this baseline is measured. Use official QVHighlights public example for engineering proof only; it cannot establish novelty or SOTA.

## Measured retrieval follow-up, 2026-11-08
One public development query shows a ranking error and narrower model evidence intervals than the labeled event. Adaptive selection alone ties ranked checks; retain both and claim no gain. Test optional pinned cross-encoder/ms-marco-MiniLM-L6-v2 on24description candidates (no index regeneration, no automatic runtime download). Its first fixed-recipe ten-candidate trial improvesrank2to1 in0.15sCPU; evidence is insufficient for a general accuracy claim. Preserve model intervals as observed; do not stretch them to the benchmark labels. Source check budgets now distinguish logical calls from HTTP retries and sent frame slots.
The evaluation manifest records exactmedia duration separately from roundedofficialannotation duration. Keep strictbounds; do not silently clamp predictions. Reject changed, missing or unchecked sources before scoring.

## Separate Gemma verification prompt, 8 November 2026
The final full-video browser query exposed length-truncated JSON in verification, even after description indexing succeeded. Apply the same explicit field names, compact example and short requested text to this separate task, retaining the strict schema,2048token cap and no-repair policy. Use visible-evidence-gemma-verification-json-v1 in verification traces and saved run specs. Keep the description v2spec unchanged so the205-window index remains valid. Exact failed query/window passed in3.44s58tokens; public positive/negative controls passed in4.72s61tokens and3.42s35tokens. Re-run source-check comparisons under the new verification prompt; preserve earlier results with their original identity.

## Proposed next stage: evidence completeness before broader claims
Inspection found a fixed-window upper bound and first-match stopping that explain the public boundary failure. Proposed priority is a frozen broader benchmark plus optional boundary continuation, then speech and scoped event counting. Do not use a graph or train another model before this controlled baseline is measured. These choices await approval under the replacement AGENTS.md. Keep existing description indexes valid and retain the current search path as a baseline.

Research follow-up (still proposed): prefer the verified selective Charades-STA45video122query pilot over the gzip QVHighlights archive. Root verified ZIP64range access and primarylicense recovery. Keep licensed data private and state the exact pinned annotation-copy provenance. Increase proposed first-stage cap from500to1500hostedcalls to include indexing and controlled ablations for the complete declared pilot; await approval before this spend or code change.

## Approved Charades/boundary slice
User approved the45video122query pilot with1GBmedia/1500hostedattempt caps. Reuse existing import/model/search modules and isolate benchmark tables via the existing per-schema pattern. Use a local benchmark-only request gateway and durable private attempt ledger so retries cannot bypass the cap. No new dependency or public-dataset redistribution.
Use explicit VSLNet reference label preprocessing against pinned annotation durations, preserving rawlabels. Predictions remain bounded to actual media. R1+.3/.5/.7 andmIoU are primary reference-compatible metrics; simpleR5 stays diagnostic because legacyTALL applies threshold-specificNMS. Freeze test protocol before predictions and retain every failed case.

## Event-edge evidence and controlled comparison
Use a separate strict source-sample task; do not alter the description build or old verifier. Neighbor checks retain7newframes+1identical seed reference. Positive extensions require a same-event link; repeated events and unknown links stay separate. Bracket midpoint proposals stay distinct from raw source intervals. Partial query support cannot claim complete. Fixed ranked and uniform extent controls share the same reranked pool and3check/24slot cap; report actual attempts and matched-work subsets. The3-query gate has no R1@.5 gain and is not a tuning result.

## Extent task v2: derive status from frame labels
The v1 development run exposed a model role error: only the repeated reference was positive, yet the model said match. Do not loosen validation or repair that reply. In a new four-field wire protocol, ask only for frame labels, query support, same-event relation and observation. Compute status in code from new-frame labels and record the derivation. Preserve raw v1 failure, all56completed v1cases and359attempts. Rerun the full development grid under v2 before freezing test. This costs more requests but removes an unnecessary model decision; it does not prove better visual recognition.

## Extent v3 and budget re-plan before heldout evaluation
A v2 neighbor returned allabsent with relationnot_applicable. That relation is valid when there is no positive event pair; the validator over-constrained it merely because a reference slot existed. V3 fixes applicability, retaining the raw label and rejecting N/A for positive new/reference pairs. Keep all old replies/attempts. To stay under1500after493attempts, run53developmentqueries with2extentcontrols (318maxrequests), then69testqueries withall3conditions(621max). This pre-test design keeps all selected queries; it does not use test results to choose a method. Worst1432total,68retryheadroom. New version/hashes separate this run from both earlier failed protocols.

## V4 role-specific output schemas and final pre-test budget design
V3model returnedN/A forpositivepair because the shared wire enum still permitted it. Select a seed schema withN/Aconst and neighbor schema with3actual relationdecisions before calling the model. Useunknown when no newtarget or link is uncertain; do not coerce returnedvalues. This moves known input-role constraints into constrained decoding. At616spentattempts, validateall53developmentqueries withmainextent only (159max), thenall69testqueries withall3conditions(621max):1396maximum. Development comparisons fromolderprotocols remainfailed historical runs and do notselectthewinner. No testprediction or target-driven tuning occurred.

## V5 distinguishes supplied-context support and new evidence
Full-query support is a semantic judgment over all suppliedorderedframes, including the retainedreference. New-frame presence/status and event extension are separate. V4failed a reference-supported allclaim with allnewframesabsent. V5 changes thisscope explicitly and preservesrawlabels;statusstillno_match. An allclaimrequiresatleastonepresentinput, and negative neighbor packets cannot upgradepartialparentquerysupport. Keepseed/neighborwireenums. At642attempts,newdev159+test621max=1422<=1500. No held-outpredictionorGT-drivenqualitytuning.

## Explicit point evidence after incomplete frozen baseline
The unchangedbaselineproducedthesamezerodurationmatchtwice;thefrozenrunisincomplete(63/207,2errors). Preserveit. A singlevisibleinstantshouldnotbeinventedintoanintervalorcrashthepipeline. Newversionacceptsequalstart/endasevidencepoint,UIlabelsat-time,andtemporalextentmetricscountpointonlyanswersaszero/abstention. Reversed/outsideboundsremainerrors. New2-checkexploratorycomparisonkeepsall69queries/all3methods,with53one-checkdevqueries;991+53+414=1458maxattempts. Originaltestexposureisdisclosed;newnumberscannotbecalleduntouchedheldoutorSOTA. Existingdescriptionindexesremainvalid.

## Context support without timestamp localization is an abstention
A validstructuredmodelreplysaidallquerysupportandallframesabsent. Clip-levelrecognitionandper-samplelocalizationcanconflictorhave differentgranularity. Keeprawjudgments,logwarning,andderiveinsufficient_evidence,nospan,nopositiveanchor. Source/schema/duplicateerrorsstillraise. Prompt/schemaunchanged.
ReuseonlyunaffectedcompletedresponsesafterstrictAST/source/prompt/schema/scopecompatibilityproof;eachnewcasehasparentcaseSHA/protocolandidenticalrawresult. Allcachedcasesmustavoidthenewuncertaintybranch. Thisisexplicitauditedcachemigration,notreplyrepair/hiddenversionmixing. Preservealloldfreezes/errors. At1220spent,174cached+240freshattemptscomplete414requestevaluation;newglobalmax1460. Costsacrossprotocolsoverlapandmustnotbeaddedtwice. Runremainsexploratoryaftertestexposure.

## Final measured decision: no general benchmark win

All 69 evaluation queries and 207 cases completed at two checks and 16 frame slots per method. The new method reaches 33.33% R@1 at IoU 0.5, versus 30.43% for uniform inspection and 42.03% for reranked candidate retrieval. Mean IoU is 28.86%, below reranked retrieval at 35.89% and raw retrieval at 36.99%. Stricter R@1 at IoU 0.7 improves to 13.04%, versus 4.35% for reranked retrieval. The gain over uniform at IoU 0.5 is only two queries; its confidence interval includes zero.

Do not claim a win by comparing only with the weak numeric verifier at 1.45%. Keep current defaults and leave event-boundary inspection experimental. Six of eleven model-complete proposals fail the IoU 0.5 localization check. Reliable full-event boundaries remain unsolved.

The next quality gate needs independent long-video and negative-query examples, with strong retrieval as a baseline. Improve temporal perception and coverage before adding more agent complexity. Training, speech and count implementation need a separate approved scope.

## Research-led temporal learning — 14 November 2026

The user approved this new performance campaign and Sol training. First test deterministic score curves over saved caption scores, then train a frozen-feature temporal head. Keep all current product behavior unchanged until a new path earns its place. Simple smoothing and maximum-subarray decoding are established methods; they are controls, not a novelty claim.

Choose the pinned MIT-licensed UniVTG model as the first trainable control because author features, metadata, config and weights are accessible and small enough to inspect. A strict loader avoids the old loader's missing-feature zero substitution. Its released training metadata has 12,404 rows, versus the canonical 12,408; audit and disclose this before a reproduction claim. Start from scratch for the controlled training comparison so a released downstream checkpoint cannot contaminate our train-only validation split.

Compare binary foreground training with IoU-quality foreground targets at the same features, initialization and compute. IoU-quality classification is established prior art, so this is an accuracy experiment rather than a new-method claim. Use three seeds and a deterministic video-disjoint development split from official train. The published downstream checkpoint is a separate reference, not the initialization for that controlled comparison.

Defer full VLM RL, graph infrastructure and router work: they add cost without resolving the observed localization error. TD-DETR and SDST remain stronger alternatives; TimeLens/TimeLens2 provide refined-boundary and generalist references with separate artifact terms. Do not mix their label protocols or claim that published full-test numbers are comparable to our old 69-query pilot.

The first train-selected caption curve improves mean IoU on the old pilot, but its R1@.5 gain is only one query with an interval including zero. Keep it outside the product default. Local contrast did not establish a gain; do not add it to the product.

The first Sol smoke found an environment dependency, not a model failure: Git is absent in the reused container. Verify exact author runtime-file SHA-256 values with the standard library instead of adding Git or binding a host executable. Preserve the failed run. A staged epoch journal also fixes a review-found resume race that could lose the best checkpoint. No long training starts until the new short smoke passes.

V2 batch smoke passed, but the first long run found a validation bug: the author float32 clamp followed by four-decimal rounding has a different boundary envelope from rounding the double-precision duration. Preserve author outputs and use that exact envelope in scoring. Reject larger or non-finite outputs. Expand the v3 smoke to full development validation and complete state save/load before another long submission. This is a reliability fix from train-development data, not test-score tuning.

The release audit found interval as well as text differences from the canonical copy: 562 shared test intervals differ by at most 0.18534 seconds. Report processed author-release results separately. A small feature-head gain on this release cannot establish a canonical full-benchmark SOTA win.

Before the first full-test prediction, review reproduced padding dependence in the author's temporal convolution heads. Keep batch32 for the identical-harness comparison of our six models and the released checkpoint. Add an explicitly separate batch4 reference check matching the author config. Report batch size in every result; do not call the batch32 reference an exact paper reproduction. This protocol choice uses code inspection and a synthetic model check, not test scores.

## Reject the first trained adaptation after complete test

All six runs and all eight full-test cases completed. Mean R1@.5 is 60.04% for baseline versus 58.80% for IoU-quality, with a -1.24-point mean difference and paired interval [-3.08,+0.55]. The IoU .7 point estimate improves but its interval includes zero; mean IoU falls. Keep the baseline. Do not cherry-pick the winning seed or treat the earlier validation gain as a test gain.

The reference at native batch4 reproduces the rounded published60.19% R1@.5/38.55%R1@.7/52.17%mIoU. Match-harness batch32 yields60.11%R1@.5. All checkpoint selections and hashes were audited;47focusedtests passed. Publicaggregate contains no raw examples.

Move to the already-selected stronger-reference stage: SDST has an accessible checkpoint, BSD3source and byte-identical processed labels, avoiding FlashVTG query-ID remapping. First acquire a complete27.3GB local feature snapshot and validate only the native Charades files; no weak-ETag range shortcut. Then gate its isolated CUDA ROI extension and checkpoint before any further training. Paper72% recall is not our result. This is a reference/representation experiment, not a novelty claim.


## Isolate the SDST runtime and retain the failed download

Use the pinned official Torch2.2.1/CUDA12.1 development image, not a kernel port into Torch2.11. Rebuild the native ROI operator later on an allocated A100; never load the bundled sharedlibrary. CPU preparation has exact image/source checks, an isolated package target and explicit import failures. Missing OpenCV OS libraries require a recorded re-plan. No change reaches app dependencies or frozen experiments.

The first Sol data job1608962 failed before the archive stream because Google returned a second HTML page. A local bounded probe had confirmed the expected full-response headers. Preserve this difference and inspect onSol; do not weaken content/length checks or silently switch features. Runtime preparation1609074 is independent and can continue.


## Stop repeat registry builds; change transport only with evidence

Both CPU image jobs1609074 and1609248 hit the same Docker registry TLS handshake timeout before layers. Stop this step under the two-failure rule and diagnose the endpoint or an exact-digest offline transport. Keep the selected runtime, kernel source and frozen experiments unchanged. No SDST GPU allocation is justified yet.

The data failure is a Google quota page onSol, whereas a bounded local probe previously returned the exact ZIP headers. Use F:/codex-private/video-search-sdst-20261115 for the same full snapshot only if a fresh local probe passes; 509GBfree supports retained failed streams. Transfer checked bytes, then run all dataset checks on allocatedSolCPU. No alternate dataset or feature format is authorized by this transport choice.


## Same SDST image through a verified registry mirror

The registry mirror has the identical pinned manifest SHA25642204bca460bb77cbd524577618e1723ad474e5d77cc51f94037fffbc2c88c6f, matching config and16matching layer lengths. Use it explicitly, with no automatic registry fallback. New CPU job1609446 tests that route; native package, GPU and model passes remain unproved. The original compute-node TLS cause remains uncertain. See research/sdst-network-replan-2026-11-15.md.

The local data route later also hit Google's quota and stopped before a full download. Schedule one existing-script CPU retry1609447 after24hours, instead of immediate repeated requests. The raw artifact and all validation rules stay fixed. If quota persists, preserve the error and re-plan. Do not spend GPUs on unavailable data.

## Headless OpenCV in the isolated SDST runtime — 19 November 2026

Both 15 November jobs failed; neither used a GPU. Runtime 1609446 proved the mirror route: the 9.0 GB SIF was built and hashed, and every pinned package plus CLIP installed. It failed only at the final import probe because opencv-python needs libGL.so.1, which the pinned Torch 2.2.1 image does not ship. This was the documented OpenCV OS-library uncertainty; the job failed explicitly as designed. Data retry 1609447 still received Google Drive's quota page three times (HTTP 200, 2,040-byte HTML; expected 27,292,943,823 bytes); the 24-hour delay did not clear the file's traffic quota. Failure manifests remain on scratch.

Approved fix: pin opencv-python-headless==4.9.0.80 in the isolated runtime requirements. Same upstream version, released 31 December 2023 with a Linux x86-64 wheel; no GUI/libGL dependency; the cached server-side SDST paths do not use highgui. Base image, digest, CLIP commit and all other pins stay unchanged. The failed stage directory and SIF evidence remain untouched. Proof: the four focused runtime tests pass in Docker after the change; PyPI confirms the pin exists; the remote source hash was verified before submission (dd7b34f28ce8cd9d3175e03bc789e107244615b36f59ab159a4f094b42834ce2). Job 2067147 runs the new CPU-only preparation with a fresh stage. The data route stays blocked by the file's Google Drive quota; no further data attempts until the user chooses a path.

## Headless OpenCV pin was insufficient; SDST stopped — 19 November 2026

Job 2067147 FAILED 1:0 after 3:12 with the same libGL.so.1 import error. The log proves the cause: pip collected our opencv-python-headless==4.9.0.80 pin and, separately, nncore's declared opencv-python>=4.9 dependency; it backtracked through GUI opencv-python versions and installed one into the same isolated target, so the GUI cv2 binary won. A complete fix needs a no-deps nncore install or a constraint that redirects nncore's OpenCV requirement to headless. Under the same-day mandate below, the SDST route is stopped; no further fix attempts. All failures, stage directories and the 9.0 GB SIF remain on scratch as evidence.

## New mandate: complete the full product autonomously — 19 November 2026

The user set the direction and removed the per-step approval requirement: keep building until the complete system works end to end. Skip the SDST reference route and switch the research goal to proving the delivered system is best in class on an accessible benchmark; the exact SDST target is not required.

Product definition to complete: import recordings (folder or browser upload), index visual and description evidence, accept text and reference-image questions, return timestamped candidate intervals with model-verified source checks and playback, and support doorbell/CCTV use cases: visitor, delivery-driver and package questions, daily and monthly counts, speech topics. Test through real uploads and real questions until a security company or a laptop user can download the project, point it at their footage folder and start using it.

Decisions under this mandate:

- SDST is stopped (see above). The Google-Drive data block and both runtime failures stay recorded.
- The research goal becomes an honest best-in-class claim for the local zero-shot pipeline among comparable systems, on accessible benchmarks (a fresh untouched Charades-STA selection, negative queries, long-video cases), instead of chasing a supervised specialist number. Supervised reproduction already matched the released reference (60.04% vs 60.19%) and the IoU-quality adaptation was rejected. Any SOTA wording must name its comparison class.
- Build order: (1) reference-image queries, (2) capture-date and calendar scoping, (3) local speech/subtitle search, (4) scoped event counting, (5) corpus UX and release polish, (6) a real end-to-end campaign, (7) the fresh benchmark evaluation. Each stage keeps targeted tests, model-enabled regression and browser proof, and records measured limits honestly.

## Reference-image queries — 19 November 2026

Implemented under the autonomous mandate, stage 1. `/search` and `/evidence-search` accept `image_base64` (PNG, JPEG or WebP, decoded limit 10 MiB). The query image is decoded, RGB-converted, max-512 shrunk with PIL (`pil-rgb-max512-v1`, recorded in the response) and embedded with the pinned SigLIP2 image tower — the same checkpoint and space as the window vectors. With an image, the visual query vector is the L2-normalized sum of the unit text and image vectors (`unit-sum-text-image-l2-v1`). Images are rejected on the description path and with reranking, with explicit errors. The browser attaches an image, switches to the hybrid path, and disables reranked/extent policies; the library gains an explicit **Build visual index** control, keeping indexing explicit rather than automatic on upload. Static assets carry `?v=0.2` cache-busting after a stale-script trap during the browser check.

Proof: 3 focused tests passed; full model-enabled regression 521 passed, 2 private-checkout skips, 2 existing warnings. Real browser flow on a fresh 22-second upload: hosted Gemma description index, visual index via the new control, a real frame image plus "A robot moves a clear cup under the machine." — one source check, match at 17.88–20.14 seconds, playback seek at 17.88 seconds readyState 4, zero console errors. [Evidence](evaluation/image-query-e2e-results.json).

Known limit kept visible: the reference image steers retrieval only; the source check verifies the text query against sampled frames and never receives the image.

## Calendar scoping — 19 November 2026

Stage 2 under the autonomous mandate. Schema v5 adds `recordings.capture_date` and `capture_date_source` (additive; live database upgraded at startup). Dates are explicit: a per-recording date input in the library, and a bulk **Use file dates** action that derives dates from stored modification times at the browser's time-zone offset. A user-set date is never overwritten; the file action only fills recordings without a date.

`/search` and `/evidence-search` accept `start_date`/`end_date`. Date-filtered result and incomplete-build queries require a capture date in range; coverage deliberately does not apply the date filter, and instead reports `recordings_without_capture_date`, so an empty date-scoped result reads as "dates skipped it", never as "index unavailable". The browser scope selector (All time, Today, Yesterday, Last 7/30 days, Custom) plus a small deterministic keyword set ("today", "yesterday", "this/last week", "this/last month") applies scopes visibly; explicit choices stay authoritative.

Proof: focused tests 8 passed; full model-enabled regression **524 passed, 2 private-checkout skips, 2 existing warnings**. Real database upgraded v4→v5 with all data intact; 7 recordings dated from file times. Browser: "Did the robot move a cup under the machine today?" matched at 17.88–20.14 s with the scope shown; a yesterday scope returned no candidates with an honest absence note; zero console errors. [Evidence](evaluation/calendar-scoping-e2e-results.json).

Known limits: a date is a calendar day, not an instant; file times approximate capture time; recordings without dates are skipped and reported.

## Speech and subtitle search — 19 November 2026

Stage 3 under the autonomous mandate. Schema v6 adds `transcript_builds`/`transcript_segments` and the `transcript` job kind (additive; live database upgraded). Two transcript sources: pinned local Whisper base ASR (`openai/whisper-base` @ `e37978b90ca9030d5170a5c07aadb050351a65bb`, local CPU, chunked) through durable jobs, and direct SRT/VTT subtitle import via `POST /recordings/{id}/subtitles` (parsed, duration-validated, idempotent by content hash). Both embed with the pinned MiniLM text encoder, so `/search` gains a `speech` path that fuses dense and lexical ranks over all ready transcript builds with the same recording/time/date scoping as other paths. Speech results are labelled transcript matches with playback; the visual source-check path is unchanged, and evidence-search stays visual-only.

Proof: speech suite 5 passed including a real ASR test on a generated spoken fixture; full model-enabled regression 529 passed, 2 private-checkout skips, 2 existing warnings. Real browser run on 150 seconds of footage audio: 76 wall-seconds of local transcription, 6 segments, top match "It literally just came out of the oven" at 147.08–149.04 s, playback seek to 147.08 s, zero console errors. [Evidence](evaluation/speech-search-e2e-results.json).

Known limits: audio-origin assumption (stream start = source zero; nonzero origins not offset-corrected), ASR is an estimate, transcript jobs restart whole recordings on retry, no per-segment checkpoint, no speech verification.

## Scoped occurrence counting — 19 November 2026

Stage 4 under the autonomous mandate. `POST /count-events` defines an event by the text query and a declared scope (recordings, time range, capture dates), then checks each registered window with the existing visual verifier. Verified occurrences whose spans overlap within half a second merge into one event carrying every supporting verification ID; `insufficient_evidence` partitions are counted as uncertain, never as absence; a `max_checks` budget (default 60, cap 500) stops long scans, which report partial observed counts explicitly. Counts are computed from verified event records in code, never from retrieved windows or model prose. The browser exposes it as an experimental count mode with per-event playback.

Proof: count suite 6 passed ungated against the labelled local VLM fixture; full model-enabled regression 535 passed, 2 private-checkout skips, 2 existing warnings. Real browser run: "the robot arm moves a cup" on the fresh coffee upload returned 1 occurrence, 3 of 3 intervals checked, with the two adjacent-window reports merged into one event spanning 16.4-20.1 seconds and zero console errors. [Evidence](evaluation/event-counting-e2e-results.json).

Known limits: observed counts over checked partitions only; the half-second merge rule cannot separate events closer than that; sparse frame sampling can miss brief actions; long scans are budget-bounded; cross-camera identity and repeated-event semantics beyond temporal overlap remain unbuilt.
