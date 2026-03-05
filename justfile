# Variables

DEFAULT_PY_VER := "3.10"
PY_VERSIONS := "3.7 3.8 3.9 3.10 3.11 3.12 3.13"

default:
    just --list

# Clean up python bytecode
clean:
    find . -type f -name "*.pyc" -exec rm -f {} \;

# Run tests for a specific version (default: 3.10)
test VER=DEFAULT_PY_VER:
    PY_VER={{ VER }} ./bin/run-test.sh

# Run tests for all supported versions
test-all:
    #!/usr/bin/env bash
    for ver in {{ PY_VERSIONS }}; do
        PY_VER=$ver ./bin/run-test.sh || exit 1;
    done

# Attach to a test session for a specific version
attach VER=DEFAULT_PY_VER:
    PY_VER={{ VER }} ./bin/run-test.sh attach

# Run the Django example
run-example-django:
    ./bin/run-example-django.sh

# Install the dev package locally
install PASSPHRASE="":
    python3 -m pip install \
        --no-cache-dir \
        -v \
        . \
        -Csetup-args="-Dpassphrase={{ PASSPHRASE }}"

# Build the distribution
build-dist:
    #!/usr/bin/env bash
    rm -rf dist/
    if [ -z "$(git status --porcelain --untracked-files=no)" ]; then
        python -m build --sdist -Csetup-args="-Dpassphrase=__DUMMY__" ;
    else
        echo "Please stash your local modification before build dist ...";
        exit 1;
    fi

# Upload distribution to PyPI
upload-dist:
    twine upload dist/*

# Upload distribution to TestPyPI
upload-dist-for-test:
    twine upload -r testpypi dist/*

# Install from TestPyPI
testpypi-install VER PASSPHRASE="":
    python3 -m pip install \
        --index-url https://test.pypi.org/simple/ \
        --extra-index-url https://pypi.org/simple/ \
        --no-cache-dir \
        pyconcrete=={{ VER }} \
        -Csetup-args="-Dpassphrase={{ PASSPHRASE }}"
