# words — JapaneseWordWatch 远程词库发布仓库

JapaneseWordWatch（iPhone）Issue 006 远程词库下载功能的发布仓库。App 从
`catalog.json` 读取词包清单，按清单下载 `packs/*.json` 并安装。本仓库只负责
词库数据与发布自动化，不包含 App 代码。

- App 仓库：
- catalog Raw URL：`https://raw.githubusercontent.com/dai1012/words/main/catalog.json`

## 目录结构

```
words/
├── README.md                  # 本文件
├── catalog.json               # 【生成】词包清单（脚本生成，禁止手工修改）
├── packs/                     # 【生成】App 下载的正式词包（脚本生成）
│   ├── test-basic.json
│   └── test-travel.json
├── sources/                   # 可编辑源数据（人工/AI 只改这里）
│   ├── test-basic.source.json
│   └── test-travel.source.json
├── scripts/
│   ├── build_catalog.py       # 生成 packs + catalog，计算所有派生字段
│   ├── validate_release.py    # 校验 schema/完整性/一致性/无漂移
│   └── publish.sh             # 一条命令：构建 + 校验 + 发布准备
├── schemas/
│   └── README.md              # 与 App Issue 005 schema 的对应关系
└── .github/workflows/
    └── validate-word-packs.yml  # push/PR 自动校验，只读不改
```

## 如何修改词库

1. 编辑 `sources/<name>.source.json`：改 `metadata`（标题/分类/级别/标签/描述）
   或 `entries`（单词列表）。`entryID` 必须唯一。
2. 如果词条内容有变化，把 `packVersion` 加 1（见下节）。
3. 运行 `./scripts/publish.sh --push`。

不要直接编辑 `catalog.json` 或 `packs/`——它们由脚本生成，手工改动会被校验拒绝。

## 如何提升 packVersion

`sources/<name>.source.json` 里的 `packVersion` 是唯一的人工版本信号：

- 词条或 metadata 内容变化 → 必须把 `packVersion` +1。
- 内容没变 → 保持原值，重复构建幂等成功。
- 内容变了但 `packVersion` 没升 → `build_catalog.py` 直接失败并提示，
  不会静默覆盖（fail closed）。

App 对同一 packID 的 installed 版本与 catalog 版本不同会拒绝覆盖（见
「Issue 006 当前限制」），所以发布新版测试包时版本号一定要变化。

## 如何本地构建

```bash
./scripts/publish.sh --check    # 只检查：构建到内存比较，不写盘
```

构建脚本负责：

- 从 `sources/*.source.json` 生成 `packs/*.json`。
- 确定性序列化（UTF-8、固定 key 顺序、固定缩进）：重复构建 byte-identical。
- 自动计算并写入：`entryCount`、`fileSize`、`sha256`、catalog 里全部
  descriptor 字段、`catalogVersion`、`generatedAt`。
- 输出先写入临时目录，全部校验通过后原子替换；失败不留半生成结果。

## 如何校验

```bash
python3 scripts/validate_release.py
```

校验内容：

- JSON 可解析、符合 Issue 005 schema（版本/ID grammar/语言/分类/标签/必填）。
- descriptor 与 pack 一致（packID/packVersion/entryCount/metadata 逐项）。
- 完整性：`fileSize` 与 `sha256` 基于仓库内原始字节计算并比对。
- `fileURL` 安全：只允许相对路径指向 `packs/`，无 `..`、无 `/` 开头、
  无反向斜杠、无 http。
- 限制：catalog ≤ 1 MiB / 100 descriptors；pack ≤ 10 MiB / 20,000 词条。
- 无漂移：重新执行一次构建，与现有文件必须零 diff。

注意：`validate_release.py` 是**生成侧校验**，不是 App Swift validator 的
替代品。App 安装时仍会用 Issue 005/006 的 Swift validator 重新校验原始字节
（`RemoteWordPackValidator`）。发布前建议在 App 仓库运行一次
`JapaneseWordTimelineTests`（覆盖 005/006 validator 的全部测试）。

## 如何发布

```bash
./scripts/publish.sh            # 构建 + 校验 + 零 diff 确认 + 展示变更，不提交
./scripts/publish.sh --push     # 上述步骤通过后 commit（仅词库文件）+ push
```

