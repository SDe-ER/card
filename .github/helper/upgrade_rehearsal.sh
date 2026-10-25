#!/bin/bash
# Upgrade rehearsal (go-live P0 #119): CARD FROM_REF on the pinned frappe/erpnext, synthetic data,
# then the code under test, migrate twice, compare. Evidence in ~/rehearsal/.
set -euo pipefail

FRAPPE_REF=${FRAPPE_REF:-v16.51.1}
ERPNEXT_REF=${ERPNEXT_REF:-v16.50.0}
FROM_REF=${FROM_REF:-v1.0.1}
OUT=~/rehearsal
HELPER="${GITHUB_WORKSPACE}/.github/helper"
mkdir -p "$OUT"

cd ~
sudo apt-get update
sudo apt-get remove -y mysql-server mysql-client || true
sudo apt-get install -y libcups2-dev redis-server mariadb-client libmariadb-dev
pip install frappe-bench

git clone "https://github.com/frappe/frappe" --branch "${FRAPPE_REF}" --depth 1
bench init --skip-assets --frappe-path ~/frappe --python "$(which python)" frappe-bench

mkdir -p ~/frappe-bench/sites/test_site
cp "${HELPER}/site_config.json" ~/frappe-bench/sites/test_site/
for sql in "SET GLOBAL character_set_server = 'utf8mb4'" \
	"SET GLOBAL collation_server = 'utf8mb4_unicode_ci'" \
	"CREATE USER 'test_frappe'@'localhost' IDENTIFIED BY 'test_frappe'" \
	"CREATE DATABASE test_frappe" \
	"GRANT ALL PRIVILEGES ON \`test_frappe\`.* TO 'test_frappe'@'localhost'" \
	"FLUSH PRIVILEGES"; do
	mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "$sql"
done

cd ~/frappe-bench
sed -i 's/^watch:/# watch:/g; s/^schedule:/# schedule:/g; s/^socketio:/# socketio:/g; s/^redis_socketio:/# redis_socketio:/g' Procfile

bench get-app erpnext "https://github.com/frappe/erpnext" --branch "${ERPNEXT_REF}"
bench get-app card "${GITHUB_WORKSPACE}"
git -C apps/card fetch --tags "${GITHUB_WORKSPACE}" HEAD
CANDIDATE=$(git -C apps/card rev-parse FETCH_HEAD)
git -C apps/card checkout --quiet "${FROM_REF}"
./env/bin/pip install --quiet -e apps/card
bench setup requirements --dev

bench start &>> ~/frappe-bench/bench_start.log &
bench --site test_site reinstall --yes
bench --site test_site install-app erpnext
bench --site test_site install-app card
{
	echo "frappe ${FRAPPE_REF} / erpnext ${ERPNEXT_REF}"
	echo "from: card ${FROM_REF} $(git -C apps/card rev-parse HEAD)"
	echo "to:   card ${CANDIDATE}"
	bench version
} | tee "$OUT/versions.txt"

cd sites
../env/bin/python "${HELPER}/upgrade_rehearsal.py" test_site seed | tee "$OUT/seed.json"
../env/bin/python "${HELPER}/upgrade_rehearsal.py" test_site snapshot "$OUT/0-before.json"

cd ..
git -C apps/card checkout --quiet "${CANDIDATE}"
./env/bin/pip install --quiet -e apps/card
bench --site test_site migrate 2>&1 | tee "$OUT/migrate-1.log"
(cd sites && ../env/bin/python "${HELPER}/upgrade_rehearsal.py" test_site snapshot "$OUT/1-after-migrate.json")
bench --site test_site migrate 2>&1 | tee "$OUT/migrate-2.log"
cd sites
../env/bin/python "${HELPER}/upgrade_rehearsal.py" test_site snapshot "$OUT/2-after-second-migrate.json"

../env/bin/python "${HELPER}/upgrade_rehearsal.py" test_site compare "$OUT/0-before.json" "$OUT/1-after-migrate.json" upgrade | tee "$OUT/compare-upgrade.txt"
../env/bin/python "${HELPER}/upgrade_rehearsal.py" test_site compare "$OUT/1-after-migrate.json" "$OUT/2-after-second-migrate.json" idempotent | tee "$OUT/compare-idempotent.txt"
../env/bin/python "${HELPER}/upgrade_rehearsal.py" test_site smoke | tee "$OUT/smoke.txt"
