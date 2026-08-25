# words 仓库使用说明

## 一、仓库用途

仓库：

```text
https://github.com/dai1012/words
```

本地目录：

```text
/Users/xxxxx/work/words
```

该仓库用于管理 JapaneseWordWatch 的远程词库。

当前方式：

```text
修改 sources/*.source.json
        ↓
push 到 GitHub
        ↓
GitHub Actions 自动生成 packs/*.json
        ↓
GitHub Actions 自动更新 catalog.json
        ↓
手机 App 刷新下载页面后看到变化
```

不使用：

- S3
- 私有仓库
- Personal Access Token
- Agent
- App 内置词库更新
- 手工修改 catalog 的方式

---

# 二、目录说明

```text
words/
├── sources/
│   ├── *.source.json
│   └── 任意子目录/
│       └── *.source.json
├── packs/
│   └── *.json
├── catalog.json
├── scripts/
│   ├── build_catalog.py
│   ├── publish.sh
│   └── validate_release.py
└── .github/
    └── workflows/
        └── validate-word-packs.yml
```

各目录职责：

## sources/

人工维护的原始词库。

平时只需要：

- 新增 source
- 修改 source
- 删除 source

例如：

```text
sources/CN/中日/JLPT/jlpt-n5.source.json
sources/CN/中英/IELTS/ielts-core.source.json
sources/test-basic.source.json
```

source 可以放在任意深度的子目录中（目录名不限语言、层数不限）。source
相对 `sources/` 的父目录会自动写入 catalog 的 `directoryPath`，App 下载页面
按该路径动态显示目录浏览层级；App 不直接读取 `sources/`，只读取 catalog。
目录名称（中文、日文、英文等）原样保留，App 不写死任何目录名。

市场目录约定：顶层 `CN/` 表示面向中文用户的市场入口（不表示词条语言）；
其下一层目录表示学习方向，如 `中日`＝中文学习者学日语、`中英`＝中文学习
者学英语、`中西`＝中文学习者学西班牙语。较新的方向目录采用"中文名-英文
名"双语命名（如 `中法-Chinese-French`），便于非中文背景维护者识别；早期
短名目录（中日、中英、中韩、中西）保持不变。未来新增其他市场（如 `JP/`、
`EN/`）时沿用同样约定。测试词包（test-basic / test-travel）为联调夹具，
保留在根目录，不属于任何市场。

规则：

- source 的 basename（如 `N1.source.json` 的 `N1`）在全部 sources 中必须唯一，
  因为 pack 输出文件名由 basename 派生；同名会构建失败
- 只移动 source 到其他目录、不改内容时，pack 文件、下载地址与版本均不变，
  不需要提高 packVersion
- 目录名不允许 Unicode 控制字符（换行、Tab 等）；允许中文、日文、英文、
  Emoji、中间空格
- 不要在 source 中手写 directoryPath，构建会失败（该字段由目录结构自动生成）

## packs/

由脚本自动生成的手机下载文件。

例如：

```text
packs/jlpt-n5.json
packs/test-basic.json
```

不要手工修改。

## catalog.json

手机 App 下载页面读取的词库目录。

包含：

- packID
- packVersion
- 标题
- 分类
- 等级
- 词条数
- 下载地址
- 文件大小
- SHA-256
- 最低 App 版本

不要手工修改。

## scripts/build_catalog.py

负责：

- 校验 source JSON
- 生成 pack
- 统计 entryCount
- 计算 fileSize
- 计算 SHA-256
- 生成 fileURL
- 更新 catalog
- 检测版本号
- 删除已经没有 source 的旧 pack
- 保持重复生成结果一致

## GitHub Actions

当 main 分支的以下文件变化时执行：

```text
sources/**
scripts/build_catalog.py
scripts/validate_release.py
.github/workflows/validate-word-packs.yml
```

Actions 会：

1. 生成 pack 和 catalog
2. 运行校验
3. 检查是否有变化
4. 有变化时自动 commit
5. 正常 push 回 main

自动提交信息：

```text
chore: regenerate word pack catalog [skip ci]
```

自动提交只允许包含：

```text
catalog.json
packs/*.json
```

---

# 三、新增词库

只需要新增一个 source 文件。

例如：

```text
sources/my-new-pack.source.json
```

