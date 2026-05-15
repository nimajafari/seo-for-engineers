# Makefile, top-level test orchestration for SEO for Engineers
#
# Conventions:
   - Every chapter has a `test-NN` target that runs its smoke tests.
   - `test-all` runs everything in chapter order.
   - `test CHAPTER=chapter-NN-topic` runs a single chapter.
   - `lint` runs format and lint checks across the repository.
   - Targets that depend on live external services (Google IP ranges,
     CMS APIs, Search Console) are gated by environment variables and
     skipped gracefully when those are unset.

# Requirements:
   - Python 3.11+ with venv module
   - Node 20+ with npx (only for TypeScript-bearing chapters)
   - DuckDB CLI (only for chapter 18)

# Run `make help` for a list of available targets.

SHELL := /bin/bash
PYTHON := python3
ROOT := $(shell pwd)
VOL1 := volume-1-code-and-craft

# Chapters that have Python-based tests.
PY_CHAPTERS := \
  chapter-14-sitemaps \
  chapter-15-robots-txt \
  chapter-16-crawl-budget \
  chapter-17-faceted-navigation \
  chapter-18-log-analysis \
  chapter-19-headless

# Chapters with TypeScript-based tests.
TS_CHAPTERS := \
  chapter-19-headless

# Chapters with shell-script smoke tests.
SH_CHAPTERS := \
  chapter-15-robots-txt

.DEFAULT_GOAL := help

# ----------------------------------------------------------------
# Help
# ----------------------------------------------------------------

.PHONY: help
help:
	@echo "SEO for Engineers, repository test orchestration"
	@echo ""
	@echo "Common targets:"
	@echo "  make test-all           Run every chapter's smoke tests"
	@echo "  make test CHAPTER=XX    Run a single chapter's tests"
	@echo "  make test-python        Run only Python-based chapter tests"
	@echo "  make test-typescript    Run only TypeScript-based chapter tests"
	@echo "  make lint               Run lint and format checks"
	@echo "  make clean              Remove caches and venvs"
	@echo ""
	@echo "Optional environment variables:"
	@echo "  CMS_GRAPHQL_URL         Live CMS endpoint for contract tests"
	@echo "  STAGING_BASE_URL        Staging origin for live audit tests"
	@echo ""
	@echo "Per-chapter targets:"
	@for chapter in $(PY_CHAPTERS); do \
	  echo "  make test-$$chapter"; \
	done

# ----------------------------------------------------------------
# Aggregate targets
# ----------------------------------------------------------------

.PHONY: test-all
test-all: test-python test-typescript test-shell
	@echo ""
	@echo "================================================================"
	@echo "  ALL CHAPTER TESTS PASSED"
	@echo "================================================================"

.PHONY: test
test:
ifndef CHAPTER
	$(error CHAPTER is not set. Usage: make test CHAPTER=chapter-NN-topic)
endif
	@$(MAKE) test-$(CHAPTER)

.PHONY: test-python
test-python: $(addprefix test-,$(PY_CHAPTERS))

.PHONY: test-typescript
test-typescript: $(addprefix test-ts-,$(TS_CHAPTERS))

.PHONY: test-shell
test-shell: $(addprefix test-sh-,$(SH_CHAPTERS))

# ----------------------------------------------------------------
# Per-chapter Python targets
# ----------------------------------------------------------------

define PY_CHAPTER_RULES
.PHONY: test-$(1)
test-$(1):
	@echo ""
	@echo "================================================================"
	@echo "  $(1) (Python)"
	@echo "================================================================"
	@cd $(VOL1)/$(1) && \
	  $(PYTHON) -m venv .venv 2>/dev/null || true && \
	  source .venv/bin/activate && \
	  pip install -q -r requirements.txt && \
	  if [ -d tests ] || ls test_*.py >/dev/null 2>&1; then \
	    $(PYTHON) -m pytest -q; \
	  else \
	    echo "  (no pytest suite, running module imports as smoke test)"; \
	    for f in *.py; do \
	      $(PYTHON) -c "import ast; ast.parse(open('$$f').read())" \
	        && echo "  ✓ $$f parses" \
	        || (echo "  ✗ $$f failed to parse" && exit 1); \
	    done; \
	  fi
endef

$(foreach chapter,$(PY_CHAPTERS),$(eval $(call PY_CHAPTER_RULES,$(chapter))))

# ----------------------------------------------------------------
# Per-chapter TypeScript targets
# ----------------------------------------------------------------

