# Security notes

This document describes the security posture of Local Video Search as shipped
in this repository. It is written for one reader: the person who runs this app
on their own machine.

## Threat model

The app is single-user and self-hosted. It assumes:

- The machine and the user account are trusted. The app is not a multi-tenant
  service and has no authentication.
- The network boundary is the loopback interface. Compose publishes the API on
  `127.0.0.1:8000` only. The database has no published port.

**What the app protects:**

- Your video library stays on your machine. The library folder is bind-mounted
  **read-only** into the containers; the app cannot write into it.
- Uploaded videos stay local. They live in a named Docker volume on your host.
- The database (paths, fingerprints, embeddings, descriptions, speech text)
  stays local, inside the Compose network.
- Speech transcription runs locally (Whisper), as do the SigLIP2 image and text
  encoders used for search. Query images are embedded locally; they are not
  uploaded.

**What leaves the machine:** sampled video frames and the matching window text,
sent to the vision endpoint you configure. With `VISION_PROVIDER=qwen` that is
your `QWEN_BASE_URL` (this can be a service on your own machine, for example
via `host.docker.internal`). With `VISION_PROVIDER=gemma` it is the ASU-hosted
service at `VOYAGER_BASE_URL`. Full videos are never uploaded.

**Keys:** vision API keys live in `.env` on the host (gitignored), are passed
to the containers as environment variables, and are never returned by any API
endpoint. Database errors are logged without the connection string and the
error response omits it too.

## Network posture

- API: published on `127.0.0.1:8000` only. Not reachable from other machines.
- Database: reachable only on the internal Compose network. No published port.
- The app rejects requests whose `Host` is not localhost (`TrustedHostMiddleware`).

## Response headers

Every response from the API carries:

- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src
  'self'; media-src 'self'; img-src 'self' data:; frame-ancestors 'none';
  base-uri 'none'; form-action 'self'` — same-origin scripts, styles and media
  only; the page cannot be framed.
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: same-origin`
- `X-Request-ID` — a correlation ID, useful when reading logs.

Non-GET/HEAD/OPTIONS requests that look cross-origin (`Sec-Fetch-Site:
cross-site`, or a mismatched `Origin`) are rejected with `403` before they reach
any handler. There is no CORS configuration; the browser UI is same-origin.

## Uploads

`POST /uploads` accepts one streamed video at a time:

- Size cap: `UPLOAD_MAX_BYTES`, default 2 GiB. The declared `Content-Length`
  is checked first; the stream is also cut off if it grows past the cap (`413`).
- File names: at most 240 bytes, no control characters, no `/`, `\`, or `:`,
  and a known video extension only (`.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`,
  `.m4v`, `.mts`, `.m2ts`, `.mpeg`, `.mpg`). Anything else is `422`.
- Bytes are staged to a `.part` file, fsynced, hashed (SHA-256), and hard-linked
  into place. A re-sent upload with the same `X-Upload-ID` is idempotent;
  concurrent use of one ID returns `409`.
- Videos are stored under `/__uploads/<upload-id>/<filename>` inside the
  uploads volume, and the upload is only accepted if the API can read the exact
  same bytes back through its read-only view of that volume.

### The `/__uploads` marker

Uploaded recordings are recorded in the database with a marker prefix:
`__uploads` followed by the upload ID. When any part of the app resolves such a
path, it is mapped into the read-only mount of the uploads volume
(`/uploaded-media`), never into your library folder. Import, search and
playback therefore use one code path for both sources, while the two storage
areas stay separate: the library is read-only, uploads are a separate volume,
and only the API can write there (the worker sees it read-only too).

## Container hardening

- The app image runs as non-root user `app`, UID 10001.
- The API and worker containers have a **read-only root filesystem**; frame
  sampling, media probing and wav scratch files go to a size-bounded tmpfs at
  `/tmp` (1 GiB, mode 1777).
- Memory limits bound a runaway job: API 3 GiB, worker 4 GiB, database 2 GiB.
  No CPU pinning — the limits stop unbounded growth, they do not reserve RAM.
- The worker gets a 10-minute stop grace period so a SIGTERM lets the current
  job finish (audio extraction alone may run up to 600 s). If it is killed
  anyway, the job's 60-second lease expires and the remaining windows are
  re-claimed on the next run.
- The base image is pinned by digest (`python:3.12-slim-bookworm@sha256:...`)
  and the one `apt-get` layer removes its package lists in the same step.

## Known limits

Be honest with yourself about these before exposing anything:

- **No authentication.** Anything that can reach `127.0.0.1:8000` — any local
  process or user on this machine — can use the full API, including imports,
  uploads and deletion-free search. This is fine for one trusted machine and
  wrong for anything shared.
- Do not put this API behind a public reverse proxy or tunnel without adding
  an authentication layer in front of it first.
- **Single user.** There is no account model, no audit trail of who did what.
- Database credentials are static values in `compose.yaml`. This is acceptable
  only because the database has no published port; change them before any
  non-local deployment.
- The cross-origin write block and CSP are browser mitigations. A non-browser
  local client is not stopped by them — which is the same trust boundary as
  above.

## Reporting a vulnerability

Placeholder — this project does not yet have a formal disclosure policy.
Until one exists, please do not publish unreported security issues. Open a
private security advisory on the GitHub repository, or contact the maintainer
first.