示例：

```json
{
  "schemaVersion": 1,
  "packID": "com.dai1012.example.basic",
  "packVersion": 1,
  "metadata": {
    "title": "示例词库",
    "language": "ja",
    "classification": "example",
    "level": "beginner",
    "description": "示例词库说明。",
    "tags": [
      "example",
      "basic"
    ]
  },
  "entries": [
    {
      "entryID": "example-basic-001",
      "term": "確認",
      "reading": "かくにん",
      "meaning": "确认"
    }
  ]
}
```

新增词库时：

```text
packVersion = 1
```

source 可以放在任意深度子目录，例如 `sources/中日/商务/基础.source.json`；
父目录自动成为 App 中的目录层级（中日 / 商务），无需修改 App 代码。

注意：source 的 basename 必须在全仓库唯一。如果两个 source 同名（例如
`sources/a/基础.source.json` 与 `sources/b/基础.source.json`），构建会失败，
因为两者会生成同一个 pack 输出文件。

然后提交：

```bash
cd /Users/xxxxxx/work/words

git add sources/my-new-pack.source.json
git commit -m "feat: add example word pack"
git push origin main
```

GitHub Actions 会自动：

- 生成 `packs/my-new-pack.json`
- 更新 `catalog.json`
- 自动 commit
- 自动 push

Actions 完成后，本地同步：

```bash
git pull --ff-only
```

手机端进入下载页面并刷新即可看到。

---

# 四、修改现有词库

修改现有 source 时，必须同时提高 `packVersion`。

例如原来：

```json
"packVersion": 1
```

修改词条后改为：

```json
"packVersion": 2
```

再次修改时：

```json
"packVersion": 3
```

规则：

```text
词包内容不变
→ packVersion 可以不变

词包内容变化
→ packVersion 必须 +1
```

内容变化包括：

- 新增词条
- 删除词条
- 修改 term
- 修改 reading
- 修改 meaning
- 修改标题
- 修改描述
- 修改 tags
- 修改 classification
- 修改 level

以下操作**不算内容变化**，不需要提高 packVersion：

- 只移动 source 到其他目录（basename 不变）：App 中浏览位置变化，pack 文件、
  下载地址、版本均不变
- 目录改名（basename 不变）：同上
- source 文件改名（词条内容不变）：pack 输出文件名变化，App 中已安装状态
  不受影响（按 packID 识别）

修改后：

```bash
git add sources/对应文件.source.json
git commit -m "feat: update example word pack"
git push origin main
```

Actions 会自动更新：

- packVersion
- entryCount
- fileSize
- SHA-256
- catalogVersion
- generatedAt
- pack 文件

完成后：

```bash
git pull --ff-only
```

---

# 五、删除词库

删除时只删除对应 source。

例如：

```bash
git rm sources/my-new-pack.source.json
git commit -m "feat: remove example word pack"
git push origin main
```

不要手工删除：

```text
packs/my-new-pack.json
```

不要手工修改：

```text
catalog.json
```

GitHub Actions 会自动：

- 删除对应 pack
- 从 catalog 删除 descriptor
- 提高 catalogVersion
- 自动 commit 和 push

Actions 完成后：

```bash
git pull --ff-only
```

删除后：

- Raw pack URL 返回 404
- 手机刷新后不再显示该词库
- 已经下载到手机本地的旧数据是否保留，由 App 本地逻辑决定

---

# 六、source 基本格式

## 顶层结构

```json
{
  "schemaVersion": 1,
  "packID": "...",
  "packVersion": 1,
  "metadata": {},
  "entries": []
}
```

## packID

示例：

```text
com.dai1012.jlpt.n5
com.dai1012.test.basic
```

建议规则：

- 全小写
- 使用字母、数字、点和连字符
- 同一词包发布后不要随意修改
- packID 表示词包身份

## packVersion

必须为大于等于 1 的整数。

```json
"packVersion": 1
```

修改已发布词包时必须增加。

## metadata

示例：

```json
"metadata": {
  "title": "JLPT N5 日语词汇",
  "language": "ja",
  "classification": "jlpt",
  "level": "n5",
  "description": "JLPT N5 日语词汇。",
  "tags": [
    "jlpt",
    "n5",
    "vocabulary",
    "chinese"
  ]
}
```

