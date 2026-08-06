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
│   └── *.source.json
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
sources/jlpt-n5.source.json
sources/test-basic.source.json
```

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
- 使用 force push
- 把 Personal Access Token 写入仓库
- 修改 JapaneseWordWatch 来配合普通词库更新
- 在 source 中填写 entryCount、SHA-256 或 fileSize
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
