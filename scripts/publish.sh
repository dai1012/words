#!/usr/bin/env bash
# 词库发布准备：构建 → 校验 → 零 diff 确认 → 展示变更。
#
# 用法：
#   ./scripts/publish.sh            # 只准备，不 commit / push
#   ./scripts/publish.sh --check    # 只检查（构建不落盘 + 校验），不修改
#   ./scripts/publish.sh --push     # 准备 + commit（仅词库文件）+ push 到 upstream
#
# 任何一步失败立即停止。不使用 force push，不保存任何凭证（依赖已配置的
# git credential helper / SSH）。
set -euo pipefail

MODE="${1:-prepare}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALLOWED_PATHS="^(README\.md|catalog\.json|\.gitignore|packs/|sources/|scripts/|schemas/|\.github/)( |$)"

cd "$REPO_ROOT"

# 1. 确认位于 words 仓库。
if [[ "$(git rev-parse --show-toplevel 2>/dev/null)" != "$REPO_ROOT" ]]; then
    echo "error: 必须在 words 仓库内运行 publish.sh" >&2
    exit 1
fi

# 2. 确认工作树状态：不允许词库发布范围之外的未提交变更。
STRAY="$(git status --porcelain | awk '{print $2}' | { grep -vE "$ALLOWED_PATHS" || true; })"
if [[ -n "$STRAY" ]]; then
    echo "error: 存在词库发布范围外的未提交变更，先处理它们：" >&2
    echo "$STRAY" >&2
    exit 1
fi

if [[ "$MODE" == "--check" ]]; then
    # 只检查：构建到内存比较（不写盘）+ 完整校验。
    python3 scripts/build_catalog.py --check
    python3 scripts/validate_release.py
    echo "CHECK OK: 生成文件无漂移，校验全部通过"
    exit 0
fi

# 3-5. 构建 → 校验 → 再构建确认零 diff。
python3 scripts/build_catalog.py
python3 scripts/validate_release.py
python3 scripts/build_catalog.py --check >/dev/null
echo "BUILD OK: 重复构建零 diff"

# 6. 展示即将发布的变更。
if [[ -n "$(git status --porcelain)" ]]; then
    git status --short
    git diff --stat
else
    echo "工作树无变更（catalog/packs 与已提交版本一致）"
fi

if [[ "$MODE" != "--push" ]]; then
    echo
    echo "准备完成。未 commit / push。"
    echo "确认无误后执行：./scripts/publish.sh --push"
    exit 0
fi

# 8. --push：验证分支 → commit（仅词库文件）→ push upstream。
CURRENT_BRANCH="$(git branch --show-current)"
if [[ -z "$CURRENT_BRANCH" ]]; then
    echo "error: detached HEAD，无法推送" >&2
    exit 1
fi
UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name "@{upstream}" 2>/dev/null || true)"
if [[ -z "$UPSTREAM" ]]; then
    echo "error: 当前分支 $CURRENT_BRANCH 无 upstream，先设置 git push -u origin $CURRENT_BRANCH" >&2
    exit 1
fi

if [[ -z "$(git status --porcelain)" ]]; then
    echo "nothing to commit"
    exit 0
fi

# commit message：catalog 版本 + 每个 pack 的 packID@version 摘要。
CATALOG_VERSION="$(python3 -c 'import json;print(json.load(open("catalog.json"))["catalogVersion"])')"
PACK_SUMMARY="$(python3 -c '
import json
c=json.load(open("catalog.json"))
print(", ".join("{}@v{}".format(p["packID"], p["packVersion"]) for p in c["packs"]))
')"
MESSAGE="chore: publish word pack catalog v${CATALOG_VERSION} (${PACK_SUMMARY})"

git add README.md catalog.json packs sources scripts schemas .github
git commit -m "$MESSAGE"
git push "$UPSTREAM" "HEAD:$CURRENT_BRANCH"
echo "PUSH OK: $UPSTREAM ($MESSAGE)"
