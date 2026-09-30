#!/usr/bin/env sh
# Backup diário do PostgreSQL (docker compose). Agende no cron do servidor:
#   15 3 * * * /caminho/do/projeto/scripts/backup.sh >> /var/log/prospeccao-backup.log 2>&1
# Mantém os últimos 14 backups em deploy/backups/. Copie-os também para fora do servidor.
set -eu
cd "$(dirname "$0")/.."
mkdir -p deploy/backups
FILE="deploy/backups/prospeccao-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U prospeccao --no-owner prospeccao | gzip > "$FILE"
test -s "$FILE"
ls -1t deploy/backups/prospeccao-*.sql.gz | tail -n +15 | xargs -r rm --
echo "Backup gerado: $FILE"