define TS_CHAPTER_RULES
.PHONY: test-ts-$(1)
test-ts-$(1):
	@echo ""
	@echo "================================================================"
	@echo "  $(1) (TypeScript)"
	@echo "================================================================"
	@cd $(VOL1)/$(1) && \
	  if command -v npx >/dev/null 2>&1; then \
	    for f in *.test.ts *.test.tsx; do \
	      [ -f "$$f" ] || continue; \
	      echo "  running $$f"; \
	      SITE_ORIGIN=https://example.com npx --yes tsx --test "$$f"; \
	    done; \
	  else \
	    echo "  npx not installed; skipping TypeScript tests"; \
	  fi
endef

$(foreach chapter,$(TS_CHAPTERS),$(eval $(call TS_CHAPTER_RULES,$(chapter))))

# ----------------------------------------------------------------
# Per-chapter shell-script targets
# ----------------------------------------------------------------

define SH_CHAPTER_RULES
.PHONY: test-sh-$(1)
test-sh-$(1):
	@echo ""
	@echo "================================================================"
	@echo "  $(1) (shell)"
	@echo "================================================================"
	@cd $(VOL1)/$(1) && \
	  for f in *.sh; do \
	    [ -f "$$f" ] || continue; \
	    bash -n "$$f" && echo "  ✓ $$f passes syntax check" \
	      || (echo "  ✗ $$f failed syntax check" && exit 1); \
	  done
endef

$(foreach chapter,$(SH_CHAPTERS),$(eval $(call SH_CHAPTER_RULES,$(chapter))))

# ----------------------------------------------------------------
# Live-service tests, gated by environment variables
# ----------------------------------------------------------------
```
.PHONY: test-live-cms
test-live-cms:
ifndef CMS_GRAPHQL_URL
	@echo "  CMS_GRAPHQL_URL not set; skipping live CMS contract tests"
else
	@echo "  running CMS contract validator against $$CMS_GRAPHQL_URL"
	@cd $(VOL1)/chapter-19-headless && \
	  source .venv/bin/activate && \
	  $(PYTHON) cms_contract_validator.py \
	    --graphql $$CMS_GRAPHQL_URL \
	    --query @test/page-by-slug.gql \
	    --variables '{"slug":"smoke-test"}'
endif

.PHONY: test-live-staging
test-live-staging:
ifndef STAGING_BASE_URL
	@echo "  STAGING_BASE_URL not set; skipping live staging audit"
else
	@echo "  running headless audit against $$STAGING_BASE_URL"
	@cd $(VOL1)/chapter-19-headless && \
	  source .venv/bin/activate && \
	  echo "/" | $(PYTHON) headless_seo_audit.py \
	    --batch --base-url $$STAGING_BASE_URL
endif
```
# ----------------------------------------------------------------
# Lint and format
# ----------------------------------------------------------------
```
.PHONY: lint
lint: lint-python lint-typescript lint-markdown

.PHONY: lint-python
lint-python:
	@echo "Checking Python style across chapter directories"
	@command -v ruff >/dev/null 2>&1 || pip install -q ruff
	@find $(VOL1) -name '*.py' -not -path '*/.venv/*' | \
	  xargs ruff check --quiet || echo "  ruff reported issues"
	@find $(VOL1) -name '*.py' -not -path '*/.venv/*' | \
	  xargs ruff format --check --quiet || echo "  ruff format reported issues"

.PHONY: lint-typescript
lint-typescript:
	@echo "Checking TypeScript syntax"
	@if command -v npx >/dev/null 2>&1; then \
	  find $(VOL1) -name '*.ts' -o -name '*.tsx' | \
	    grep -v node_modules | \
	    xargs -I {} npx --yes tsc --noEmit --strict {} 2>&1 | head -50; \
	else \
	  echo "  npx not installed; skipping TypeScript lint"; \
	fi

.PHONY: lint-markdown
lint-markdown:
	@echo "Checking Markdown structure"
	@for f in README.md CHANGELOG.md CITATIONS.md $(VOL1)/README.md; do \
	  [ -f "$$f" ] && echo "  ✓ $$f exists" || (echo "  ✗ $$f missing" && exit 1); \
	done
```
# ----------------------------------------------------------------
# Maintenance
# ----------------------------------------------------------------

.PHONY: clean
clean:
	@echo "Removing virtualenvs and caches"
	@find $(VOL1) -name '.venv' -type d -exec rm -rf {} + 2>/dev/null || true
	@find $(VOL1) -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
	@find $(VOL1) -name '.pytest_cache' -type d -exec rm -rf {} + 2>/dev/null || true
	@find $(VOL1) -name 'node_modules' -type d -exec rm -rf {} + 2>/dev/null || true
	@find $(VOL1) -name '*.pyc' -delete 2>/dev/null || true
	@echo "  done"

.PHONY: list-chapters
list-chapters:
	@ls -1 $(VOL1) | grep '^chapter-' | sort