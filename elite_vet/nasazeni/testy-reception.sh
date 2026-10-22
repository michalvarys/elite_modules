#!/usr/bin/env bash
# Spusti testy modulu elite_vet_reception v Dockeru na cerstve databazi.
# Pouziti: bash testy-reception.sh                 (vsechny testy modulu)
#          bash testy-reception.sh TestSetup       (jen jedna testovaci trida, napr. TestSetup)
# Druhe a dalsi spusteni: bash testy-reception.sh "" update
set -euo pipefail
cd "$(dirname "$0")/../.."
TAG="${1:-}"
TAGS="/elite_vet_reception"
if [ -n "$TAG" ]; then TAGS="/elite_vet_reception:${TAG}"; fi
MODE="-i"; if [ "${2:-}" = "update" ]; then MODE="-u"; fi
docker compose up -d db
# -i instaluje modul i se zavislostmi; databaze ev_test se zalozi sama.
docker compose run --rm odoo odoo -d ev_test $MODE elite_vet_reception \
  --without-demo=all --test-enable --test-tags "$TAGS" \
  --stop-after-init --log-level=test 2>&1 | tee /tmp/ev_test_reception.log
# Odoo vraci 0 i pri padlem testu, proto se hleda v logu. Soudi se podle urovne
# logu (format "CAS PID UROVEN db logger: zprava"), ne podle podretezce, a chybejici
# modul ("invalid module names") nesmi projit jako zeleny beh bez testu.
if grep -qE " (ERROR|CRITICAL) |invalid module names" /tmp/ev_test_reception.log; then
  echo "TESTY SELHALY"; exit 1
fi
echo "TESTY OK"
