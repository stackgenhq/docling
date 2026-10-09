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
`docling-serve-cpu` base: Serve 1.36.0, Core 2.99.0 and Jobkit 3.8.1. It supports
CPU execution, not GPU/CUDA. Runtime installation is offline with `--no-deps`;
other base dependencies are not upgraded. Do not install an overlapping legacy
`docling` distribution alongside `docling-slim`.

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

`stackgen-serve.yml` tests native AMD64 and ARM64 images on pull requests and
relevant `main` pushes. After both test jobs pass, a `main` push publishes
`ghcr.io/stackgenhq/docling-serve:main` and `:sha-<commit>` as a multi-platform image.
Manual dispatch is test-only unless `publish` is selected on `main`. PRs cannot
publish. Publication rebuilds wheels from the tested revision with the same
pinned base and build constraints; it does not promote the local test image IDs.

GHCR login uses `GITHUB_TOKEN` with package-write permission only in the publish
job. Organisation package policy and native runner access must permit this.
The workflow summary reports the manifest digest; deployments should use it.
Publishing does not deploy or update downstream deployment image references.

Remote CI and publication have not been executed. Local checks cover native
ARM64 and emulated AMD64, not native AMD64 capacity. Vulnerability remediation
is deferred; these tests are not a security approval. Production registry access,
concurrent large uploads, and upload-through-search acceptance remain required.
