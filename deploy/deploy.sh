#!/usr/bin/env bash
#
# 채움 백엔드 무중단 배포 — EC2 안에서 실행됩니다.
#
#   사용법:  deploy.sh <커밋SHA> <S3버킷>
#
# 쉬는 포트에 새 버전을 띄우고, 정상 기동을 확인한 뒤에야 nginx 가 가리키는 쪽을 바꿉니다.
# 확인에 실패하면 전환하지 않고 중단하므로 구 버전이 계속 서비스합니다.
#
# GitHub Actions 가 SSM 으로 이 스크립트를 실행하지만, SSM 터미널에서 직접 돌려도 됩니다.

set -euo pipefail

SHA="${1:?사용법: deploy.sh <커밋SHA> <S3버킷>}"
BUCKET="${2:?사용법: deploy.sh <커밋SHA> <S3버킷>}"
REGION="${AWS_REGION:-ap-northeast-2}"

APP_USER=ubuntu
ROOT=/opt/chaeum
RELEASES="$ROOT/releases"
SHARED="$ROOT/shared"
VENV="$SHARED/venv"
UPSTREAM_CONF=/etc/nginx/conf.d/chaeum-upstream.conf
UNIT_DEST=/etc/systemd/system/chaeum@.service

HEALTH_TIMEOUT=60   # 새 버전 기동을 기다리는 최대 시간(초)
KEEP_RELEASES=3     # 롤백용으로 남겨 둘 릴리스 수
LOG=/var/log/chaeum-deploy.log

# SSM 출력은 잘리므로 전체 기록은 파일에 남깁니다.
exec > >(tee -a "$LOG") 2>&1
echo "══════════ $(date '+%F %T') 배포 시작 — $SHA ══════════"

say() { echo "▸ $*"; }
die() { echo "✗ $*" >&2; exit 1; }

# ── 1. 지금 서비스 중인 포트를 읽고, 쉬는 포트를 고른다 ────────────────
[ -f "$UPSTREAM_CONF" ] || die "upstream 설정이 없습니다: $UPSTREAM_CONF"
CURRENT_PORT="$(grep -oE '127\.0\.0\.1:[0-9]+' "$UPSTREAM_CONF" | head -1 | cut -d: -f2)"
case "$CURRENT_PORT" in
  8001) NEW_PORT=8002 ;;
  8002) NEW_PORT=8001 ;;
  *)    die "upstream 포트를 해석할 수 없습니다: '$CURRENT_PORT'" ;;
esac
say "현재 $CURRENT_PORT 서비스 중 → 새 버전은 $NEW_PORT 에 띄웁니다"

PREV_CURRENT="$(readlink -f "$ROOT/current" || true)"

# ── 2. S3 에서 릴리스를 받아 푼다 ──────────────────────────────────────
REL="$RELEASES/$SHA"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say "S3 에서 내려받는 중 — s3://$BUCKET/releases/$SHA.tar.gz"
aws s3 cp "s3://$BUCKET/releases/$SHA.tar.gz" "$TMP/release.tar.gz" --region "$REGION" --quiet \
  || die "S3 다운로드 실패 (EC2 역할에 읽기 권한이 있는지 확인하세요)"

rm -rf "$REL"
mkdir -p "$REL"
tar -xzf "$TMP/release.tar.gz" -C "$REL"
[ -d "$REL/backend" ] || die "압축 안에 backend/ 가 없습니다"
say "풀었습니다 — $REL"

# ── 3. 공유 자료를 링크한다 (배포가 DB·캐시·키를 덮어쓰지 않게) ────────
rm -rf "$REL/backend/storage" "$REL/backend/cache" "$REL/backend/.env" "$REL/backend/.venv"
ln -s "$SHARED/storage" "$REL/backend/storage"
ln -s "$SHARED/cache"   "$REL/backend/cache"
ln -s "$SHARED/.env"    "$REL/backend/.env"
chown -R "$APP_USER:$APP_USER" "$REL"
say "shared 링크 연결 — storage · cache · .env"

