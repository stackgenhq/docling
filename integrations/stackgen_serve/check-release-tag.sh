#!/bin/sh
# Check a release tag against the adapter version and print the image version.
# Usage: sh integrations/stackgen_serve/check-release-tag.sh TAG [PYPROJECT]
# A hotfix tag vX.Y.Z-hotfix.N uses adapter version X.Y.Z.
set -eu
tag=${1:?usage: check-release-tag.sh TAG [PYPROJECT]}
pyproject=${2:-integrations/stackgen_serve/pyproject.toml}
case $tag in
    *"
"*)
        echo 'Tag must be one line.' >&2
        exit 1
        ;;
esac
if ! printf '%s\n' "$tag" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+(-hotfix\.[0-9]+)?$'; then
    echo "Tag must be vX.Y.Z or vX.Y.Z-hotfix.N: $tag" >&2
    exit 1
fi
version=${tag#v}
adapter=$(sed -n 's/^version = "\([^"]*\)".*/\1/p' "$pyproject" | head -n 1)
if [ -z "$adapter" ]; then
    echo "No version in $pyproject" >&2
    exit 1
fi
if [ "${version%%-hotfix.*}" != "$adapter" ]; then
    echo "Tag $tag does not match adapter version $adapter in $pyproject" >&2
    exit 1
fi
printf '%s\n' "$version"
