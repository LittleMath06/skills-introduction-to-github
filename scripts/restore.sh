#!/usr/bin/env sh
# Restaura um backup: scripts/restore.sh deploy/backups/prospeccao-AAAAMMDD-HHMMSS.sql.gz
# ATENÇÃO: substitui o banco atual. Teste periodicamente em um ambiente separado.
set -eu
[ $# -eq 1 ] || { echo "uso: $0 arquivo.sql.gz"; exit 1; }
cd "$(dirname "$0")/.."
docker compose stop app
docker compose exec -T db psql -U prospeccao -d postgres -c "DROP DATABASE IF EXISTS prospeccao;" -c "CREATE DATABASE prospeccao OWNER prospeccao;"
gunzip -c "$1" | docker compose exec -T db psql -U prospeccao -d prospeccao
docker compose start app
echo "Restaurado de $1"
