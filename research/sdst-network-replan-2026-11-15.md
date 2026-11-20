# SDST image transport re-plan — 15 November 2026

The image preparation step is stopped after two failures. This worker made only small network requests from `sol-login05`. No job was submitted, no image layer was downloaded, no package was installed, and no runtime code was changed.

## Failure evidence

Read both original files under `/scratch/psheta12/video-search-sdst-20261115/logs`:

- `runtime-1609074.log`: job failed after about 25 seconds.
- `runtime-1609248.log`: job failed after about 17 seconds.

Both logs end before any layer download:

```text
pinging container registry registry-1.docker.io:
Get "https://registry-1.docker.io/v2/": net/http: TLS handshake timeout
```

The logs prove a registry handshake failure. They do not show a package, Torch, CUDA, source or checkpoint failure. Keep both logs. Do not submit the same build a third time.

## Small Sol login checks

Python `urllib` requests and curl ran on `sol-login05`; Apptainer reports version `1.5.4-1.el8`. No proxy environment variable was set. Requests used certificate verification, with 10–15-second time limits. Token response bodies were not printed or saved.

| Request | Result |
| --- | --- |
| Docker Hub `/v2/`, Python | Expected HTTP 401 in 0.205 seconds; normal bearer challenge |
| Docker Hub public repository token | HTTP 200 in 0.187 seconds |
| Docker Hub `/v2/`, curl IPv4 | Expected HTTP 401; TLS 0.129 seconds, total 0.190 seconds |
| Docker Hub `/v2/`, curl IPv6 | Connection failure, curl exit 7; no TLS connection |
| Google mirror `/v2/` | Expected HTTP 401 with Google mirror bearer challenge |
| Google mirror public repository token | HTTP 200; token present, value not shown |
| Google mirror pinned manifest | HTTP 200; 3,680 bytes; exact expected SHA-256 |
| Google mirror image config | HTTP 200; 20,908 bytes; exact expected SHA-256 |
| Google mirror 16 layer HEAD requests | All HTTP 200; every Content-Length equals the pinned manifest; no body read |

Docker DNS returned both IPv4 and IPv6 addresses. The Google mirror also had both families. Direct Docker Hub TLS works on login now. Therefore these login checks do **not** reproduce the compute job's Go-client timeout. A compute-node route, transient failure or client/address-family difference remains possible. IPv6 failure alone does not prove the cause: a client can fall back to IPv4. No DNS, proxy, TLS or firewall setting was changed.

The exact same image is available at Google's mirror:

```text
docker://mirror.gcr.io/pytorch/pytorch@sha256:42204bca460bb77cbd524577618e1723ad474e5d77cc51f94037fffbc2c88c6f

Manifest SHA-256:
42204bca460bb77cbd524577618e1723ad474e5d77cc51f94037fffbc2c88c6f
Config SHA-256:
8a2cd2aba91fa1daef17b57f2cea623488c179d82a3166c67898289383553cd0
Platform: linux/amd64
Layer count: 16
Compressed layer bytes: 9,063,269,507
```

Both response payload hashes were computed on Sol. The manifest contains the same config and all layer digests already selected from the official PyTorch image. All 16 layer HEAD responses stayed on `mirror.gcr.io`. A HEAD response proves current endpoint access and expected length, not full payload integrity or sustained transfer speed.

Google documents `mirror.gcr.io` as its managed Docker Hub cache. It does not promise that a particular image stays cached. Its documented Docker setup can fall back to Docker Hub; **do not use that fallback behavior here**. Use the explicit mirror URI and digest as a new, recorded transport choice. Apptainer supports explicit OCI registry hostnames in `docker://` URIs. [Google cache documentation](https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images), [Apptainer registry support](https://apptainer.org/docs/user/latest/docker_and_oci.html).

## Proposed next step

1. Record acceptance of this transport re-plan. Preserve the failed scripts/logs and the chosen Torch 2.2.1 / CUDA 12.1 image identity.
2. In the next **allocated CPU preparation** job, first repeat small mirror token, manifest and config requests on that allocated node. Require HTTP 200 and both exact payload hashes. Stop before the build if any check fails. This checks the node class that matters; login success alone is insufficient.
3. Build from the explicit mirror URI above, using the existing private cache, temporary output, lock, resource bounds and atomic SIF publication. Record both the mirror transport URI and the canonical PyTorch digest. Do not substitute a tag, another Torch version, a proxy, insecure TLS or a bundled shared library.
4. Require Apptainer's normal OCI digest checks during full transfer. After conversion, record the final SIF SHA-256 and environment checks. A SIF has its own hash; do not compare its bytes to an OCI manifest hash. Continue the existing package/import checks only after this image stage passes.
5. Allow at most two failures of this new transport step. On the second failure, stop and preserve both logs. No SDST GPU gate starts until CPU runtime preparation passes.

This worker did not implement the proposed URI or submit the job. The parent owns execution within the user's approved campaign and project approval rules.

## If the mirror cannot complete

Use an explicit offline transport plan, not another runtime. On a host with working registry access, obtain the same pinned PyTorch image and export a Docker/OCI archive. Save its archive SHA-256, source manifest/config digests and checked blob identities. Transfer the complete archive to Sol, compare the archive hash, then convert it in an allocated CPU job. Apptainer documents `docker-archive:` input for a `docker save` archive; use the input format that matches the actual export. This needs extra local disk, transfer time and a separate reviewed procedure. No export, transfer or conversion was attempted here. [Apptainer archive conversion](https://apptainer.org/docs/user/main/build_a_container.html).

Unrun: compute-node mirror preflight, Apptainer mirror build, full layer transfers/hashes, SIF conversion, runtime package/import checks and GPU checks. Root cause is not proved; the exact-image mirror is a tested transport candidate, not a completed fix.
