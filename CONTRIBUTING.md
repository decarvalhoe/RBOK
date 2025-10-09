# Contributing to RBOK

Thank you for your interest in contributing to RBOK! This document summarises the expectations for
proposing changes and describes how the automated continuous integration (CI) pipeline is configured.

## Workflow overview

All contributions should be submitted through pull requests (PRs). Please:

1. Create a feature branch from `main`.
2. Commit focused changes with clear messages.
3. Open a PR and ensure it references any relevant issues.
4. Wait for the automated CI checks to complete successfully before requesting review or merging.

> **Merge gating** – The `CI` workflow is required for every PR. Protect the `main` branch so that
> merges are only allowed after the workflow reports success.

## Continuous integration pipeline

The GitHub Actions workflow at [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every
push and pull request targeting `main`. It performs the following checks:

### Python services (`backend` and `ai_gateway`)

- Matrices cover Python 3.10 and 3.11 so that we catch incompatibilities early.
- Dependencies are installed using cached `pip` downloads for faster runs.
- Test suites execute with pytest, produce coverage reports (`coverage.xml`) and JUnit XML results
  in the `reports/` directory. These artefacts are uploaded for inspection.

### Web application (`webapp`)

- Runs on Node.js 18 and 20.
- Uses `npm ci` with caching to install dependencies reproducibly.
- Executes `npm run lint` followed by Jest tests with coverage. Coverage output and machine readable
  test results (`reports/jest-results.json`) are published as workflow artefacts.

### Mobile application (`mobile`)

- Currently validated on Node.js 18.
- Installs dependencies with `npm ci` and runs Jest tests with coverage, exporting the same artefact
  structure as the web application.

### Container images

- After all test jobs succeed, Docker images are built for the backend, AI gateway and web
  application from their respective `Dockerfile`s. This ensures our images remain buildable.
- On pushes to `main`, the optional `docker-publish` stage logs into GitHub Container Registry (GHCR)
  and pushes refreshed images tagged as `latest`. Set repository secrets or tighten permissions if
  you need to publish elsewhere.

## Local verification

To minimise CI failures, run the same commands locally before opening a PR:

```bash
# Backend
cd backend
pip install -r requirements.txt
pytest --cov=app

# AI Gateway
cd ai_gateway
pip install -r requirements.txt
pytest --cov=ai_gateway

# Web application
cd webapp
npm ci
npm run lint
npm test -- --coverage

# Mobile application
cd mobile
npm ci
npm test -- --coverage
```

## Reporting issues

If you encounter flaky tests or CI failures you cannot reproduce, please open an issue with as much
context as possible (commit SHA, workflow run link, logs). This helps maintainers investigate and
improve the pipeline.

We appreciate your contributions and reviews—thank you for helping us build RBOK!
