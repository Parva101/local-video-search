# Voice project option: test calls, find failures, improve turn detection

Checked November 4, 2026. This is a project assessment, not a tested product claim.

## Best fit

Build an open, self-hosted voice-agent test system with a trained speech component. Its user is an engineer who needs to know why an agent cuts callers off, waits too long, loses corrections, or records the wrong details. The system should replay audio through a real agent, preserve timing and tool-call evidence, compare versions, and help fix one measured failure class.

This adds audio processing and model training to the user's existing text-first agent QA work. It can be a complete developer product without training an entire speech-to-speech model.

## What already exists

Hamming documents audio-level tests for interruptions, noise, latency, network faults, and call outcomes. Coval offers simulated voices, noise conditions, joint conversation/audio/tool evaluation, comparisons, and CI use. These first-party pages establish existing product scope; they do not independently prove product quality. A new project must not claim to invent voice-agent testing. [Hamming WebRTC testing](https://hamming.ai/resources/webrtc-call-quality-testing-voice-agents), [Coval simulation](https://www.coval.ai/products/simulation)

Audio turn detection also exists. Pipecat Smart Turn publishes an audio-native model, weights, training code, and data. Current LiveKit documentation describes an audio-based full model and a local CPU mini model. A comparison must include current audio models, not only silence thresholds or the older LiveKit text detector. [Smart Turn](https://github.com/pipecat-ai/smart-turn), [LiveKit turn detector](https://docs.livekit.io/agents/logic/turns/turn-detector/)

The proposed distinction is reproducible public audio tests, clear failure traces, and a measured model improvement in a defined setting. This is a proposed focus, not a verified market gap.

## Concrete training task

Start with an end-of-turn classifier: given recent speech, decide whether the caller has finished. Target hesitation, spoken numbers, self-correction, and background noise. First measure the stock models; select the weakest useful subset before committing to a training target.

Smart Turn's training code uses a Whisper-tiny encoder and a classification model. It is a concrete base to adapt and benchmark on Sol. Use the existing training path before adding a new model architecture. A one-GPU pilot is a reasonable planning choice; actual memory and runtime are unmeasured. [Smart Turn training code](https://github.com/pipecat-ai/smart-turn/blob/main/train.py)

An optional later experiment can provide dialogue context, such as whether the agent asked for a multi-part number. That needs paired context/audio labels; the inspected public data alone does not establish this training set.

## Public data feasibility

Pipecat publishes approximately 271,000 training clips and 31,500 test clips. Cards label both datasets CC BY 4.0. Fields include language, endpoint label, filler flags, synthetic status, and source. Use a manageable subset first. [Training data](https://huggingface.co/datasets/pipecat-ai/smart-turn-data-v3.2-train), [Test data](https://huggingface.co/datasets/pipecat-ai/smart-turn-data-v3.2-test)

These are endpoint clips, not a complete benchmark of live calls, interruptions, tool actions, or latency. Keep public test data out of model selection. Add a separate human-recorded evaluation set with speaker consent and held-out speakers. Do not treat synthetic speech success as proof of real caller performance. Pipecat's contribution guide explains complete/incomplete labels and consent expectations. [Data guide](https://github.com/pipecat-ai/smart-turn/blob/main/docs/data_generation_contribution_guide.md)

OpenSLR provides room responses and noise at 16 kHz under a stated Apache 2.0 license. This supports repeatable noise and reverberation tests. Keep noise sources separate across training and evaluation. [OpenSLR noise data](https://www.openslr.org/28/)

## Useful finished scope and evaluation

Proposed product scope:

1. A LiveKit adapter that sends timed audio fixtures to an agent and records audio, transcript, model timing, and tool events.
2. Test cases for pauses, corrections, interruption, silence, noise, and required field capture.
3. A report with replay, event timeline, failure type, and version comparison.
4. A trained turn model exported for local use, plus a public benchmark and repeatable Sol jobs.
5. A command that returns failure for a regression, so teams can use it in CI.

Use VAD plus fixed silence, stock Smart Turn, and the adapted model as core baselines. Add LiveKit's current local detector where integration permits. Report early cutoff rate and response-delay distributions together: waiting indefinitely must not count as success. Measure interruption stop time separately; endpoint classification does not solve all interruption problems. Also report field accuracy and task completion from actual tool outputs, clean-speech regressions, and CPU inference cost.

No model or commercial service was tested. Real user adoption, superior model quality, and market differentiation remain unproven; data quality and live-call evaluation are the main work.
