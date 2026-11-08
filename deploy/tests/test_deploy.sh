#!/usr/bin/env bash
set -euo pipefail

DEPLOY_SH="$(dirname "$0")/../deploy.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FAILED=0

mkdir -p "$WORK/release/backend" "$WORK/release/deploy"
echo marker >"$WORK/release/backend/marker.txt"
: >"$WORK/release/backend/pyproject.toml"
: >"$WORK/release/deploy/chaeum@.service"

fake() {
  printf '#!/usr/bin/env bash\necho "${0##*/} $*" >>"$FAKE/calls.log"\n%s\n' "${2:-}" >"$FAKE/$1"
  chmod +x "$FAKE/$1"
}

new_root() {
  FAKE="$(mktemp -d "$WORK/root.XXXXXX")"
  mkdir -p "$FAKE"/{bin,releases,shared/{storage,cache,venv/bin}}
  : >"$FAKE/shared/.env"
  echo 'server 127.0.0.1:8001;' >"$FAKE/chaeum-upstream.conf"
  tar -czf "$FAKE/release.tar.gz" -C "$WORK/release" backend deploy

  fake bin/aws 'cp "$FAKE/release.tar.gz" "$4"'
  fake bin/sudo 'shift 2; exec "$@"'
  fake bin/nginx '[ "${NGINX_TEST_FAIL:-}" != 1 ]'
  fake bin/curl '[ "${CURL_FAIL:-}" != 1 ]'
  fake bin/sleep
  fake bin/systemctl
  fake bin/chown
  fake bin/journalctl
  fake shared/venv/bin/pip '[ "${PIP_FAIL:-}" != 1 ]'
}

run_deploy() {
  : >"$FAKE/calls.log"
  PATH="$FAKE/bin:$PATH" FAKE="$FAKE" \
    CHAEUM_ROOT="$FAKE" \
    CHAEUM_UPSTREAM_CONF="$FAKE/chaeum-upstream.conf" \
    CHAEUM_UNIT_DEST="$FAKE/chaeum@.service" \
    CHAEUM_DEPLOY_LOG=/dev/null \
    bash "$DEPLOY_SH" "$1" test-bucket 2>&1 | sed 's/^/    │ /' >>"$FAKE/deploy.log"
}

current_release() { readlink -f "$FAKE/current" || true; }
upstream_port() { grep -oE '127\.0\.0\.1:[0-9]+' "$FAKE/chaeum-upstream.conf" | cut -d: -f2 || true; }
release_shas() { ls "$FAKE/releases" | cut -d- -f1 | paste -sd ' ' -; }
save_upstream() { cp "$FAKE/chaeum-upstream.conf" "$FAKE/upstream.before"; }
upstream_unchanged() { cmp -s "$FAKE/upstream.before" "$FAKE/chaeum-upstream.conf"; }
called() { grep -qxF "$1" "$FAKE/calls.log"; }
not_called() { ! called "$1"; }

fail() {
  echo "FAIL $SCENARIO: $1"
  echo "$1" >>"$FAKE/failures"
}

scenario() {
  SCENARIO="$1"
  new_root
  set +e
  (set -e; "$2")
  local status=$?
  set -e
  [ "$status" -eq 0 ] || fail "시나리오가 도중에 멈춤(종료 코드 $status)"
  if [ -s "$FAKE/failures" ]; then
    FAILED=1
    [ ! -f "$FAKE/deploy.log" ] || cat "$FAKE/deploy.log"
  else
    echo "PASS $SCENARIO"
  fi
}

same_commit_twice() {
  local ports first second
  ports="$(upstream_port)"
  run_deploy abc1234 || fail "첫 배포가 실패함"
  ports="$ports→$(upstream_port)"
  first="$(current_release)"
  sleep 1
  run_deploy abc1234 || fail "두 번째 배포가 실패함"
  ports="$ports→$(upstream_port)"
  second="$(current_release)"

  [ -f "$first/backend/marker.txt" ] || fail "첫 배포 폴더가 지워짐"
  [ "$second" != "$first" ] || fail "두 번째 배포가 같은 폴더를 씀"
  [[ "${second##*/}" == abc1234-* ]] || fail "폴더 이름이 abc1234- 로 시작하지 않음: ${second##*/}"
  [ "$ports" = "8001→8002→8001" ] || fail "포트가 $ports 로 바뀜"
  [ ! -e "$FAKE/chaeum-upstream.conf.bak" ] || fail ".bak 파일이 남음"
}

