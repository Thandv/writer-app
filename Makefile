# writer-app — common tasks.
#
#   make install       Install in editable mode with UI + test extras
#   make corpus        Build the reference corpus (style cards + craft + Gutenberg)
#   make test          Run the test suite
#   make ui            Launch the Streamlit UI
#   make build         Build the self-extracting installer (dist/writer-app-install.sh)
#   make clean         Remove build artefacts

PY        := python3
DIST      := dist
INSTALLER := $(DIST)/writer-app-install.sh
VERSION   := $(shell sed -n 's/^version *= *"\(.*\)"/\1/p' pyproject.toml | head -1)

.PHONY: help install corpus test ui build installer wheel sdist clean

help:
	@echo "writer-app v$(VERSION) — make targets:"
	@echo "  install   Editable install with all extras"
	@echo "  corpus    Build the reference corpus"
	@echo "  test      Run pytest"
	@echo "  ui        Launch the Streamlit UI"
	@echo "  build     Build the self-extracting installer"
	@echo "  wheel     Build the Python wheel"
	@echo "  clean     Remove build artefacts"

install:
	$(PY) -m pip install -e ".[dev]"

corpus:
	$(PY) -m writer_app.shared.corpus build

test:
	$(PY) -m pytest tests -q

ui:
	streamlit run ui/app.py

wheel:
	$(PY) -m pip install --quiet build
	$(PY) -m build --wheel

sdist:
	$(PY) -m pip install --quiet build
	$(PY) -m build --sdist

build installer: $(INSTALLER)

$(INSTALLER): scripts/build-installer.sh scripts/install.sh
	@mkdir -p $(DIST)
	bash scripts/build-installer.sh "$(INSTALLER)" "$(VERSION)"

clean:
	rm -rf $(DIST) build *.egg-info src/*.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
