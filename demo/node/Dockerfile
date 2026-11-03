# Harbor demo — React app + Node backend (@foid/node SDK) in one image.
# Build context is demo/:  docker compose up node --build
FROM node:22-alpine AS web
WORKDIR /web
COPY package.json package-lock.json ./
COPY vendor ./vendor
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM node:22-alpine
ENV NODE_ENV=production DEMO_DIST_DIR=/app/dist DEMO_KEYS_DIR=/app/keys HOST=127.0.0.1 PORT=3200
WORKDIR /app/node
# The SDK comes in as a packed tarball (vendor/), the way it would from npm.
COPY node/package.json node/package-lock.json ./
COPY node/vendor ./vendor
RUN npm ci --omit=dev --no-audit --no-fund
COPY node/server.mjs ./
COPY --from=web /web/dist /app/dist
EXPOSE 3200
CMD ["node", "server.mjs"]
