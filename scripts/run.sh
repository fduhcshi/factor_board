#!/usr/bin/env bash
# 统一启动脚本：前台直接运行，--background 交给 nohup 后台执行。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi

if ! "$PYTHON" -c "import akshare" >/dev/null 2>&1; then
  cat >&2 <<EOF
当前解释器缺少依赖：$PYTHON

请任选一种方式：
  1) 在项目内建虚拟环境：python3 -m venv .venv && .venv/bin/pip install -e .
  2) 指定已装好依赖的解释器：PYTHON_BIN=/path/to/python bash scripts/run.sh
EOF
  exit 2
fi

BACKGROUND=0
ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--background" ]]; then
    BACKGROUND=1
  else
    ARGS+=("$arg")
  fi
done

if [[ "$BACKGROUND" -eq 1 ]]; then
  RUN_ID="$(date +%Y%m%d-%H%M%S)"
  LOG_DIR="$ROOT/outputs/logs"
  mkdir -p "$LOG_DIR"
  LOG_FILE="$LOG_DIR/run-$RUN_ID.log"
  nohup "$PYTHON" -u main.py ${ARGS[@]+"${ARGS[@]}"} >"$LOG_FILE" 2>&1 &
  PID=$!
  echo "run_id=$RUN_ID"
  echo "pid=$PID"
  echo "log=$LOG_FILE"
  echo "查看日志: tail -f $LOG_FILE"
  echo "停止任务: kill $PID"
else
  exec "$PYTHON" main.py ${ARGS[@]+"${ARGS[@]}"}
fi
