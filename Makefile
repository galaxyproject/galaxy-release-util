# Location of virtualenv used for development.
VENV?=.venv
IN_VENV=if [ -f $(VENV)/bin/activate ]; then . $(VENV)/bin/activate; fi;
UPSTREAM?=galaxyproject
SOURCE_DIR?=galaxy-release-util
PROJECT_URL?=https://github.com/galaxyproject/galaxy-release-util
PROJECT_NAME?=galaxy-release-util
TEST_DIR?=tests
# Open resource on Mac OS X or Linux
OPEN_RESOURCE=bash -c 'open $$0 || xdg-open $$0'
 
.PHONY: clean-pyc clean-build docs clean

help:
	@egrep '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

setup-venv: ## setup a development virtualenv in current directory
	if [ ! -d $(VENV) ]; then virtualenv $(VENV); exit; fi;
	$(IN_VENV) pip install -r dev-requirements.txt
	$(IN_VENV) pip install -e .

lint: ## check style using tox and flake8 for Python 2 and Python 3
	$(IN_VENV) tox -e lint

test: ## run tests with the default Python (faster than tox)
	$(IN_VENV) tox -e unit

open-history:  # view HISTORY.rst as HTML.
	rst2html.py HISTORY.rst > /tmp/galaxy_release_util_history.html
	$(OPEN_RESOURCE) /tmp/galaxy_release_util_history.html

dist: clean ## create and check packages
	$(IN_VENV) python -m build
	$(IN_VENV) twine check dist/*
	ls -l dist
