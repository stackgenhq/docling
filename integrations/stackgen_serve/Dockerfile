# Build the wheels from this checkout before building with the repository root context.
# CPU execution only. Use the upstream CPU variant instead of CUDA dependencies.
FROM ghcr.io/docling-project/docling-serve-cpu:v1.38.2@sha256:7a480a1604fa3b42efeddc7db9527690d9f9bc903226136013e2bfe6b1a4dfb0 AS cleaned
# The base image repository still has python3 3.9.25-10.el9 (CVE-2026-115557).
# Xray names the fix 3.9.25-16.el9_9. AlmaLinux publishes that build.
# Install the pinned RPMs before the filesystem copy. dnf and rpm need Python 3.9.
# Do not upgrade any other package.
# The base ships a vulnerable rsync (RHSA-2026:67462) and no package requires it.
# Only the unused Ray autoscaler calls it. Remove it offline.
ARG TARGETARCH
COPY integrations/stackgen_serve/python3-rpms.txt /tmp/python3-rpms.txt
COPY integrations/stackgen_serve/rpms/${TARGETARCH}/ /tmp/python3-rpms/
USER 0
RUN /usr/bin/python3 - <<'PY'
import hashlib
import os
import pathlib
import subprocess

machine = {"x86_64": "amd64", "aarch64": "arm64"}[os.uname().machine]
root = pathlib.Path("/tmp/python3-rpms")
expected = []
for line in pathlib.Path("/tmp/python3-rpms.txt").read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    arch, filename, sha, _url = stripped.split()
    if arch == machine:
        expected.append((filename, sha))
if len(expected) != 2:
    raise SystemExit(f"Expected 2 RPMs for {machine}, found {len(expected)}.")
present = sorted(path.name for path in root.glob("*.rpm"))
names = sorted(name for name, _sha in expected)
if present != names:
    raise SystemExit(f"RPM files {present} do not match {names}.")
for filename, sha in expected:
    digest = hashlib.sha256((root / filename).read_bytes()).hexdigest()
    if digest != sha:
        raise SystemExit(f"{filename} sha256 {digest} != {sha}.")
subprocess.run(
    ["rpm", "-Uvh", *[str(root / filename) for filename, _sha in expected]],
    check=True,
)
completed = subprocess.run(
    ["rpm", "-q", "python3", "python3-libs"],
    check=True,
    capture_output=True,
    text=True,
)
installed = [line for line in completed.stdout.splitlines() if line]
stale = [line for line in installed if "3.9.25-16.el9_9" not in line]
if not installed or stale:
    raise SystemExit(f"Unexpected system Python: {installed}")
print("\n".join(installed))
for path in root.glob("*"):
    path.unlink()
root.rmdir()
pathlib.Path("/tmp/python3-rpms.txt").unlink()
PY
RUN rpm -e rsync && ! rpm -q rsync
USER 1001
COPY --chown=1001:0 integrations/stackgen_serve/dist/*.whl /tmp/fork-wheels/
# The base has docling-slim, not the legacy overlapping docling distribution.
# Fail if that layout changes. Do not resolve or upgrade dependencies.
# Xray reports the example keys in transformers testing_utils. Delete the source
# and the bytecode. The build fails if either file was not there to delete.
RUN python -c "from importlib.metadata import distributions; assert 'docling' not in {d.metadata['Name'] for d in distributions()}" \
    && python -m pip install --no-index --no-deps --force-reinstall /tmp/fork-wheels/*.whl \
    && rm -rf /tmp/fork-wheels \
    && sources=$(find /opt/app-root -xdev -path '*/transformers/testing_utils.py' -print -delete) \
    && bytecode=$(find /opt/app-root -xdev -path '*/transformers/__pycache__/testing_utils*.pyc' -print -delete) \
    && test -n "$sources" \
    && test -n "$bytecode" \
    && ! find /opt/app-root -xdev -path '*/transformers/testing_utils.py' | grep -q . \
    && ! find /opt/app-root -xdev -path '*/transformers/__pycache__/testing_utils*.pyc' | grep -q .

# Xray reads every layer. A delete in this image does not rewrite the base layer.
# Copy the merged filesystem so the published layers do not contain those files.
# Scratch does not keep the base config. These values match docling-serve-cpu
# v1.38.2 on amd64 and arm64, including ARCH=x86_64. base-runtime.json records
# them. The image test compares the built image to that file. Update both when
# the base digest changes.
FROM scratch
COPY --from=cleaned / /
ENV VERSION=9 \
    STI_SCRIPTS_URL=image:///usr/libexec/s2i \
    STI_SCRIPTS_PATH=/usr/libexec/s2i \
    APP_ROOT=/opt/app-root \
    HOME=/opt/app-root/src \
    PLATFORM=el9 \
    NODEJS_VER=22 \
    PYTHON_VERSION=3.12 \
    PATH=/opt/app-root/src/.local/bin/:/opt/app-root/src/bin:/opt/app-root/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=off \
    NAME=python3 \
    ARCH=x86_64 \
    SUMMARY="Platform for building and running Python 3.12 applications" \
    DESCRIPTION="Python 3.12 available as container is a base platform for building and running various Python 3.12 applications and frameworks. Python is an easy to learn, powerful programming language. It has efficient high-level data structures and a simple but effective approach to object-oriented programming. Python's elegant syntax and dynamic typing, together with its interpreted nature, make it an ideal language for scripting and rapid application development in many areas on most platforms." \
    BASH_ENV=/opt/app-root/bin/activate \
    ENV=/opt/app-root/bin/activate \
    PROMPT_COMMAND=". /opt/app-root/bin/activate" \
    TESSDATA_PREFIX=/usr/share/tesseract/tessdata/ \
    OMP_NUM_THREADS=4 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/app-root \
    DOCLING_SERVE_ARTIFACTS_PATH=/opt/app-root/src/.cache/docling/models \
    LD_PRELOAD=/usr/local/lib/libmimalloc.so
USER 1001
WORKDIR /opt/app-root/src
EXPOSE 5001 8080
ENTRYPOINT ["/opt/app-root/bin/python", "-m", "stackgen_docling"]
CMD ["run"]
