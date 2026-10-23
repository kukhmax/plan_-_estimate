#!/usr/bin/env bash
# Перевод VM на `main`, когда код на VM уже выложен и `main` отличается от него ТОЛЬКО документами (README.md, docs/).
# Контейнеры НЕ пересоздаются, образы не собираются, база не трогается: меняется только ветка и коммит в каталоге репозитория.
# Если в `main` есть что-то ещё (код, миграции, образы, compose, frontend), скрипт останавливается и просит полную выкладку.
# Запуск (в НОВОЙ SSH-сессии на VM):
#   cd ~/apps/plan_-_estimate && git fetch -q origin main && git show origin/main:docs/SWITCH_VM_DOCS_ONLY_RU.sh > ~/switch_docs.sh && bash ~/switch_docs.sh
cd ~/apps/plan_-_estimate || { echo "FAIL: нет каталога ~/apps/plan_-_estimate"; return 1 2>/dev/null || exit 1; }

(
set -uo pipefail
fail() { echo; echo "=== FAIL на шаге: $1 ==="; echo "$2"; echo "Дальше НЕ идём. Пришлите весь вывод выше."; exit 1; }
ok()   { echo "PASS: $1"; }
has()  { grep -q -- "$1" <<<"$2"; }
BR="${SWITCHDOCS_BRANCH:-main}"

echo "################ G0: проверка (только чтение) ################"
[ -z "$(git status --short)" ] || fail "G0" "Рабочее дерево не чистое: $(git status --short)"
PREV=$(git branch --show-current); [ -n "$PREV" ] || fail "G0" "VM в состоянии detached HEAD: сначала вернитесь на ветку"
PREV_SHA=$(git rev-parse HEAD)
echo "ветка на VM сейчас: $PREV, коммит $(git rev-parse --short HEAD)"
git fetch -q origin "$BR" || fail "G0" "git fetch не удался"
git merge-base --is-ancestor HEAD "origin/$BR" || fail "G0" "HEAD не предок origin/$BR (ветки разошлись)"
CODE=$(git diff --name-only HEAD "origin/$BR" | grep -Ev '^(README.md|docs/)' || true)
[ -z "$CODE" ] || fail "G0" "между VM и origin/$BR есть изменения кода или настроек (не только документы): $CODE — это уже полная выкладка, а не перевод"
H=$(curl -fsS https://plan-estimate.pl/api/health) || fail "G0" "health недоступен"
has '"status":"ok"' "$H" || fail "G0" "health не ok: $H"
AL=$(docker exec plan_estimate_backend alembic current 2>/dev/null)
# голова миграций — самая новая миграция в origin/$BR (код между VM и origin/$BR не различается, значит, база уже на ней)
HEADREV=$(git ls-tree --name-only "origin/$BR" backend/alembic/versions/ | sed -n 's#.*/\(00[0-9][0-9]_[a-z0-9_]*\)\.py$#\1#p' | sort | tail -1)
[ -n "$HEADREV" ] || fail "G0" "не нашёл миграции в origin/$BR"
has "$HEADREV" "$AL" || fail "G0" "alembic current не $HEADREV: $AL"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G0" "backend не healthy"
echo "приходит (только документы):"; git log --oneline HEAD.."origin/$BR" | head -20
ok "G0"

echo; echo "################ G1: переключение ветки ################"
git checkout -q -B "$BR" "origin/$BR" || { git checkout -q -B "$PREV" "$PREV_SHA" 2>/dev/null; fail "G1" "переключение не удалось (код возвращён на $PREV)"; }
[ "$(git branch --show-current)" = "$BR" ] && [ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$BR")" ] || fail "G1" "ветка или коммит не те"
[ -z "$(git status --short)" ] || fail "G1" "после переключения дерево не чистое"
H=$(curl -fsS https://plan-estimate.pl/api/health) && has '"status":"ok"' "$H" || fail "G1" "health не ok"
[ "$(docker inspect -f '{{.State.Health.Status}}' plan_estimate_backend)" = "healthy" ] || fail "G1" "backend не healthy"
ok "G1 (ветка $BR, коммит $(git rev-parse --short HEAD); контейнеры не менялись)"

echo; echo "=============== ВСЁ PASS: VM на ветке $BR, коммит $(git rev-parse --short HEAD) ==============="
echo "Дальше: все следующие выкладки берите из origin/main; бэкап под новую голову (в НОВОЙ сессии):"
echo "  cd ~/apps/plan_-_estimate && BACKUP_BRANCH=main BACKUP_HEAD=$HEADREV bash ~/backup_a9.sh"
)
