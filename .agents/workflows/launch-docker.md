<!--Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.-->
---
description: Clean up, build, and start the CommonContext curation tool using Docker, then display local access URLs
---

## /launch-docker — Launch the CommonContext Curation Tool with Docker

Use this workflow to clean up any existing containers, build the curation server Docker image, start the container in detached mode, and verify that the GUI is accessible.

### How to invoke

In chat, type:

> `/launch-docker`

---

### What the agent will do

#### Step 1 — Verify prerequisites and environment
1. Ensure `docker compose` is available on the host machine by running `docker compose version`.
2. Discover and locate the `OPENROUTER_API_KEY`:
   - Check the local `.env` file first.
   - If not present locally, check sibling repository `.env` files (e.g. `c:\Users\MustafaUzumeri\Documents\GitHub\DPContentPublishing\.env`).
   - If found, create or update a local `.env` file in the root of the `CommonContext` repository to ensure the API key is passed into the Docker environment.

#### Step 2 — Clean up existing containers
1. Stop and remove any active or dangling containers and networks defined in `docker-compose.yml` to prevent name clashes:
   ```bash
   docker compose down
   ```

#### Step 3 — Build and start the service
1. Run docker compose up with the build flag in detached (background) mode:
   ```bash
   docker compose up --build -d
   ```
   *Note: Docker will reuse the cached dependency layers from pip unless `requirements.txt` has changed, which keeps the build fast (typically under 5 seconds).*

#### Step 4 — Verify container status
1. Check the status of the curation container by running:
   ```bash
   docker compose ps
   ```
2. Confirm the status is `Up` and mapped to port `8400`.
3. Check container logs if it enters a restarting state to diagnose and fix any issues (e.g., missing Python scripts):
   ```bash
   docker compose logs --no-log-prefix -n 50
   ```

#### Step 5 — Present status and access link
1. Provide a clean status report to the user.
2. Output a direct clickable link to the running curation interface:
   👉 **[http://localhost:8400](http://localhost:8400)**

---

### Commit Convention

If any changes are made to `Dockerfile`, `docker-compose.yml`, or `.dockerignore` during the launch, commit them together:
```
FEAT: configure docker compose setup for curation server
```
```
FIX: resolve missing dependencies or files in Dockerfile
```
```
DOCS: add /launch-docker workspace workflow
```