`--push` 模式：

- 要求当前分支有 upstream，拒绝 detached HEAD。
- 只提交词库相关文件（README/catalog/packs/sources/scripts/schemas/.github）。
- commit message 自动包含 catalog 版本与每个 pack 的 `packID@version` 摘要。
- 不使用 force push，不保存任何凭证。
- 任何一步失败立即停止。

## 哪些字段由脚本自动生成，禁止手工修改

| 文件 | 自动生成字段 |
| --- | --- |
| `packs/*.json` | `schemaVersion`、`entryCount` |
| `catalog.json` | 全部（`schemaVersion`、`catalogVersion`、`generatedAt`、每个 descriptor 的 `entryCount`/`fileSize`/`sha256`/`fileURL`/`minimumAppVersion`） |
| `scripts/build_catalog.py` | `MINIMUM_APP_VERSION` 常量（所有 descriptor 共用） |

`fileSize` 与 `sha256` 基于最终落盘的 pack 原始字节计算，绝不能手填。
`minimumAppVersion` 当前为 `1.0.0`（App `MARKETING_VERSION`），定义在
`build_catalog.py` 顶部。

## App 无需重新 build 的情况

用户不需要升级 App，只要 App 已支持远程词库（Issue 006 已实现），新词包发布后
在 App 里刷新目录即可看到。发布测试包后 iOS 无需重装。

## App 需要重新发布的情况

- `minimumAppVersion` 提高（App 版本门槛变化）。
- 出现 App 不认识的 `schemaVersion`（schema 升级，属 Issue 008 之后的规划）。
- 修改了需要配套 UI 行为的包结构。

## Issue 006 当前限制

- 同一 packID 已安装时不能覆盖：App 对已安装 pack 的 `packVersion` 与 catalog
  版本不同会拒绝安装（`alreadyInstalledDifferentVersion`）。
- 测试新版词包时，需要先在 App 里删除旧包，再下载新版本。
- 自动更新（同 packID 版本提升自动替换）属于 Issue 008，当前未实现。
- 无离线 catalog 缓存：每次刷新都重新请求网络。

## GitHub Raw URL 缓存

`raw.githubusercontent.com` 有 CDN 缓存。发布后**立即**访问可能拿到旧内容
或 404。等待数分钟，或提升 `packVersion` 强制内容变化。验证发布结果请使用
`curl` 直接请求 raw URL 并比对 SHA-256（见 `schemas/README.md`）。

## 当前测试词包

| packID | 版本 | 词条 | 说明 |
| --- | --- | --- | --- |
| `com.dai1012.test.basic` | v1 | 5 | 基础问候语，classification=test |
| `com.dai1012.test.travel` | v1 | 5 | 旅行场景，classification=travel |

内容均标注「测试词包」，仅用于联调验证，非真实学习数据。

## 第三方词包来源与许可证

### JLPT N5 日语词汇

- 上游项目：`jamsinclair/open-anki-jlpt-decks`
- 原始数据：<https://raw.githubusercontent.com/jamsinclair/open-anki-jlpt-decks/main/src/n5.csv>
- 项目主页：<https://github.com/jamsinclair/open-anki-jlpt-decks>
- 上游版权：Copyright (c) 2020 Jamie Sinclair
- 许可证：MIT，完整文本见 `sources/jlpt-n5.LICENSE.txt`

本仓库保持原始 CSV 的词条顺序，将 `expression`/`reading` 转换为
`term`/`reading`，并将英文 `meaning` 翻译、校订为简体中文。每条 `entryID`
仅由上游原始 `guid` 的 UTF-8 字节计算 SHA-256 后生成，格式为
`jlpt-n5-<64 位小写十六进制>`；修改中文释义不会改变 `entryID`。

该 MIT 许可及来源说明同时适用于本仓库的 JLPT N1–N5 词包。上游数据修正记录：N4
`ごらんになる`、`かまう` 的空 reading 分别补为 expression 原文；N2 上游第二次出现
的完全重复词条 `やかん / やかん / kettle`（guid `tkW,zBf(b9`）仅保留首次出现，
N2 发布词条数为 1905。
