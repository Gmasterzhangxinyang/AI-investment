#!/bin/zsh
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
BUNDLED_PYTHON="$ROOT_DIR/runtime/python/bin/python3"
BUNDLED_SITE_PACKAGES="$ROOT_DIR/runtime/site-packages"

clear
echo "AI 投研工作台 - 初始化环境"
echo "----------------------------------------"
echo "项目目录: $ROOT_DIR"
echo ""

if [[ -x "$BUNDLED_PYTHON" && -d "$BUNDLED_SITE_PACKAGES" ]]; then
  echo "检测到交付包内置 Python 和全部运行依赖。"
  echo "正在做离线环境自检..."
  export PYTHONPATH="$BUNDLED_SITE_PACKAGES:$ROOT_DIR/backend:$ROOT_DIR"
  export PYTHONNOUSERSITE=1
  export PYTHONDONTWRITEBYTECODE=1
  if [[ -f "$BUNDLED_SITE_PACKAGES/certifi/cacert.pem" ]]; then
    export SSL_CERT_FILE="$BUNDLED_SITE_PACKAGES/certifi/cacert.pem"
  fi
  if "$BUNDLED_PYTHON" - <<'PY' >/dev/null 2>&1
import numpy
import openpyxl
import pandas
import reportlab
from superpower.server import app
PY
  then
    echo ""
    echo "内置环境检查通过，无需安装 Python，也无需联网安装依赖。"
    echo "现在可以双击「启动AI投研.command」。"
    echo "按任意键退出。"
    if [[ -t 0 ]]; then
      read -k 1
    fi
    exit 0
  fi
  echo ""
  echo "内置环境不完整，请联系交付方重新获取完整离线包。"
  echo "按任意键退出。"
  if [[ -t 0 ]]; then
    read -k 1
  fi
  exit 1
fi

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

if ! "$PYTHON" -m pip install -r "$ROOT_DIR/requirements.lock"; then
  echo ""
  echo "固定版本依赖安装失败。请把上面的错误信息发给开发者。"
  echo "按任意键退出。"
  if [[ -t 0 ]]; then
    read -k 1
  fi
  exit 1
fi

if ! "$PYTHON" -m pip install --no-build-isolation --no-deps -e "$ROOT_DIR"; then
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
