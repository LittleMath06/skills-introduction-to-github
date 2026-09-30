#!/usr/bin/env sh
# Atualização periódica (mensal, após a publicação dos dados abertos da Receita):
#   30 4 20 * * /caminho/do/projeto/scripts/cron-update.sh >> /var/log/prospeccao-update.log 2>&1
set -eu
cd "$(dirname "$0")/.."
docker compose exec -T app python -m prospeccao.cli update
