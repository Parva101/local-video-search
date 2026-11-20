# SDST preparation review ? 15 November 2026

Read-only code review of `scripts/sol/prepare_sdst.py` and its tests. No code was changed and no Sol job was submitted by the reviewer.

No confirmed launch blocker was found in the full-download, selected extraction, tensor or source-path checks. The host wrapper must create a complete manifest from the pinned Git checkout before the container runs. The container then verifies the detached commit and every listed payload hash without calling Git.

## Checks run

- All 36 focused synthetic tests passed in 0.66 seconds on Windows.
- A live, bounded local `requests` probe on 15 November 2026 used the exact confirmation parser and redirect helper from the preparation script.
- Initial response: HTTP 200; Content-Type `text/html; charset=utf-8`; Content-Length `2460`; no Content-Encoding or Transfer-Encoding.
- Confirmed response: HTTP 200; Content-Type `application/octet-stream`; Content-Length `27292943823`; no Content-Encoding or Transfer-Encoding.
- The first four response bytes were `50 4b 03 04`, the expected ZIP local-header prefix. The response was then closed. No archive was saved. Temporary confirmation parameters were not recorded.

This supports the exact full-response header contract, rather than inferring it from an earlier HTTP 206 range response. It does not prove that a complete stream will finish.

Reserve 100 GiB for up to three retained failed streams, selected extraction and source files. Available filesystem space is not proof of the account quota.

Unrun: complete download, all real feature arrays, the Linux lock and atomic publication on Sol. Full runtime and GPU checks are separate gates.
