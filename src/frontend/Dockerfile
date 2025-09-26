FROM node:24-alpine AS frontend-deps

# Upgrade system packages to install security updates
RUN apk update && \
  apk upgrade && \
  rm -rf /var/cache/apk/*

WORKDIR /home/frontend/

COPY ./src/frontend/package.json ./package.json
COPY ./src/frontend/yarn.lock ./yarn.lock
COPY ./src/frontend/apps/conversations/package.json ./apps/conversations/package.json
COPY ./src/frontend/packages/eslint-config-conversations/package.json ./packages/eslint-config-conversations/package.json

RUN yarn install --frozen-lockfile

COPY .dockerignore ./.dockerignore
COPY ./src/frontend/.prettierrc.js ./.prettierrc.js
COPY ./src/frontend/packages/eslint-config-conversations ./packages/eslint-config-conversations
COPY ./src/frontend/apps/conversations ./apps/conversations

### ---- Front-end builder image ----
FROM frontend-deps AS conversations

WORKDIR /home/frontend/apps/conversations

FROM frontend-deps AS conversations-dev

WORKDIR /home/frontend/apps/conversations

EXPOSE 3000

CMD [ "yarn", "dev"]

# Tilt will rebuild conversations target so, we dissociate conversations and conversations-builder 
# to avoid rebuilding the app at every changes.
FROM conversations AS conversations-builder

WORKDIR /home/frontend/apps/conversations

ARG API_ORIGIN
ENV NEXT_PUBLIC_API_ORIGIN=${API_ORIGIN}

ARG PRODUCT_NAME
ENV NEXT_PUBLIC_PRODUCT_NAME=${PRODUCT_NAME}

RUN yarn build

# ---- Front-end image ----
FROM nginxinc/nginx-unprivileged:alpine3.22 AS frontend-production

# Upgrade system packages to install security updates
USER root
RUN apk update && \
  apk upgrade && \
  rm -rf /var/cache/apk/*
USER -

# Un-privileged user running the application
ARG DOCKER_USER
USER ${DOCKER_USER}

COPY --from=conversations-builder \
    /home/frontend/apps/conversations/out \
    /usr/share/nginx/html

COPY ./src/frontend/apps/conversations/conf/default.conf /etc/nginx/conf.d
COPY ./docker/files/usr/local/bin/entrypoint /usr/local/bin/entrypoint

ENTRYPOINT [ "/usr/local/bin/entrypoint" ]

CMD ["nginx", "-g", "daemon off;"]