其中：

- `title`：必填
- `language`：必填
- `classification`：必填
- `level`：可选
- `description`：可选
- `tags`：可选

不要写：

```json
"level": null
```

不需要的字段直接省略。

---

# 七、词条格式

每条词条格式：

```json
{
  "entryID": "example-001",
  "term": "確認",
  "reading": "かくにん",
  "meaning": "确认"
}
```

字段说明：

## entryID

每条词必须唯一。

要求：

- 同一个词包内不能重复
- 已发布后不要随意修改
- 修改释义时 entryID 应保持不变
- 修改顺序时 entryID 也应保持不变

示例：

```text
test-basic-001
jlpt-n5-完整SHA256
```

## entries 数组顺序与词条身份

JapaneseWordWatch 当前实际的词条身份是 `packID + entryIndex`，即词条在
entries 数组中的零基位置索引；收藏、隐藏与同步均按该位置识别词条。
entryID 仍是 pack 内稳定的业务标识（grammar 与唯一性受 schema 校验），
但不是当前收藏/隐藏/同步使用的索引身份。

因此，已发布词包的 entries 数组必须按位置保持稳定。

允许：

- 原位修改 term、reading、meaning
- 原位增加 details、watch 等非身份字段（以 App 版本支持为前提）
- 仅在数组末尾追加新词条（新 entryID 必须全包唯一）

禁止：

- 在已有词条前插入
- 删除已有词条
- 对已有词条排序或重排
- 通过去重、清洗、合并改变既有索引

未经版本化迁移，不得删除、插入或重排既有 entries；否则设备上的旧收藏
与隐藏记录会静默指向其他词条。稳定性边界的权威说明见 JapaneseWordWatch
仓库 `Models/WordID.swift` 头部注释。

## term

日语词。

不能为空。

## reading

读音。

通常写平假名。

当前脚本允许空字符串：

```json
"reading": ""
```

但不能使用只包含空格的内容。

## meaning

中文释义。

不能为空。

---

# 八、字段顺序

JSON 对象内部字段顺序不影响 App 使用。

下面两种写法等价：

```json
{
  "entryID": "test-001",
  "term": "青い",
  "reading": "あおい",
  "meaning": "蓝色的；青色的"
}
```

```json
{
  "entryID": "test-001",
  "meaning": "蓝色的；青色的",
  "reading": "あおい",
  "term": "青い"
}
```

真正重要的是：

- 字段名正确
- 字段值正确
- entries 数组顺序正确
- entryID 唯一

为了方便人工查看，建议统一顺序：

```text
entryID
term
reading
meaning
```

---

# 九、提交前本地检查

修改完成后，可以先运行：

```bash
cd /Users/xxxxxx/work/words

python3 -m json.tool sources/修改的文件.source.json >/dev/null
```

也可以运行完整生成检查：

```bash
python3 scripts/build_catalog.py --check
```

但需要注意：

如果你只修改了 source，还没有生成 pack 和 catalog，`--check` 会失败，这是正常的。

当前自动化使用方式下，平时可以只检查 JSON 语法，然后直接 push，让 Actions 生成。

如需本地完整生成：

```bash
python3 scripts/build_catalog.py
python3 scripts/build_catalog.py --check
python3 scripts/validate_release.py
```

## 高频更新的推荐工作流

日常维护按以下顺序执行，可避免绝大多数发布事故：

1. `git status` 确认工作树干净；`git pull --ff-only` 同步远端；
2. 只修改 `sources/` 下的 `.source.json`；移动 source 用 `git mv` 且保持
   basename 不变（pack 文件、下载地址与版本均不变，规则见第四章）；
   packs 与 catalog 永远交给生成脚本，不手改；
3. 用 `python3 -m json.tool <文件> >/dev/null` 校验改动文件的 JSON 语法；
4. 运行 `python3 scripts/build_catalog.py` 生成，随后 `--check` 与
   `validate_release.py` 三连验证；
5. 审查 `git status` / `git diff`：
   - 变更是否只有预期中的 source、catalog.json 和对应 pack；
   - 既有 pack 除新增文件外不应出现 M 状态（出现即身份漂移，停止检查）；
   - 排除 `.DS_Store` 及任何未知文件，不要加入提交；
