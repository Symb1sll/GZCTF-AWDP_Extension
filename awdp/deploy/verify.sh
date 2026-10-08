#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "$0")"
DC=(docker compose --env-file /srv/awdp-dev/compose.env -f compose.yaml)
"${DC[@]}" ps
WEB_ID=$("${DC[@]}" ps -q web)
DB_ID=$("${DC[@]}" ps -q db)
test -n "$WEB_ID" && test -n "$DB_ID"
test "$(docker port "$WEB_ID" 8080/tcp)" = '127.0.0.1:18091'
test -z "$(docker port "$DB_ID")"
READY=false
for attempt in {1..30}; do
    if curl -fsS -o /dev/null --connect-timeout 3 --max-time 5 http://127.0.0.1:18091/; then
        READY=true
        break
    fi
    sleep 2
done
if [ "$READY" != true ]; then
    echo 'Web did not become reachable; inspect Compose logs before proceeding.' >&2
    exit 1
fi
python3 ./prepare_attack_network.py --check
systemctl is-active awdp-dev-runner.service
"${DC[@]}" exec -T db psql -U awdp_dev -d gzctf_awdp_dev -v ON_ERROR_STOP=1 -c 'SELECT "MigrationId" FROM "__EFMigrationsHistory" ORDER BY "MigrationId" DESC LIMIT 1;'
"${DC[@]}" exec -T db psql -U awdp_dev -d gzctf_awdp_dev -v ON_ERROR_STOP=1 -c 'SELECT "GameId", "ChallengeId", "ParticipationId", "Status", COUNT(*) FROM "AwdpSubmissions" GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;'
"${DC[@]}" exec -T db psql -U awdp_dev -d gzctf_awdp_dev -v ON_ERROR_STOP=1 -c 'SELECT "GameId", "ChallengeId", "ParticipationId", MAX("FixScore") AS "FixAward" FROM "AwdpSubmissions" WHERE "Status" = '\''passed'\'' GROUP BY 1,2,3 ORDER BY 1,2,3;'
docker ps -a --filter label=gzctf.awdp.dev.managed=true --format 'table {{.Names}}\t{{.Status}}'
docker ps --filter name=gzctf-gzctf-1 --filter name=gzctf-db-1 --format 'table {{.Names}}\t{{.Status}}'
echo 'Infrastructure checks complete; browser acceptance is still required.'
