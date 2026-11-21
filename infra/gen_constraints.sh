#!/bin/sh
# Prints the pins for infra/constraints.txt. Run INSIDE python:3.12.8-slim (the image's Python, so
# markers and wheels match what the image installs), from the repo root:
#   docker run --rm -v "$PWD:/repo:ro" python:3.12.8-slim sh /repo/infra/gen_constraints.sh > /tmp/pins
# then replace everything below the header comment of infra/constraints.txt with /tmp/pins.
# Runtime dependencies come from backend/pyproject.toml; setuptools/wheel pin the build backend
# (applied through PIP_CONSTRAINT, which also reaches pip's isolated build environment).
set -eu
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore
mkdir -p /tmp/src && cd /repo/backend && tar cf - --exclude=.venv --exclude=__pycache__ --exclude=*.egg-info --exclude=tests . | tar xf - -C /tmp/src
python -m venv /tmp/venv
/tmp/venv/bin/pip install -q /tmp/src
echo "# runtime"
/tmp/venv/bin/pip freeze --exclude reader-backend | sort -f
/tmp/venv/bin/pip install -q setuptools wheel
echo "# build backend"
/tmp/venv/bin/pip freeze | grep -iE '^(setuptools|wheel)=='