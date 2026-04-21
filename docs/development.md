# 开发者文档

这份文档记录当前 `wechat-cli` 的维护约定，重点覆盖分层边界、目录/缓存约定、发布流程和已知兼容性边界。它的目标不是替代用户向 README，而是帮助后续重构时尽量沿用这一轮已经收敛下来的边界。

说明：当前仓库只维护 Python CLI 与 Python 打包链路。

## 设计目标

- CLI 入口层只负责参数解析、错误码和输出格式，不直接拼 SQL。
- `core/` 的查询服务层负责跨库编排、缓存复用、结构化结果和文本格式化。
- `*_repo.py` 只负责数据库路径解析和原始 SQL 访问，避免把 Click、stdout、缓存状态混进去。
- 共享状态应挂在 `AppContext` 或 `DBCache` 实例上，避免模块级全局缓存污染多账号或测试场景。
- 命令 JSON 返回尽量统一到 `scope`、`count`、`failures` 这组公共字段。

## 项目分层

### CLI 与输出

- `wechat_cli/main.py`
  注册 Click 命令，创建 `AppContext`，并把 `--config` / `WECHAT_CLI_CONFIG` 透传给配置层。
- `wechat_cli/commands/`
  每个命令文件只处理参数校验、退出码、调用服务层和输出编排。
- `wechat_cli/output/formatter.py`
  统一 JSON / text 输出，以及 Windows 控制台 UTF-8 兼容处理。

### 运行时上下文与共享状态

- `wechat_cli/core/config.py`
  负责加载 `config.json`、自动探测 `db_dir`、规范化相对路径、补默认配置。
- `wechat_cli/core/context.py`
  每次 CLI 调用初始化一次 `AppContext`，持有配置、密钥、`DBCache` 和消息库索引入口。
- `wechat_cli/core/db_cache.py`
  负责 SQLCipher 数据库的惰性解密、WAL 合并、跨进程缓存复用、TTL 清理和多账号命名空间隔离。

### 查询/服务层

- `wechat_cli/core/messages.py`
  负责消息库发现、聊天上下文解析、历史记录/搜索/统计、媒体路径解析。
- `wechat_cli/core/session_data.py`
  集中处理 `session.db` 查询，供 `sessions`、`unread`、`session-updates` 复用。
- `wechat_cli/core/session_updates.py`
  基于 `session.db` 做“会话级增量更新”，并维护 `last_check.json` 状态。
- `wechat_cli/core/contacts.py`
  负责联系人名称映射、详情、群成员和 self username 解析。
- `wechat_cli/core/favorites.py`
  负责收藏查询与 XML 内容摘要格式化。
- `wechat_cli/core/command_result.py`
  统一集合类命令的返回结构。

### Repository 层

- `wechat_cli/core/messages_repo.py`
  负责 `message_*.db` 的原始 SQL 访问、Name2Id 读取、分表索引和统计查询。
- `wechat_cli/core/contacts_repo.py`
  负责 `contact.db` 路径解析和联系人相关 SQL。
- `wechat_cli/core/favorites_repo.py`
  负责 `favorite.db` 路径解析和收藏查询 SQL。

维护时尽量保持一个简单规则:

- `commands/` 不直接 `sqlite3.connect(...)`
- `*_repo.py` 不直接依赖 Click 或输出格式
- 需要组合多个 repo 或缓存时，优先放回 `core/*.py`

## 运行时目录约定

### 状态目录

默认状态目录是 `~/.wechat-cli/`，主要文件如下:

- `config.json`
  主配置文件。`init` 当前至少会写入 `db_dir`。
- `all_keys.json`
  `init` 提取出的数据库密钥。
- `last_check.json`
  `session-updates` / `new-messages` 的上次游标状态。
- `decrypted/`
  预留的“预解密库覆盖目录”。当前 `contact.db` 和 `favorite.db` 会优先读取这里的库文件。
- `decoded_images/`
  仍会由配置层补默认值，但当前主查询链路未实际使用，属于兼容保留字段。

### 配置字段

`load_config()` 会把相对路径统一解释为“相对于配置文件所在目录”，因此下面这些字段都可以写相对路径:

- `db_dir`
- `keys_file`
- `decrypted_dir`
- `decoded_image_dir`

当前和缓存行为相关的两个关键配置:

- `persist_decrypted_cache`
  默认 `false`。为 `true` 时，`DBCache` 不做 TTL 过期清理，解密后的缓存文件可以长期复用。
- `decrypted_cache_ttl_hours`
  默认 `24`。当 `persist_decrypted_cache` 为 `false` 时，控制解密缓存的保留时长。

一个典型配置大致如下:

```json
{
  "db_dir": "C:/Users/<you>/.../db_storage",
  "persist_decrypted_cache": false,
  "decrypted_cache_ttl_hours": 24
}
```

## 微信数据目录约定

当前代码默认 `config["db_dir"]` 指向某个账号目录下的 `db_storage`。如果路径最后一级名为 `db_storage`，配置层会自动推导:

- `wechat_base_dir = dirname(db_dir)`

这样服务层就能把数据库目录和媒体目录关联起来。当前默认约定如下:

- `<wechat_base_dir>/db_storage/contact/contact.db`
- `<wechat_base_dir>/db_storage/favorite/favorite.db`
- `<wechat_base_dir>/db_storage/session/session.db`
- `<wechat_base_dir>/db_storage/message/message_*.db`
- `<wechat_base_dir>/msg/...`

媒体路径解析现在依赖 `msg/` 的现有布局:

- 文件消息优先尝试 `msg/file/YYYY-MM/<title>`
- 图片/语音/视频优先尝试 `msg/attach/<bucket>/YYYY-MM/<Img|Voice|Video>`
- 视频在无法定位原文件时，会回退到 `msg/video/YYYY-MM/*_thumb.jpg`

这里有一个需要维护时牢记的边界:

- 文件消息可以返回 `exact_file` 或 `candidate_file`
- 图片/语音/视频通常只能返回候选目录或缩略图，不应伪装成“精确文件路径”

## 缓存与查询边界

### `AppContext`

`AppContext` 每次 CLI 调用只创建一次，负责:

- 加载配置和密钥
- 创建 `DBCache`
- 发现消息库键列表 `msg_db_keys`
- 暴露 `display_name_fn()` 给各命令复用

### `DBCache`

`DBCache` 当前是运行时共享状态的核心:

- 以绝对 `db_dir` 的哈希做命名空间，避免多账号缓存串用
- 对每个相对库路径生成稳定缓存文件名
- 解密后会尝试把 `-wal` 内容 patch 回 SQLite 文件
- 通过 `tempfile.gettempdir()/wechat_cli_cache` 做跨进程复用
- 通过 `_index.json` 记录命名空间、源库 mtime 和缓存路径
- 通过 `.lock` 文件规避并发重复解密

注意:

- `decrypted_dir` 不是当前主缓存目录
- 当前真正的解密缓存目录是系统临时目录下的 `wechat_cli_cache`
- `contacts` / `favorites` 读取 `decrypted_dir` 只是一种“显式覆盖入口”

### 联系人缓存

`contacts.py` 不再使用模块级全局缓存，而是把状态挂在 `cache._contacts_state` 上:

- `datasets`
  以绝对 `decrypted_dir` 为 key，缓存联系人名称和完整联系人列表
- `self_usernames`
  以绝对 `db_dir` 为 key，缓存当前账号的 self username 推断结果

### 消息库索引缓存

`messages.py` 会把消息库索引挂到 `cache._messages_state["db_indexes"]`:

- key 是相对数据库键，比如 `message/message_1.db`
- value 会记录 `db_path`、`version_token`、消息表列表、`Name2Id` 推导结果和 `MAX(create_time)` 缓存

失效策略依赖 `DBCache.describe()` 返回的 `version_token`，也就是源 `.db` / `-wal` 的 mtime 组合；因此消息库更新后会自动放弃旧索引。

### 会话更新语义

`session-updates` 的语义已经固定为:

- 基于 `session.db`
- 返回的是“会话级更新流”
- 不是逐条新消息流

`new-messages` 仍保留为隐藏兼容别名，但新的实现和文档都应优先使用 `session-updates` 这个名字。

### 命令返回结构

集合类命令优先使用 `build_collection_result()`，返回结构保持以下公共字段:

- `scope`
- `count`
- `failures`
- `limit` / `offset`（适用时）

如果新增命令，也建议尽量沿用这个模型，避免同一 CLI 内部出现多套 JSON 包装风格。

## 本地开发与验证

常用的本地检查命令:

```bash
python -m unittest discover -s tests -v
python -m compileall wechat_cli tests scripts
python scripts/check_release_metadata.py
python scripts/package_smoke.py
python scripts/prepare_release.py --dry-run
```

说明:

- `unittest`
  负责覆盖命令返回、缓存、配置、消息格式化和发布元数据校验。
- `compileall`
  主要用于快速发现语法错误和导入级问题。
- `check_release_metadata.py`
  校验 `pyproject.toml` 与 `wechat_cli.__version__` 是否一致。
- `bump_version.py`
  同步更新 `pyproject.toml` 与 `wechat_cli.__version__`，支持 `--dry-run`、`--print-current` 和在必要时用 `--allow-misaligned` 修复漂移。
