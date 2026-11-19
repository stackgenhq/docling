# StackGen record-table Serve integration

## Benefit

Markdown exports iterate actual table cells instead of constructing
`TableData.grid`. Sparse tables do not allocate a padded rectangle. Explicit
empty values, source coordinates, column/row header flags, merged ranges and
rich content remain available. Each table uses continuous `Record N` blocks, not headings.
The structured document and its JSON export remain unchanged. Parsing, sorting
and output still use memory; this is not protection against all OOM failures.

## Image and startup

This repository owns the exporter and Serve startup adapter. The image installs
both wheels built from this checkout. It uses the digest-pinned upstream
`docling-serve-cpu` base: Serve 1.38.2, Core 2.104.0 and Jobkit 3.9.1. It supports
CPU execution, not GPU/CUDA. Runtime installation is offline with `--no-deps`.
Wheel dependencies stay at the base image versions. Do not install an overlapping legacy
`docling` distribution alongside `docling-slim`.

The build installs pinned AlmaLinux `python3` and `python3-libs` 3.9.25-16.el9_9
before the filesystem copy. That is the build Xray names for CVE-2026-115557
(RHSA-2026:98533). The CentOS Stream mirror used by the base image still has
3.9.25-10.el9. `dnf` and `rpm` keep system Python 3.9. The application stays
on Python 3.12. No other base package is upgraded.

The build removes the base `rsync` package (RHSA-2026:67462). No package needs
it. Only the unused Ray autoscaler calls it. The build also deletes
`transformers` `testing_utils.py` and its bytecode. Xray reports the example
keys in that module as secrets. Xray reads every layer, so a delete in a later
layer still leaves the file in the base layer. The final stage copies the
merged filesystem onto a new image. The published image has that filesystem
and no base layers. Image tests fail if `rsync` or `testing_utils` is present,
if system `python3` or `python3-libs` is not 3.9.25-16.el9_9,
if the image has more than two layers, or if the runtime configuration differs
from the base image.

The launcher enables the exporter before Serve imports. An importable factory
also enables it in spawned workers and reload children. Importing the adapter
alone does not change SDK behavior. Explicit table serializers override its
default. The adapter uses private Core helpers for annotations and caption
placement; update the regression tests before changing the pinned runtime.

## Local validation

Run from the repository root with Python 3.11+, uv and Docker:

```sh
sh integrations/stackgen_serve/build.sh
sh integrations/stackgen_serve/test-image.sh
uvx --from ruff==0.15.12 ruff check --config pyproject.toml integrations/stackgen_serve
uvx --from ruff==0.15.12 ruff format --check --config pyproject.toml integrations/stackgen_serve
make validate
```

Image tests mount only tests and a source-hash manifest, not application source.
They compare the installed converter with the checkout, exercise CSV and HTML
in default/workers/reload modes, and require `pip check` to pass. Containers
have no external network, a 3 GiB memory limit and two CPUs. Models are not loaded.
Process identity and OOM guards prevent health responses from hiding worker loss.
The CSV fixture includes blank lines and explicit empty fields.

For a larger approved UTF-8 CSV, set `CSV` to its absolute path:

```sh
docker run --rm --network=none --memory=4g --cpus=2 \
  --entrypoint /opt/app-root/bin/python \
  -v "$PWD/integrations/stackgen_serve/tests:/tests:ro" \
  -v "$CSV:/fixture/input.csv:ro" stackgen-docling:fork-review \
  /tests/http_smoke.py default --csv /fixture/input.csv --requests 1 --timeout 600
```

Repeat with `workers` and `reload`. The test compares every field and record
label. One worker-mode request does not prove coverage of both workers or
concurrent upload capacity. Memory counters include the test client and startup;
they are not a server-only profile. Do not commit customer files or large fixtures.
These checks do not establish PDF model behavior or upload-to-search acceptance.

## CI and publication

`stackgen-serve.yml` tests native AMD64 and ARM64 images on pull requests,
relevant `main` pushes and release tags. Publication starts only after both test
jobs pass. It rebuilds wheels from the tested revision with the same pinned base
and build constraints; it does not promote the local test image IDs. PRs cannot
publish.

| Trigger | Image tags |
| --- | --- |
| Push to `main` | `main`, `sha-<commit>` |
| Manual run on `main` with `publish` | `main`, `sha-<commit>` |
| Tag `vX.Y.Z` or `vX.Y.Z-hotfix.N` on `main` | The same name: `vX.Y.Z` or `vX.Y.Z-hotfix.N` |
| Manual run on `main` with `alias_tag` and `alias_digest` | The same release tag for an existing digest. No rebuild. |

The `main` tag moves with every merge, including upstream syncs. Pin
deployments to a release tag and its digest: `vX.Y.Z@sha256:<digest>`. The
workflow summary shows this pin. Image labels record the release, the commit,
and the Docling and Serve versions.

### Release

1. In a PR, set `version` in `integrations/stackgen_serve/pyproject.toml` to
   the new release. A hotfix tag `vX.Y.Z-hotfix.N` keeps version `X.Y.Z`.
2. Merge the PR. Tag the merge commit on `main` and push only that tag:
   `git tag v0.2.0 <commit>` and `git push origin v0.2.0`.
3. Wait for the workflow. Copy the pin from its summary to the consumers.

The workflow stops if the tag is not on `main`, if the tag does not match the
adapter version, or if the image tag exists. Do not move or reuse a release tag.
Release a new patch or hotfix version instead.

To name an existing published digest without a rebuild, tag its source commit.
Then run the workflow manually on `main` with `alias_tag` and `alias_digest`.
The run checks the tag and the adapter version, and requires the image revision
label to match the tag commit. A tag on a commit whose workflow has no tag
trigger does not start a build.

Do not publish a GitHub Release. The upstream `pypi.yml` and
`discord-release.yml` workflows run on published releases; a tag push does not
start them. Upstream uses the same `v*` tag names (for example `v2.142.1`). Sync
upstream with `git fetch --no-tags` and do not push upstream tags here.

GHCR login uses `GITHUB_TOKEN` with package-write permission only in the publish
and alias jobs. Organisation package policy and native runner access must permit
this. Publishing does not deploy or update downstream deployment image references.

Remote CI runs native AMD64 and ARM64 tests before each `main` publication.
Those tests check this image. They are not an Xray approval. The published
image contains system `python3` and `python3-libs` 3.9.25-16.el9_9. `dnf` and
`rpm` need system Python 3.9. The application stays on Python 3.12.
Production registry access, concurrent large uploads, and upload-through-search
acceptance remain required.
