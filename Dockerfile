# ── Stage 1: compile the purged Tailwind stylesheet ───────────────────────────
# Replaces the old in-browser Tailwind Play CDN runtime. Uses the standalone
# Tailwind CLI (no Node/npm) to emit app/static/css/app.css containing only the
# classes actually used in the templates. Runs on every `fly deploy`.
FROM python:3.12-slim AS cssbuild
ARG TAILWIND_VERSION=v3.4.17
WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /usr/local/bin/tailwindcss \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64" \
    && chmod +x /usr/local/bin/tailwindcss
# Only the inputs the purge needs to scan.
COPY tailwind.config.js ./
COPY app/static/css/tailwind-input.css ./app/static/css/tailwind-input.css
COPY app/templates ./app/templates
COPY app/static/js ./app/static/js
RUN tailwindcss -c tailwind.config.js \
        -i app/static/css/tailwind-input.css \
        -o app/static/css/app.css --minify

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# System dependencies for the character-import pipeline:
#   antiword - legacy Microsoft .doc extraction (import-design §6)
#   libmagic1 - file-type detection for uploaded documents
#   libcairo2 - cairosvg backend for the dice-roll "copy as image" card
RUN apt-get update \
    && apt-get install -y --no-install-recommends antiword libmagic1 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The combat simulator's character generator (l7r-combat-simulator), which
# builds the GM's NPCs from its current XP progression
# (combat-design/design.md 4.1). Like everything else in this image it comes
# from the LOCAL build context: scripts/deploy.sh exports the simulator
# checkout's committed HEAD into build-simulator/ just before `fly deploy`,
# and passes that commit in so every generated NPC records it. Deploy with
# the script, not a bare `fly deploy` - without build-simulator/ this COPY
# fails, which is the point: an image without the simulator cannot build NPCs.
COPY build-simulator /tmp/simulator
RUN pip install --no-cache-dir /tmp/simulator && rm -rf /tmp/simulator
ARG SIMULATOR_COMMIT=""
ENV SIMULATOR_COMMIT=${SIMULATOR_COMMIT}

COPY . .

# Overwrite the committed app.css with the freshly-purged build that matches the
# templates in this image (the committed copy is only for local dev convenience).
COPY --from=cssbuild /build/app/static/css/app.css ./app/static/css/app.css

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
