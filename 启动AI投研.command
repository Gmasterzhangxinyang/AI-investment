#!/bin/zsh
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$ROOT_DIR/data/wind/current"
PORT="${AI_RESEARCH_PORT:-8766}"
URL="http://127.0.0.1:${PORT}/frontend/"

ETF_FILE="01_ETF清单和日频公式.xlsx"
TL_FILE="02_TL日频公式.xlsx"
CB_FILE="03_可转债数据.xlsx"

mkdir -p "$DATA_DIR" "$ROOT_DIR/outputs/latest" "$ROOT_DIR/logs"

clear
echo "AI 投研工作台"
echo "----------------------------------------"
echo "项目目录: $ROOT_DIR"
echo "Excel目录: $DATA_DIR"
echo "访问地址: $URL"
echo ""

missing=()
for file in "$ETF_FILE" "$TL_FILE" "$CB_FILE"; do
  if [[ ! -f "$DATA_DIR/$file" ]]; then
    missing+=("$file")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "提示：下面的 Excel 还没有放到 data/wind/current："
  for file in "${missing[@]}"; do
    echo "  - $file"
  done
  echo ""
  echo "系统仍会启动；放好文件后，在网页里点击「一键刷新」。"
  open "$DATA_DIR" >/dev/null 2>&1 || true
  echo ""
fi

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
else
  echo "没有找到 Python。请先安装 Python 3.11+，或把可用 Python 放到 .venv/bin/python。"
  echo "按任意键退出。"
  if [[ -t 0 ]]; then
    read -k 1
  fi
  exit 1
fi

echo "使用 Python: $PYTHON"

"$PYTHON" - <<'PY' >/dev/null 2>&1
import numpy
import openpyxl
import pandas
import reportlab
PY
if [[ $? -ne 0 ]]; then
  echo ""
  echo "当前 Python 缺少运行依赖。"
  echo "请先双击「初始化环境.command」，完成后再双击「启动AI投研.command」。"
  echo ""
  echo "按任意键退出。"
  if [[ -t 0 ]]; then
    read -k 1
  fi
  exit 1
fi

if command -v curl >/dev/null 2>&1 && curl -fsS "$URL" >/dev/null 2>&1; then
  echo "检测到本地服务已在运行，直接打开工作台。"
  open "$URL"
  exit 0
fi

echo "正在启动本地服务..."
echo "关闭这个窗口会停止服务。"
echo ""

(sleep 1.5 && open "$URL") &
cd "$ROOT_DIR" || exit 1
exec "$PYTHON" serve.py --port "$PORT"
