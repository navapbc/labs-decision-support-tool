##################################################
# Constants
##################################################

APP_NAME := main-app

# Adding this to the end of a script that outputs JSON will convert
# it to a readable format with timestamps and color-coding.
#
# Note that you can also change the LOG_FORMAT env var to switch
# between JSON & human readable format. This is left in place
# in the event JSON is output from a process we don't log.
DECODE_LOG := 2>&1 | python3 -u src/logging/util/decodelog.py

# Required for CI flags below to work properly
SHELL = /bin/bash -o pipefail

# The APP_DIR variable is the path from the root of the repository to this Makefile.
# This variable is used to display errors from Flake8 and MyPy in the 'Files Changed'
# section of a pull request. If this is set to the incorrect value, you won't be able
# to see the errors on the correct files in that section
APP_DIR := app
ifdef CI
 DOCKER_EXEC_ARGS := -T -e CI -e PYTEST_ADDOPTS="--color=yes"
 FLAKE8_FORMAT := '::warning file=$(APP_DIR)/%(path)s,line=%(row)d,col=%(col)d::%(path)s:%(row)d:%(col)d: %(code)s %(text)s'
 MYPY_FLAGS := --no-pretty
 MYPY_POSTPROC := | perl -pe "s/^(.+):(\d+):(\d+): error: (.*)/::warning file=$(APP_DIR)\/\1,line=\2,col=\3::\4/"
else
 FLAKE8_FORMAT := default
endif

# By default, all python/poetry commands will run inside of the docker container
# if you wish to run this natively, add PY_RUN_APPROACH=local to your environment vars
# You can set this by either running `export PY_RUN_APPROACH=local` in your shell or add
# it to your ~/.zshrc file (and run `source ~/.zshrc`)
ifeq "$(PY_RUN_APPROACH)" "local"
PY_RUN_CMD := poetry run
else
PY_RUN_CMD := docker compose run $(DOCKER_EXEC_ARGS) --rm $(APP_NAME) poetry run
endif

# Docker user configuration
# This logic is to avoid issues with permissions and mounting local volumes,
# which should be owned by the same UID for Linux distros. Mac OS can use root,
# but it is best practice to run things as with least permission where possible

# Can be set by adding user=<username> and/ or uid=<id> after the make command
# If variables are not set explicitly: try looking up values from current
# environment, otherwise fixed defaults.
# uid= defaults to 0 if user= set (which makes sense if user=root, otherwise you
# probably want to set uid as well).
ifeq ($(user),)
RUN_USER ?= $(or $(strip $(USER)),nodummy)
RUN_UID ?= $(or $(strip $(shell id -u)),4000)
else
RUN_USER = $(user)
RUN_UID = $(or $(strip $(uid)),0)
endif

export RUN_USER
export RUN_UID

release-build:
	docker buildx build \
		--target release \
		--platform=linux/amd64 \
		--build-arg RUN_USER=$(RUN_USER) \
		--build-arg RUN_UID=$(RUN_UID) \
		$(OPTS) \
		.

##################################################
# Local Development Environment Setup
##################################################

setup-local:
	# Configure poetry to use virtualenvs in the project directory
	poetry config virtualenvs.in-project true

	# Install dependencies
	poetry install --no-root

##################################################
# API Build & Run
##################################################

build:
	docker compose build

start:
	docker compose up --detach

start-debug:
	docker compose -f ../docker-compose.yml -f ../docker-compose.debug.yml up --detach

run-logs: start
	docker compose logs --follow --no-color $(APP_NAME)

init: build init-db

clean-volumes: ## Remove project docker volumes (which includes the DB state)
	docker compose down --volumes

stop:
	docker compose down

check: format-check lint test

##################################################
# DB & migrations
##################################################

#########################
# DB running / setup
#########################

# Docker starts the image for the DB but it's not quite
# ready to accept connections so we add a brief wait script
init-db: start-db db-migrate

start-db:
	docker compose up --detach main-db
	./bin/wait-for-local-db.sh

## Destroy current DB, setup new one
db-recreate: clean-volumes init-db

#########################
# DB Migrations
#########################

alembic_config := ./src/db/migrations/alembic.ini
alembic_cmd := $(PY_RUN_CMD) alembic --config $(alembic_config)

db-migrate: ## Apply pending migrations to db
	$(PY_RUN_CMD) db-migrate

db-migrate-down: ## Rollback last migration in db
	$(PY_RUN_CMD) db-migrate-down

