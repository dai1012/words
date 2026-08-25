# Schema 对应关系

本仓库的 `catalog.json` 与 `packs/*.json` 遵循 JapaneseWordWatch Issue 005
「远端词库 JSON v1」schema。权威实现是 App 仓库的 Swift 代码：

- `JapaneseWordiPhone/Services/RemoteWordPacks/RemoteWordPackSchema.swift`
- `JapaneseWordiPhone/Services/RemoteWordPacks/RemoteWordPackValidator.swift`

测试（App 仓库）：

- `JapaneseWordTimelineTests/RemoteWordPackCatalogTests.swift`（schema 语义）
- `JapaneseWordTimelineTests/RemoteWordPackConfigurationTests.swift`（URL 策略）
- Issue 005 tests（`issues/005-remote-word-pack-schema/D.test-plan.md`）

## 文档结构

### catalog.json

```json
{
  "schemaVersion": 1,
  "catalogVersion": 1,
  "generatedAt": "2026-08-05T10:19:49Z",
  "packs": [
    {
      "packID": "com.dai1012.test.basic",
      "packVersion": 1,
      "title": "测试基础词包（Test Basic）",
      "language": "ja",
      "classification": "test",
      "level": "beginner",
      "directoryPath": ["中日", "商务"],
      "entryCount": 5,
      "fileURL": "packs/test-basic.json",
      "fileSize": 1243,
      "sha256": "4a5dc0ec…",
      "minimumAppVersion": "1.0.0",
      "description": "…",
      "tags": ["test", "basic"]
    }
  ]
}
```

### packs/<name>.json

```json
{
  "schemaVersion": 1,
  "packID": "com.dai1012.test.basic",
  "packVersion": 1,
  "entryCount": 5,
  "metadata": { "title": "…", "language": "ja", "classification": "test",
                "level": "beginner", "description": "…", "tags": ["test", "basic"] },
  "entries": [
    { "entryID": "test-basic-001", "term": "おはよう",
      "reading": "おはよう", "meaning": "早上好（测试词包）" }
  ]
}
```

## 关键规则（Swift validator 的冻结规则）

| 字段 | 规则 |
| --- | --- |
| `schemaVersion` | 必须是整数 `1`；两阶段 decode，`!= 1` 直接拒绝 |
| `packID` | `^[a-z0-9]+(?:[.-][a-z0-9]+)*$`，3–128 字符，至少一个 `.` |
| `entryID` | `^[a-z0-9][a-z0-9._-]{0,127}$`，作用域内唯一 |
| `entries[]` 顺序 | 词条实际身份是 `packID + entryIndex`（位置索引）；entryID 是 pack 内稳定业务标识，但不是当前收藏/隐藏/同步的索引身份。已发布词包未经版本化迁移，不得删除、插入或重排既有 entries；允许原位修改字段值与在末尾追加 |
| `packVersion`/`catalogVersion` | `>= 1` 整数 |
| `generatedAt` | 精确 RFC 3339 UTC，真实日历日期 |
| `language` | `^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$` |
| `classification`/`level`/`tag` | 小写 slug `^[a-z0-9]+(?:-[a-z0-9]+)*$` |
| 可选字段（`level`/`description`/`tags`） | 缺失省略 key；**显式 `null` 非法** |
| `fileURL` | 相对路径（无 `/` 开头、无 `..`、percent-encoding 合法）或绝对 https；App 解析相对 URL 到 catalog 目录 |
| `directoryPath`（descriptor 可选，Issue 011） | 字符串数组；source 相对 `sources/` 的父目录，从最外层到最内层；根目录 source 为 `[]`；段禁止空/纯空白/`.`/`..`/前导尾随空格/`/`/`\`/Unicode 控制字符（category `Cc`，按 `unicodedata.category` 判断）；允许中文/日文/英文/Emoji/中间空格；只存在于 catalog descriptor，pack JSON 无此字段；仅影响 App 浏览位置，不参与身份、安装、更新、收藏与同步判断；source 顶层或 metadata 手写该字段时 build 失败 |
| `entryCount` | 与 `entries` 实际数量一致 |
| `fileSize`/`sha256` | 与 pack 文件原始字节完全一致（`fileSize`=字节数，`sha256`=小写 64 位 hex） |

## Python 校验与 Swift validator 的关系

`scripts/validate_release.py` 复刻上述规则用于**生成侧**快速校验，但它不是
App Swift validator 的替代品。两者是独立实现，任何 schema 变更必须先在
App 仓库（Issue 005 的 Swift validator 及其测试）落地，再同步到这里。
App 安装 pack 时仍会执行完整的 Swift 校验（structure/semantic/integrity）。

补充边界：descriptor.directoryPath 的目录段合法性（禁止空段、`.`/`..`、
前后空格、路径分隔符、Unicode 控制字符等）目前只由本仓库的
`scripts/build_catalog.py` 与 `scripts/validate_release.py` 校验。App 端
Swift validator 不做目录段规则检查：解码层仅要求数组为字符串数组、缺失
默认 `[]`、显式 null 解码失败。也就是说，目录段规则一旦在生成侧放松，
App 不会拦截——本仓库构建脚本是这条规则的唯一防线。

已验证的移动行为：仅移动 source（保持 basename 与 JSON 内容不变）时，
pack 文件 byte-identical，descriptor 中只有 directoryPath 变化，catalogVersion
随之 +1；packID、fileURL、fileSize、sha256 与 entries 顺序均不变。

## 发布后验证（真实 Raw URL）

```bash
# 等待 GitHub Raw 缓存更新后：
curl -fsSL https://raw.githubusercontent.com/dai1012/words/main/catalog.json -o /tmp/catalog.json
curl -fsSL https://raw.githubusercontent.com/dai1012/words/main/packs/test-basic.json -o /tmp/test-basic.json
curl -fsSL https://raw.githubusercontent.com/dai1012/words/main/packs/test-travel.json -o /tmp/test-travel.json
shasum -a 256 /tmp/test-basic.json   # 与 catalog.json 中 sha256 一致
cmp /tmp/test-basic.json packs/test-basic.json   # 与本地发布文件 byte-identical
```
