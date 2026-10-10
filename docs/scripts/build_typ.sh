#!/usr/bin/env bash
# 编译 docs/typ/ 下的 .typ 为带时间戳的 PDF。
#   用法: bash docs/scripts/build_typ.sh        # 列出 docs/typ/*.typ，输入编号选择
#         bash docs/scripts/build_typ.sh 2      # 直接选第 2 个
#         bash docs/scripts/build_typ.sh 实验一  # 按文件名（含关键字）选择
#   Windows 也可直接双击/运行 docs/scripts/build_typ.cmd（自动转调本脚本）。
# 输出: docs/build/<名称>-<年月日-时分秒>.pdf（该目录不入 git）。
# Windows(Git Bash)/macOS/Linux 通用；docs/typst/ 缺编译器时自动按当前系统下载。
set -e
cd "$(dirname "$0")/../.."

TYP_DIR="docs/typ"
OUT_DIR="docs/build"
TOOL_DIR="docs/typst"
TYPST_VER="v0.15.1"

# ---- 1. 找/下载 typst ----
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*|Windows_NT) EXE="typst.exe"; PLATFORM="x86_64-pc-windows-msvc"; ARCHIVE="zip" ;;
  Darwin)
    if [ "$(uname -m)" = "arm64" ]; then PLATFORM="aarch64-apple-darwin"; else PLATFORM="x86_64-apple-darwin"; fi
    EXE="typst"; ARCHIVE="tar.xz" ;;
  *) EXE="typst"; PLATFORM="x86_64-unknown-linux-musl"; ARCHIVE="tar.xz" ;;
esac

TYPST=""
for cand in "$TOOL_DIR/$EXE" "$TOOL_DIR"/*/"$EXE"; do
  if [ -f "$cand" ]; then TYPST="$cand"; break; fi
done
if [ -z "$TYPST" ] && command -v typst >/dev/null 2>&1; then
  TYPST="$(command -v typst)"
fi
if [ -z "$TYPST" ]; then
  echo ">> docs/typst/ 未找到 typst，下载 $TYPST_VER ($PLATFORM) ..."
  mkdir -p "$TOOL_DIR"
  URL="https://github.com/typst/typst/releases/download/$TYPST_VER/typst-$PLATFORM.$ARCHIVE"
  TMP="$TOOL_DIR/_dl.$ARCHIVE"
  curl -fL -o "$TMP" "$URL"
  if [ "$ARCHIVE" = "zip" ]; then
    unzip -o -j "$TMP" "*/$EXE" "*/LICENSE" "*/NOTICE" -d "$TOOL_DIR"
  else
    tar -xJf "$TMP" -C "$TOOL_DIR" --strip-components=1 "typst-$PLATFORM/$EXE" "typst-$PLATFORM/LICENSE" "typst-$PLATFORM/NOTICE"
  fi
  rm -f "$TMP"
  TYPST="$TOOL_DIR/$EXE"
fi
[ -f "$TYPST" ] || { echo "错误: typst 不可用 ($TYPST)"; exit 1; }

# ---- 2. 收集并选择 .typ ----
files=()
for f in "$TYP_DIR"/*.typ; do
  [ -f "$f" ] || continue
  files+=("$f")
done
[ "${#files[@]}" -gt 0 ] || { echo "错误: $TYP_DIR/ 下没有 .typ 文件"; exit 1; }

echo "可用的 .typ 文件:"
i=1
for f in "${files[@]}"; do
  echo "  $i) $(basename "$f")"
  i=$((i + 1))
done

choice="${1:-}"
if [ -z "$choice" ]; then
  printf "请输入编号 (1-%d): " "${#files[@]}"
  read -r choice
fi

TARGET=""
case "$choice" in
  ''|*[!0-9]*)  # 非纯数字 → 按文件名匹配
    for f in "${files[@]}"; do
      case "$(basename "$f")" in *"$choice"*) TARGET="$f"; break ;; esac
    done ;;
  *)
    if [ "$choice" -ge 1 ] && [ "$choice" -le "${#files[@]}" ]; then
      TARGET="${files[$((choice - 1))]}"
    fi ;;
esac
[ -n "$TARGET" ] || { echo "错误: 未匹配到 .typ (输入: $choice)"; exit 1; }

# ---- 3. 编译 ----
mkdir -p "$OUT_DIR"
BASE="$(basename "$TARGET" .typ)"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/$BASE-$STAMP.pdf"

echo ">> 编译 $(basename "$TARGET") → $OUT"
"$TYPST" compile "$TARGET" "$OUT"
echo ">> 完成: $OUT"
