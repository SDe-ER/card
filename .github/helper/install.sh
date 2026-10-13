#!/bin/bash
# CI bootstrap: a bench with frappe + erpnext (version-16) and CARD installed on test_site.
set -e

cd ~ || exit 1

sudo apt-get update
sudo apt-get remove -y mysql-server mysql-client || true
sudo apt-get install -y libcups2-dev redis-server mariadb-client libmariadb-dev

pip install frappe-bench

frappebranch=${FRAPPE_BRANCH:-version-16}
erpnextbranch=${ERPNEXT_BRANCH:-version-16}

git clone "https://github.com/frappe/frappe" --branch "${frappebranch}" --depth 1
bench init --skip-assets --frappe-path ~/frappe --python "$(which python)" frappe-bench

mkdir -p ~/frappe-bench/sites/test_site
cp "${GITHUB_WORKSPACE}/.github/helper/site_config.json" ~/frappe-bench/sites/test_site/

mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "SET GLOBAL character_set_server = 'utf8mb4'"
mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "SET GLOBAL collation_server = 'utf8mb4_unicode_ci'"
mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "CREATE USER 'test_frappe'@'localhost' IDENTIFIED BY 'test_frappe'"
mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "CREATE DATABASE test_frappe"
mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "GRANT ALL PRIVILEGES ON \`test_frappe\`.* TO 'test_frappe'@'localhost'"
mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "FLUSH PRIVILEGES"

cd ~/frappe-bench || exit 1

# CI needs only the web/worker; quiet the rest.
sed -i 's/^watch:/# watch:/g' Procfile
sed -i 's/^schedule:/# schedule:/g' Procfile
sed -i 's/^socketio:/# socketio:/g' Procfile
sed -i 's/^redis_socketio:/# redis_socketio:/g' Procfile

bench get-app erpnext "https://github.com/frappe/erpnext" --branch "${erpnextbranch}" --resolve-deps
bench get-app card "${GITHUB_WORKSPACE}"
bench setup requirements --dev

bench start &>> ~/frappe-bench/bench_start.log &
CI=Yes bench build --app frappe &
bench --site test_site reinstall --yes

bench --verbose --site test_site install-app erpnext
bench --verbose --site test_site install-app card
