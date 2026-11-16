# Production web image: the built Vue app inside Caddy. Build context: frontend/. The Caddyfile is mounted by
# docker-compose.yml, so a header change needs no rebuild.
FROM node:24.22.2-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx vite build

FROM caddy:2.11.7-alpine
COPY --from=build /app/dist /srv
