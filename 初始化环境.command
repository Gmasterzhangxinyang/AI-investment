#!/bin/zsh
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

clear
echo "AI 投研工作台 - 初始化环境"
echo "----------------------------------------"
echo "项目目录: $ROOT_DIR"
echo ""

if [[ -x "$VENV_DIR/bin/python" ]]; then
  PYTHON="$VENV_DIR/bin/python"
  echo "检测到已有本地环境: $VENV_DIR"
else
  if command -v python3 >/dev/null 2>&1; then
    SYSTEM_PYTHON="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    SYSTEM_PYTHON="$(command -v python)"
  else
    echo "没有找到 Python。请先安装 Python 3.11+。"
    echo "按任意键退出。"
    if [[ -t 0 ]]; then
      read -k 1
    fi
    exit 1
  fi

  echo "正在创建本地 Python 环境..."
  "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
  PYTHON="$VENV_DIR/bin/python"
fi

echo "正在安装/更新运行依赖..."
if ! "$PYTHON" -m pip install --upgrade pip setuptools wheel; then
  echo ""
  echo "pip / setuptools 更新失败，请检查网络或 Python 环境。"
  echo "按任意键退出。"
  if [[ -t 0 ]]; then
    read -k 1
  fi
  exit 1
fi

if ! "$PYTHON" -m pip install --no-build-isolation -e "$ROOT_DIR"; then
  echo ""
  echo "依赖安装失败。请把上面的错误信息发给开发者。"
  echo "按任意键退出。"
  if [[ -t 0 ]]; then
    read -k 1
  fi
  exit 1
fi

if ! "$PYTHON" - <<'PY' >/dev/null 2>&1
import numpy
import openpyxl
import pandas
import reportlab
import setuptools
PY
then
  echo ""
  echo "依赖自检失败。请把上面的错误信息发给开发者。"
  echo "按任意键退出。"
  if [[ -t 0 ]]; then
    read -k 1
  fi
  exit 1
fi

echo ""
echo "初始化完成。现在可以双击「启动AI投研.command」。"
echo "按任意键退出。"
if [[ -t 0 ]]; then
  read -k 1
fi