four_deploys() {
  local sha current
  for sha in ccc3333 aaa1111 ddd4444 bbb2222; do
    run_deploy "$sha" || fail "$sha 배포가 실패함"
  done
  current="$(current_release)"

  [ "$(release_shas)" = "aaa1111 bbb2222 ddd4444" ] || fail "가장 먼저 배포한 ccc3333만 지워져야 하는데 남은 것: $(release_shas)"
  [[ "${current##*/}" == bbb2222-* ]] || fail "current가 마지막 배포(bbb2222)를 가리키지 않음: ${current##*/}"
}

nginx_check_fails() {
  local before status=0
  run_deploy abc1234 || fail "첫 배포가 실패함"
  save_upstream
  before="$(current_release)"
  NGINX_TEST_FAIL=1 run_deploy def5678 || status=$?

  [ "$status" -ne 0 ] || fail "배포가 성공으로 끝남"
  upstream_unchanged || fail "upstream 설정이 원래대로 돌아오지 않음"
  [ "$(current_release)" = "$before" ] || fail "current가 실패 전 폴더로 돌아오지 않음"
  called "systemctl stop chaeum@8001" || fail "새 포트(8001)를 멈추지 않음"
  not_called "systemctl reload nginx" || fail "nginx를 reload함"
  not_called "systemctl stop chaeum@8002" || fail "구 버전 포트(8002)를 멈춤"
  [ ! -e "$FAKE/chaeum-upstream.conf.bak" ] || fail ".bak 파일이 남음"
}

first_deploy_nginx_check_fails() {
  local status=0
  save_upstream
  NGINX_TEST_FAIL=1 run_deploy abc1234 || status=$?

  [ "$status" -ne 0 ] || fail "배포가 성공으로 끝남"
  upstream_unchanged || fail "upstream 설정이 원래대로 돌아오지 않음"
  [ ! -L "$FAKE/current" ] || fail "current 링크가 남음 → $(readlink "$FAKE/current")"
  called "systemctl stop chaeum@8002" || fail "새 포트(8002)를 멈추지 않음"
  not_called "systemctl reload nginx" || fail "nginx를 reload함"
  not_called "systemctl stop chaeum@8001" || fail "구 버전 포트(8001)를 멈춤"
  [ ! -e "$FAKE/chaeum-upstream.conf.bak" ] || fail ".bak 파일이 남음"
}

health_check_fails() {
  local before status=0
  run_deploy abc1234 || fail "첫 배포가 실패함"
  save_upstream
  before="$(current_release)"
  CURL_FAIL=1 run_deploy def5678 || status=$?

  [ "$status" -ne 0 ] || fail "배포가 성공으로 끝남"
  upstream_unchanged || fail "upstream 설정이 바뀜"
  [ "$(current_release)" = "$before" ] || fail "current가 실패 전 폴더로 돌아오지 않음"
  called "systemctl stop chaeum@8001" || fail "새 포트(8001)를 멈추지 않음"
  not_called "systemctl reload nginx" || fail "nginx를 reload함"
  not_called "systemctl stop chaeum@8002" || fail "구 버전 포트(8002)를 멈춤"
}

failed_deploys_keep_last_good() {
  local good
  run_deploy aaa1111 || fail "첫 배포가 실패함"
  good="$(current_release)"
  if CURL_FAIL=1 run_deploy bbb2222; then fail "헬스체크가 실패한 bbb2222가 성공으로 끝남"; fi
  if NGINX_TEST_FAIL=1 run_deploy ccc3333; then fail "nginx 검사가 실패한 ccc3333이 성공으로 끝남"; fi
  if PIP_FAIL=1 run_deploy ddd4444; then fail "의존성 설치가 실패한 ddd4444가 성공으로 끝남"; fi
  run_deploy eee5555 || fail "마지막 배포가 실패함"

  [ -d "$good" ] || fail "마지막 정상 릴리스(aaa1111)가 지워짐"
  [ "$(release_shas)" = "aaa1111 eee5555" ] || fail "실패한 배포의 폴더가 남음: $(release_shas)"
}

scenario "같은 커밋 두 번" same_commit_twice
scenario "네 번 배포" four_deploys
scenario "nginx 검사 실패" nginx_check_fails
scenario "첫 배포에서 nginx 검사 실패" first_deploy_nginx_check_fails
scenario "헬스체크 실패" health_check_fails
scenario "실패한 배포 뒤에도 정상 릴리스 유지" failed_deploys_keep_last_good

[ "$FAILED" -eq 0 ] || exit 1