6. 提交前用 `git diff --cached --name-status` 核对暂存区，只允许
   allowlist 内的文件；
7. push 后到 Actions 确认 validate-word-packs 成功、没有自动 commit、
   没有第二次触发；
8. Actions 结束后 `git pull --ff-only`，确认 working tree clean。

---

# 十、GitHub Actions 成功后的操作

Actions 自动提交后，本地分支会落后远端一个 commit。

需要执行：

```bash
git pull --ff-only
```

然后确认：

```bash
git status
```

正常结果：

```text
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

---

# 十一、Actions 失败时会怎样

如果 source 有问题，Actions 会失败。

常见原因：

- JSON 少逗号
- 括号错误
- packVersion 没提高
- entryID 重复
- packID 重复
- term 为空
- meaning 为空
- tags 格式错误
- packVersion 不是整数
- metadata 格式错误

失败后：

- 不生成新 pack
- 不更新 catalog
- 不自动 commit
- 不影响上一次成功发布的远端 pack
- 手机端继续读取上一次成功的 catalog

修正 source 后再次 push 即可。

---

# 十二、为什么修改内容必须提高 packVersion

App 通过：

```text
packID + packVersion
```

判断是否为新版本。

例如：

```text
初次发布：version 1
第一次修改：version 2
第二次修改：version 3
```

如果内容发生变化但 version 不变：

- Actions 会失败
- App 无法明确判断是否需要更新
- 新旧数据可能都显示为同一版本

因此这是必须规则。

---

# 十三、catalogVersion

`catalogVersion` 由脚本自动管理。

规则：

```text
catalog 内容没有变化
→ catalogVersion 不变

