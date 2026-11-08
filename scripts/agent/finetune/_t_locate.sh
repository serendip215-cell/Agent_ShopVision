#!/usr/bin/env bash
# 本地模拟测试：验证 scnet_start.sh 的「上传包定位」逻辑在多种摆放方式下都能找到。
# 不装依赖、不加载模型，只测路径探测这一段。

set -uo pipefail
SRC_SCRIPT="$1"   # scnet_start.sh 路径
TMPROOT=$(mktemp -d)
pass=0; fail=0

# 抽取出 scnet_start.sh 里的定位逻辑（第 2 段），套到不同目录布局下试
probe_logic=$(cat <<'EOS'
REPO=""
for cand in \
    "$(pwd)" \
    "$(pwd)/exp5-5.2-upload" \
    /workspace /workspace/exp5-5.2-upload \
    /data /data/exp5-5.2-upload \
    /root /root/exp5-5.2-upload \
    "$HOME" "$HOME/exp5-5.2-upload" \
    /mnt /mnt/exp5-5.2-upload ; do
  if [ -f "$cand/scripts/agent/finetune/train_lora.py" ]; then
    REPO="$cand"; break
  fi
done
if [ -z "$REPO" ]; then
  found=$(find "$SEARCHROOT" -maxdepth 8 -name train_lora.py 2>/dev/null | head -n 1)
  [ -n "$found" ] && REPO=$(cd "$(dirname "$found")/../../.." && pwd)
fi
echo "${REPO:-NONE}"
EOS
)

make_pkg() {
  local root="$1"
  mkdir -p "$root/scripts/agent/finetune"
  echo "# stub" > "$root/scripts/agent/finetune/train_lora.py"
}

check() {
  local name="$1" expected="$2" got="$3"
  if [ "$got" = "$expected" ]; then
    echo "PASS  $name"
    pass=$((pass+1))
  else
    echo "FAIL  $name  got=$got want=$expected"
    fail=$((fail+1))
  fi
}

# 场景 A：包直接在当前工作目录
A="$TMPROOT/a"; mkdir -p "$A"; make_pkg "$A"
got=$(cd "$A" && SEARCHROOT="$A" bash -c "$probe_logic")
check "包=当前目录" "$A" "$got"

# 场景 B：当前目录下有 exp5-5.2-upload 子目录
B="$TMPROOT/b"; mkdir -p "$B"; make_pkg "$B/exp5-5.2-upload"
got=$(cd "$B" && SEARCHROOT="$B" bash -c "$probe_logic")
check "包=子目录 exp5-5.2-upload" "$B/exp5-5.2-upload" "$got"

# 场景 C：包埋在深一点的子目录里（靠 find 兜底）
C="$TMPROOT/c"; mkdir -p "$C/who/knows"; make_pkg "$C/who/knows/exp5-5.2-upload"
got=$(cd "$C" && SEARCHROOT="$C" bash -c "$probe_logic")
check "包=深层子目录（find 兜底）" "$C/who/knows/exp5-5.2-upload" "$got"

# 场景 D：什么都没有 -> NONE
D="$TMPROOT/d"; mkdir -p "$D"
got=$(cd "$D" && SEARCHROOT="$D" bash -c "$probe_logic")
check "空目录 -> NONE" "NONE" "$got"

rm -rf "$TMPROOT"
echo
echo "结果：$pass 通过 / $fail 失败"
[ "$fail" -eq 0 ] || exit 1