# ── 4. 의존성 설치 ────────────────────────────────────────────────────
say "의존성 설치 중 (몇 분 걸릴 수 있습니다)"
sudo -u "$APP_USER" "$VENV/bin/pip" install -q -e "$REL/backend" \
  || die "의존성 설치 실패"

# ── 5. 유닛 파일을 릴리스의 것으로 갱신 ────────────────────────────────
if [ -f "$REL/deploy/chaeum@.service" ]; then
  install -m 644 "$REL/deploy/chaeum@.service" "$UNIT_DEST"
  systemctl daemon-reload
  say "systemd 유닛 갱신"
fi

# ── 6. current 를 새 릴리스로 돌리고 새 포트에 띄운다 ──────────────────
# 이미 떠 있는 구 프로세스는 기동 시점에 경로가 확정돼 있어 영향받지 않습니다.
ln -sfn "$REL" "$ROOT/current"
systemctl restart "chaeum@$NEW_PORT"
say "chaeum@$NEW_PORT 기동"

# ── 7. 정상 기동 확인 — 여기가 안전장치 ────────────────────────────────
say "헬스체크 (최대 ${HEALTH_TIMEOUT}초)"
HEALTHY=0
for _ in $(seq 1 "$HEALTH_TIMEOUT"); do
  if curl -fsS -m 3 "http://127.0.0.1:$NEW_PORT/health" >/dev/null 2>&1; then
    HEALTHY=1; break
  fi
  sleep 1
done

if [ "$HEALTHY" -ne 1 ]; then
  echo "✗ 새 버전이 뜨지 않았습니다. 전환하지 않고 중단합니다."
  echo "── 실패한 유닛 로그 ──"
  journalctl -u "chaeum@$NEW_PORT" -n 40 --no-pager || true
  systemctl stop "chaeum@$NEW_PORT" || true
  [ -n "$PREV_CURRENT" ] && ln -sfn "$PREV_CURRENT" "$ROOT/current"
  die "배포 중단 — 구 버전($CURRENT_PORT)이 계속 서비스합니다"
fi
say "헬스체크 통과"

# ── 8. nginx 가 새 포트를 보게 전환 ────────────────────────────────────
# 설정 파일 한 줄만 바꾸고 reload 합니다. 기존 연결은 유지되고 새 요청만 옮겨갑니다.
cat > "$UPSTREAM_CONF" <<EOF
# 배포 스크립트가 자동으로 씁니다. 손으로 고치지 마세요.
upstream chaeum_backend {
    server 127.0.0.1:$NEW_PORT;
}
EOF
nginx -t || die "nginx 설정 검사 실패 — 전환하지 않았습니다"
systemctl reload nginx
say "전환 완료 — $CURRENT_PORT → $NEW_PORT"

# ── 9. 구 버전 정지, 재부팅 시 올라올 쪽도 새 포트로 ───────────────────
systemctl stop "chaeum@$CURRENT_PORT" || true
systemctl disable "chaeum@$CURRENT_PORT" >/dev/null 2>&1 || true
systemctl enable  "chaeum@$NEW_PORT"    >/dev/null 2>&1 || true
say "구 버전 정지 및 자동시작 대상 이전"

# ── 10. 오래된 릴리스 정리 (롤백용으로 최근 것만 남김) ─────────────────
# shellcheck disable=SC2012
ls -1dt "$RELEASES"/*/ 2>/dev/null | tail -n "+$((KEEP_RELEASES + 1))" | while read -r old; do
  [ "$(readlink -f "$old")" = "$(readlink -f "$ROOT/current")" ] && continue
  rm -rf "$old" && say "오래된 릴리스 삭제 — $old"
done

echo "══════════ 배포 성공 — $SHA · 포트 $NEW_PORT ══════════"