新增、修改或删除词包
→ catalogVersion 自动 +1
```

不要人工修改 catalogVersion。

---

# 十四、自动生成内容

以下内容全部由脚本计算，不需要填写：

- entryCount
- fileSize
- sha256
- fileURL
- minimumAppVersion
- catalogVersion
- generatedAt
- directoryPath（由 source 相对 `sources/` 的目录自动生成；source 文件不要手写该字段）

其中：

```text
fileURL = packs/对应文件.json
```

App 会根据 catalog 下载对应 pack。

---

# 十五、发布后的手机测试

## 新增词库

1. 等待 Actions 成功
2. 手机打开词库下载页面
3. 手动刷新
4. 确认新词库出现
5. 点击下载
6. 确认词条数量和内容

## 修改词库

1. 提高 packVersion
2. push
3. 等待 Actions 成功
4. 手机刷新
5. 确认显示新版本
6. 重新下载或执行 App 的更新操作
7. 确认新增或修改的词条生效

## 删除词库

1. 删除 source 并 push
2. 等待 Actions 成功
3. 手机刷新
4. 确认下载页面不再显示该词库

---

# 十六、日常最简操作

## 新增

```text
创建 sources/新词库.source.json
packVersion = 1
commit
push
等待 Actions
git pull --ff-only
手机刷新
```

## 修改

```text
修改 sources/现有词库.source.json
packVersion + 1
commit
push
等待 Actions
git pull --ff-only
手机刷新
```

## 删除

```text
删除 sources/现有词库.source.json
commit
push
等待 Actions
git pull --ff-only
手机刷新
```

---

# 十七、当前已验证的场景

以下流程均已真实测试通过：

## 修改词包

- 只修改 source
- 提高 packVersion
- Actions 自动生成 pack
- Actions 自动更新 catalog
- 手机端刷新后正常显示

## 新增词包

- 只新增 source
- Actions 自动新增 pack
- catalog 自动新增 descriptor
- Raw pack 返回 HTTP 200
- 没有无限循环

## 删除词包

- 只删除 source
- Actions 自动删除 pack
- catalog 自动删除 descriptor
- Raw pack 返回 HTTP 404
- 其他 pack 未变化
- 没有无限循环

## 移动词包目录

- `git mv` 移动 source，保持 basename 与 JSON 内容不变
- 既有 pack 文件逐字节不变（packID、basename、fileURL、entryID、entries
  顺序全部保持），packVersion 无需提升
- Actions 自动更新对应 descriptor 的 directoryPath 并提升 catalogVersion
- 已两次真实验证（JLPT N1–N5 归入 CN/中日，以及全量 CN 市场迁移）

## 批量新增语言方向

- 在 sources/CN/<双语目录>/ 下新增 source（如中法-Chinese-French）
- 一次 push 17 个新语言 starter 包（catalog v16，30 packs）验证通过
- 生成器幂等：本地生成后 Actions 零 diff 通过，无自动 commit、无二次触发

---

# 十八、不要做的操作

不要手工修改：

```text
packs/*.json
catalog.json
```

不要：

- 修改词包内容却忘记提高 packVersion
- 重复使用 entryID
- 修改已发布词条的 entryID
- 在既有词条前插入、删除或重排已发布词包的 entries
- 通过去重、清洗、合并改变已发布词包的既有词条索引
- 使用 force push
- 把 Personal Access Token 写入仓库
- 修改 JapaneseWordWatch 来配合普通词库更新
- 在 source 中填写 entryCount、SHA-256 或 fileSize
- 在 source 中手写 directoryPath
- 让两个 source 使用相同的 basename
- 同时手工修改 source、pack 和 catalog

---

# 十九、推荐提交信息

新增词库：

```text
feat: add JLPT N5 word pack
```

修改词库：

```text
feat: update JLPT N5 word pack
```

删除词库：

```text
feat: remove JLPT N5 word pack
```

测试：

```text
test: verify automatic pack addition
```

Actions 自动提交：

```text
chore: regenerate word pack catalog [skip ci]
```

---

# 二十、最重要的三条规则

```text
1. 平时只改 sources/*.source.json
2. 修改已发布词包时，packVersion 必须 +1
3. Actions 成功后执行 git pull --ff-only
```

---

# 二十一、公开仓库发布边界

本仓库是公开仓库，Git 历史永久公开。凡是进入 commit 的内容都应按
"任何人可见、且长期可见"来对待。

## 可以进入仓库的内容

- 可公开发布的最终词条：source 即最终形态，不放入中间产物；
- 真实、明确的来源说明：原创内容如实声明原创；使用第三方数据时写明
  来源与许可证，并在 source 同目录放置 license / attribution 文件；
- 公开的标音/转写方法名称引用（方法正文受版权保护时不复制其内容）。

## 禁止进入仓库的内容

- 私有原始数据、采集方法、清洗方法或内部加工记录；
- AI prompt 或任何内部审核笔记；
- 账号、Token、Cookie、密码等任何凭据；
- 私有 URL 或不可公开的第三方原始内容；
- `.DS_Store` 等本地系统文件。

## 处理原则

- 来源或许可不确定时停止并核实，不要猜测；
- 不伪造词源、版权或机构授权；
- attribution 只写真实、必要的信息，不声称不存在的第三方授权；
- 一旦误提交敏感信息，注意历史无法简单抹除，应立即按泄露处理。

---

# 二十二、多市场扩展与目录规划

## 市场语义

顶层目录 `CN/`、`JP/`、`EN/` 表示用户市场与产品入口，不表示词条语言。
同一目标语言可以服务多个市场。市场之下按学习方向分目录（如中日、
中英），需要时再按场景细分一层，即"市场 → 语言方向 → 场景"。

## 当前状态

- CN 市场已建成上线（19 个语言方向）；
- JP、EN 尚未建设。未来将复用同一套
  source → build_catalog.py → packs/catalog → validate_release.py →
  GitHub Actions 流程，不需要新增工具链。

## 目录命名约定

- 新增方向目录使用双语命名：`中文名-English Name`，
  如 `中法-Chinese-French`、`中俄-Chinese-Russian`，
  便于非中文背景的维护者识别；
- 旧短名目录（中日、中英、中韩、中西）暂时保留原样，本次不移动。

## 后续整理计划（记录在案，尚未执行）

- 将旧短名方向目录统一迁移为双语命名；
- 迁移时必须遵守既有稳定性规则：packID、basename、fileURL、entryID
  与 entries 顺序全部保持不变，参照第十七章"移动词包目录"的已验证流程；
  迁移本身只更新 descriptor 的 directoryPath 并提升 catalogVersion；
- directoryPath 变化只影响 App 下载页导航，但批量调整前仍需做一次
  App 端 UX 审查，确认层级展示与排序符合预期。
