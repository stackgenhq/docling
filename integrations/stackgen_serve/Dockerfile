# Build the wheels from this checkout before building with the repository root context.
# CPU execution only. Use the upstream CPU variant instead of CUDA dependencies.
FROM ghcr.io/docling-project/docling-serve-cpu:v1.36.0@sha256:225c8586e20d5d0fc6811a9e0e044fa602bcc4393f00389009bad42d6787b58f
COPY --chown=1001:0 integrations/stackgen_serve/dist/*.whl /tmp/fork-wheels/
# The base has docling-slim, not the legacy overlapping docling distribution.
# Fail if that layout changes. Do not resolve or upgrade dependencies.
RUN python -c "from importlib.metadata import distributions; assert 'docling' not in {d.metadata['Name'] for d in distributions()}" \
    && python -m pip install --no-index --no-deps --force-reinstall /tmp/fork-wheels/*.whl \
    && rm -rf /tmp/fork-wheels
ENTRYPOINT ["/opt/app-root/bin/python", "-m", "stackgen_docling"]
CMD ["run"]
