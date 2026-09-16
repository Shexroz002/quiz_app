# syntax=docker/dockerfile:1
#
# The Telegram Mini App as its own image: built once, then served as static
# files. Build from the repository root, not from app/bot/webapp.

# ---------------------------------------------------------------------------
# Build the bundle
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /build

# Both values are baked into the bundle and cannot be changed afterwards.
# VITE_API_BASE_URL is required in production: the Mini App is served from its
# own domain, so a relative "/api/v1/..." would hit the webapp host instead of
# the backend.
ARG VITE_API_BASE_URL
ARG VITE_BASE_PATH=/
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_BASE_PATH=${VITE_BASE_PATH}

COPY app/bot/webapp/package.json app/bot/webapp/package-lock.json ./
RUN npm ci

COPY app/bot/webapp/ ./
RUN test -n "$VITE_API_BASE_URL" \
    || (echo "VITE_API_BASE_URL bo'sh: Mini App backendni topa olmaydi" >&2; exit 1)
RUN npm run build


# ---------------------------------------------------------------------------
# Serve it
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

COPY docker/prod/webapp.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
