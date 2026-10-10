#!/usr/bin/env bash
# Spusti testy modulu elite_vet_reservation v Dockeru na cerstve databazi.
# Pouziti: bash testy-rezervace.sh                 (vsechny testy modulu)
#          bash testy-rezervace.sh TestRoom        (jen jedna testovaci trida)
# Druhe a dalsi spusteni: bash testy-rezervace.sh "" update
set -euo pipefail
cd "$(dirname "$0")/../.."
TAG="${1:-}"
TAGS="/elite_vet_reservation"
if [ -n "$TAG" ]; then TAGS="/elite_vet_reservation:${TAG}"; fi
MODE="-i"; if [ "${2:-}" = "update" ]; then MODE="-u"; fi
docker compose up -d db
# -i instaluje modul i se zavislostmi; databaze ev_test se zalozi sama.
docker compose run --rm odoo odoo -d ev_test $MODE elite_vet_reservation \
  --without-demo=all --test-enable --test-tags "$TAGS" \
  --stop-after-init --log-level=test 2>&1 | tee /tmp/ev_test.log
# Odoo vraci 0 i pri padlem testu, proto se hleda v logu.
if grep -qE "ERROR|FAIL" /tmp/ev_test.log; then
  echo "TESTY SELHALY"; exit 1
fi
echo "TESTY OK"