- `package_smoke.py`
  先跑 release metadata 校验，再执行 `python -m build`，校验 wheel / sdist 文件名与关键归档内容，打印 SHA256，随后在临时虚拟环境里分别安装 wheel / sdist，并确认 `wechat-cli` 入口与模块导入都可用。
- `prepare_release.py`
  把 `unittest`、`compileall` 和 `package_smoke` 串成单入口；支持 `--skip-tests`、`--skip-compileall`、`--skip-package-smoke` 与 `--dry-run`。

## 发布流程

当前发布流程已经收口为“版本同步脚本 + 本地脚本校验”，低风险且便于在 fork 中持续维护。

### 1. 修改版本号

优先使用版本同步脚本:

```bash
python scripts/bump_version.py 0.2.5
```

这条命令会同步更新:

- `pyproject.toml`
- `wechat_cli/__init__.py`

如果你只是想先看当前版本:

```bash
python scripts/bump_version.py --print-current
```

如果当前两个版本已经漂移，但你想强制收敛回来:

```bash
python scripts/bump_version.py 0.2.5 --allow-misaligned
```

### 2. 运行校验

按下面顺序执行最稳妥:

```bash
python -m unittest discover -s tests -v
python -m compileall wechat_cli tests scripts
python scripts/package_smoke.py
```

`package_smoke.py` 内部已经会调用 `check_release_metadata.py`，并继续做“构建 + 产物内容/sha256 校验 + 目标环境安装 smoke”，所以通常不需要单独重复跑一次 metadata 校验，除非你只想快速验证版本一致性。

### 3. 推荐单入口

现在更推荐先用发布辅助脚本串起整条链路:

```bash
python scripts/prepare_release.py
```

这条命令会依次执行:

- `python -m unittest discover -s tests -v`
- `python -m compileall wechat_cli tests scripts`
- `python scripts/package_smoke.py`

如果你只是想先看计划，不实际执行:

```bash
python scripts/prepare_release.py --dry-run
```

如果你想临时跳过某一步，也可以按需使用:

```bash
python scripts/prepare_release.py --skip-tests
python scripts/prepare_release.py --skip-compileall
python scripts/prepare_release.py --skip-package-smoke
```

### 4. 发布前手动确认

- README、开发文档和 CI 仍然保持 Python-only 安装/发布口径。
- 如需手动产出发布物，可额外执行 `python -m build`，再在目标环境里试装 sdist / wheel。
- 当前 `package_smoke.py` 已包含发布产物内容校验：它会检查 wheel / sdist 文件名、关键归档成员，并打印每个产物的 SHA256。
- 当前 `package_smoke.py` 也包含目标环境安装 smoke：它会在临时虚拟环境中安装 wheel / sdist，并校验 `wechat-cli --version`、`wechat-cli --help` 与模块导入。
- GitHub Actions 当前会在 Python `3.14` 上执行 package smoke，确保唯一受支持版本的打包与安装链路可用。
- 如果你还想进一步提高发布把关强度，可以再加一层更贴近真实用户环境的 smoke，例如 GitHub Release 资产校验或更多 Python 版本矩阵。

## 已知兼容性边界

- README 里的系统要求和平台支持仍是对外口径，尤其是 macOS / 微信版本边界。
- `init` 的密钥提取依赖对微信进程内存的读取能力。macOS / Linux 常常需要 `sudo`，Windows 也通常需要足够权限的终端。
- `contacts` 和 `favorites` 可以读取 `decrypted_dir` 下的预解密库；`messages` 和 `session.db` 仍主要走 `DBCache` 的惰性解密路径。
- `decoded_image_dir` 当前只是配置兼容字段，不要假设它已经接入现有查询链路。
- `session-updates` 的结果只由 `session.db` 驱动，不保证和“所有消息库中的逐条新消息”完全等价。
- 媒体路径解析对图片/语音/视频仍带启发式特征，维护时如果新增字段或状态，要先分清“精确命中”和“候选路径”。

## 后续重构建议

如果继续沿 TODO 往下做，比较自然的顺序是:

1. 版本同步脚本现在已经补齐；如果后续还要继续减少手工步骤，可以再考虑把 changelog / Git tag / GitHub Release 资产检查串进同一条发布辅助链路。
2. 如果未来还想继续收紧发布校验，可以补更细的发布产物检查，例如 GitHub Release 资产或更多 Python 版本矩阵。
3. 后续只要继续拆边界，优先沿用“命令层 -> 服务层 -> repo 层”的结构，不要把 SQL 和 Click 再重新耦合回去。
