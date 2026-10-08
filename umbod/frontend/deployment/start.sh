#!/bin/sh
set -eu

/bin/sh /usr/local/bin/generate-config.sh > /tmp/umbod/app-config.json.tmp
mv /tmp/umbod/app-config.json.tmp /tmp/umbod/app-config.json
export API_PROXY_ORIGIN="${API_PROXY_ORIGIN:-}"
export DNS_RESOLVER="$(awk '/^nameserver / { print $2; exit }' /etc/resolv.conf)"
envsubst '${API_PROXY_ORIGIN} ${DNS_RESOLVER}' < /etc/nginx/templates/default.conf.template > /tmp/umbod/default.conf
exec nginx -g 'daemon off;'
