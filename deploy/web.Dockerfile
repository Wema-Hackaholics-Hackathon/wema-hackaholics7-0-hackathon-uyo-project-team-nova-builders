# One recipe for the three web apps — built as static files, served by nginx, /api proxied to the backend.
#   APP=frontend    FOID user app      (also hosts the sign-in popup and hosted verification)
#   APP=enterprise  business console
#   APP=docs        docs site (VitePress)
# Build context: the repo root (docs installs @foid/react from ../sdks/react).

FROM node:22-alpine AS build
RUN npm install -g pnpm@12.15.0
ARG APP
WORKDIR /src
COPY sdks/react /src/sdks/react
COPY ${APP}/package.json ${APP}/pnpm-lock.yaml ${APP}/pnpm-workspace.yaml* /src/${APP}/
WORKDIR /src/${APP}
RUN pnpm install --frozen-lockfile
COPY ${APP}/ /src/${APP}/
# Empty VITE_API_URL = the app calls /api on its own origin, which nginx forwards to the backend.
ENV VITE_API_URL=""
ARG VITE_MONO_PUBLIC_KEY=""
ARG VITE_DOCS_URL="http://localhost:5177"
ARG DOCS_SITE_URL="http://localhost:5177"
ENV VITE_MONO_PUBLIC_KEY=${VITE_MONO_PUBLIC_KEY} VITE_DOCS_URL=${VITE_DOCS_URL} DOCS_SITE_URL=${DOCS_SITE_URL}
RUN if [ "$APP" = "docs" ]; then pnpm exec vitepress build && mv .vitepress/dist /out; \
    else pnpm exec vite build && mv dist /out; fi

FROM nginx:1.27-alpine
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /out /usr/share/nginx/html
ENV BACKEND_URL=http://backend:8000
EXPOSE 80
