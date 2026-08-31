# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- build stage
FROM node:22-alpine AS builder

WORKDIR /app

# Lockfile first so dependency install caches independently of source changes.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# Where the browser should send API calls. Vite inlines this into the bundle at
# build time, so it is a build argument rather than a runtime variable - and the
# resulting image is specific to one API origin. Point it at the public URL of
# the api deployment, scheme included and no trailing slash.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY . .
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM nginx:alpine AS runtime

RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
