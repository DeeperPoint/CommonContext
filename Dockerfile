# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
#
# Dockerfile — Knowledge Slot Curation Tool
#
# Packages the FastAPI curation server for deployment.
# Data directories (inputs/, outputs/, provenance/, etc.) are
# bind-mounted at runtime — see docker-compose.yml.

FROM python:3.12-slim

WORKDIR /app

# System dependencies required by PyMuPDF and marker-pdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY server.py convert_pdf.py convert_url.py convert_tabular.py \
    provenance.py metadata_extractor.py schema_analyzer.py ./

# Static GUI and prompt templates
COPY static/ static/
COPY prompts/ prompts/

# Ensure data directories exist (bind mounts overlay these at runtime)
RUN mkdir -p inputs outputs provenance schemas analyses

EXPOSE 8400

CMD ["python", "server.py"]