db-migrate-down-all: ## Rollback all migrations
	$(PY_RUN_CMD) db-migrate-down-all

check-migrate-msg:
ifndef MIGRATE_MSG
	$(error MIGRATE_MSG is undefined)
endif

db-migrate-create: check-migrate-msg ## Create database migration with description MIGRATE_MSG
	$(alembic_cmd) revision --autogenerate -m "$(MIGRATE_MSG)"

MIGRATE_MERGE_MSG := Merge multiple heads
db-migrate-merge-heads: ## Create a new migration that depends on all existing `head`s
	$(alembic_cmd) merge heads -m "$(MIGRATE_MERGE_MSG)" $(args)

db-migrate-current: ## Show current revision for a database
	$(alembic_cmd) current $(args)

db-migrate-history: ## Show migration history
	$(alembic_cmd) history $(args)

db-migrate-heads: ## Show migrations marked as a head
	$(alembic_cmd) heads $(args)

##################################################
# Testing
##################################################

test: ## Run all tests except for audit logging tests
	$(PY_RUN_CMD) pytest -m "not audit" $(args)

test-audit: ## Run audit logging tests
	$(PY_RUN_CMD) pytest -m "audit" $(args)

test-watch: ## Run tests continually and watch for changes
	$(PY_RUN_CMD) pytest-watch --clear $(args)

test-coverage: ## Run tests and generate coverage report
	$(PY_RUN_CMD) coverage run --branch --source=src -m pytest -m "not audit" $(args)
	$(PY_RUN_CMD) coverage report

test-coverage-report: ## Open HTML test coverage report
	$(PY_RUN_CMD) coverage html --directory .coverage_report
	open .coverage_report/index.html

test-coverage-xml-report: ## Generate test coverage report for adding to PR
	$(PY_RUN_CMD) coverage xml -o coverage_report.xml

##################################################
# Formatting and linting
##################################################

format: ## Format files
	$(PY_RUN_CMD) isort --atomic src tests
	$(PY_RUN_CMD) black src tests

format-check: ## Check file formatting
	$(PY_RUN_CMD) isort --atomic --check-only src tests
	$(PY_RUN_CMD) black --check src tests

lint: lint-py ## Lint

lint-py: lint-flake lint-mypy

lint-flake:
	$(PY_RUN_CMD) flake8 --format=$(FLAKE8_FORMAT) src tests

lint-mypy:
	$(PY_RUN_CMD) mypy --show-error-codes $(MYPY_FLAGS) src $(MYPY_POSTPROC)

lint-security: # https://bandit.readthedocs.io/en/latest/index.html
	$(PY_RUN_CMD) bandit -c pyproject.toml -r . --number 3 --skip B101 -ll -x ./.venv


##################################################
# Miscellaneous Utilities
##################################################

login: start ## Start shell in running container
	docker exec -it $(APP_NAME) bash

notebook: start
	docker exec -it main-app sh -c "poetry run jupyter notebook --ip 0.0.0.0 --no-browser --allow-root"

# Pauses for 5 seconds
sleep-5:
	sleep 5

help: ## Prints the help documentation and info about each command
	@grep -E '^[/a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'


##################################################
# ETL
##################################################

check-ingest-arguments:
ifndef DATASET_ID
	$(error DATASET_ID is undefined)
endif
ifndef BENEFIT_PROGRAM
	$(error BENEFIT_PROGRAM is undefined)
endif
ifndef BENEFIT_REGION
	$(error BENEFIT_REGION is undefined)
endif
ifndef FILEPATH
	$(error FILEPATH is undefined)
endif

ingest-guru-cards: check-ingest-arguments
	$(PY_RUN_CMD) ingest-guru-cards $(DATASET_ID) $(BENEFIT_PROGRAM) $(BENEFIT_REGION) $(FILEPATH)

ingest-policy-pdfs: check-ingest-arguments
	$(PY_RUN_CMD) ingest-policy-pdfs $(DATASET_ID) $(BENEFIT_PROGRAM) $(BENEFIT_REGION) $(FILEPATH)

ingest-bem-pdfs: check-ingest-arguments
	$(PY_RUN_CMD) ingest-bem-pdfs $(DATASET_ID) $(BENEFIT_PROGRAM) $(BENEFIT_REGION) $(FILEPATH)

ingest-edd-web: check-ingest-arguments
	$(PY_RUN_CMD) ingest-edd-web $(DATASET_ID) $(BENEFIT_PROGRAM) $(BENEFIT_REGION) $(FILEPATH)
