# Build the wheels from this checkout before building with the repository root context.
# CPU execution only. Use the upstream CPU variant instead of CUDA dependencies.
FROM ghcr.io/docling-project/docling-serve-cpu:v1.38.2@sha256:7a480a1604fa3b42efeddc7db9527690d9f9bc903226136013e2bfe6b1a4dfb0
# The base ships a vulnerable rsync (RHSA-2026:67462) and no package requires it.
# Only the unused Ray autoscaler calls it. Remove it offline; do not upgrade packages.
USER 0
RUN rpm -e rsync && ! rpm -q rsync
USER 1001
COPY --chown=1001:0 integrations/stackgen_serve/dist/*.whl /tmp/fork-wheels/
# The base has docling-slim, not the legacy overlapping docling distribution.
# Fail if that layout changes. Do not resolve or upgrade dependencies.
# Xray reports the example keys in the transformers testing_utils bytecode as secrets.
RUN python -c "from importlib.metadata import distributions; assert 'docling' not in {d.metadata['Name'] for d in distributions()}" \
    && python -m pip install --no-index --no-deps --force-reinstall /tmp/fork-wheels/*.whl \
    && rm -rf /tmp/fork-wheels \
    && find /opt/app-root -xdev -path '*/transformers/__pycache__/testing_utils*.pyc' -delete \
    && ! find /opt/app-root -xdev -path '*/transformers/__pycache__/testing_utils*.pyc' | grep -q .
ENTRYPOINT ["/opt/app-root/bin/python", "-m", "stackgen_docling"]
CMD ["run"]
