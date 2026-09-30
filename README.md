# AI Infrastructure Sizing Engine — V1 Docker Release

This is the Docker Compose release of the AI Infrastructure Sizing Engine. It implements the intended V1 flow:

**Requirement → Workload → Model → Capacity → Infrastructure → HA/DR/Growth → BOM → CAPEX/OPEX → TCO → Cloud Alternative → Evidence → PDF/XLSX report**

## Run

From this directory:

```bash
docker-compose up -d --build
```

Then open:

- http://localhost:3000 — application
- http://localhost:8000/docs — API documentation
- http://localhost:8000/health — backend/database health

For a remote Linux host, use `http://<host-ip>:3000` from your browser.

## Verify after startup

Run:

```bash
python verify_e2e.py
```

The verifier checks frontend/backend reachability, database health, all catalogs, login, project creation, deterministic sizing, persistence, governance status, and JSON/PDF/XLSX report generation.

## What is persisted

Projects and sizing results are stored in PostgreSQL in the Compose deployment. Restarting the backend does not erase them.

## Data governance

- Catalog/model/GPU/server/cloud records contain evidence/source URLs.
- Server/cloud commercial values are explicitly marked `Estimated Price` where they are planning estimates.
- The engine does **not** invent a universal benchmark. Without an exact validated model/GPU/runtime benchmark, performance sizing is labeled `Insufficient Evidence`.
- Engineering assumptions such as KV-cache allowance, runtime allowance, safety margin, utilization target and on-prem OPEX rate are explicitly cataloged.
- Server/GPU mismatches, hosted-only models without a cloud selection, and context-window violations are rejected.

## Local credentials

The Compose file contains development credentials intended only for local testing. Change them before any non-local deployment.

## Important verification note

This release was code/API tested in the build environment. The build environment used for packaging does **not** contain a Docker daemon and cannot access the npm registry, so the final Docker image build and browser automation cannot be executed there. The included `verify_e2e.py` is the final black-box gate to run on the machine where Docker is available.
