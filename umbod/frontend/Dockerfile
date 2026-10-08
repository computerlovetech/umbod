FROM oven/bun:1 AS builder

WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
RUN bun run build

FROM nginx:1.28-alpine

RUN apk add --no-cache jq && rm -rf /usr/share/nginx/html/* && mkdir -p /tmp/umbod && chown nginx:nginx /tmp/umbod
COPY --from=builder /app/build /usr/share/nginx/html
COPY deployment/nginx.conf /etc/nginx/nginx.conf
COPY deployment/default.conf.template /etc/nginx/templates/default.conf.template
COPY deployment/start.sh /usr/local/bin/umbod-frontend
COPY deployment/generate-config.sh /usr/local/bin/generate-config.sh

USER nginx
EXPOSE 3000
ENTRYPOINT ["/bin/sh", "/usr/local/bin/umbod-frontend"]
