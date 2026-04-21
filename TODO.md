# wechat-cli 重构优先级清单

这份清单按 `P0` 到 `P3` 排序，优先处理会影响可用性、正确性和后续维护成本的问题。

说明：当前仓库已经收口为纯 Python CLI 与打包链路。

## P0 先稳住 CLI 可用性

- [x] 修复 `members --format text` 的运行时错误。
  文本输出分支已经补齐成员变量访问和展示逻辑，并有回归测试覆盖。
- [x] 让多聊天 `search` 明确反馈“聊天存在但没有消息表”。
  现在会把 `missing_tables` 转成可见失败信息返回给用户，而不是静默丢失部分结果。
- [x] 收紧 `stats` 和消息聚合路径里的“吞异常”逻辑。
  `stats` 已经开始返回 `failures`，让坏库、坏表、坏路径不再表现成“成功但为空”。
- [x] 为核心只读命令补最小回归测试。
  当前已经有 `commands`、`contacts`、`session_data`、输出编码等基础测试，能兜住这批回归。

## P1 整理共享状态和重复逻辑

- [x] 去掉 `core.contacts` 的模块级全局缓存。
  联系人和自身账号缓存已经下沉到 `DBCache` 实例状态，避免多账号/多测试实例串数据。
- [x] 抽取 `session.db` 共享访问层。
  `sessions`、`unread`、`new-messages` 的重复 `session.db` 查询与基础格式化逻辑已经集中到 `wechat_cli/core/session_data.py`。
- [x] 为 `contacts`、`messages`、`favorites` 建立更清晰的 repository/query 边界。
  目前 `contacts_repo`、`messages_repo`、`favorites_repo` 已承接 SQL 和 DB 路径解析，`commands/` 侧只保留参数、错误处理和输出编排。
- [x] 统一命令返回结构和失败模型。
  已新增共享 `command_result` 包装层，`sessions`、`unread`、`contacts`、`favorites`、`history`、`search`、`stats`、`members`、`new-messages` 的 JSON 输出现在统一包含 `scope`、`count`、`failures`，分页命令统一包含 `offset/limit`。

## P2 提升缓存可靠性、性能和行为定义

- [x] 重构 `DBCache` 的缓存命名和生命周期管理。
  当前缓存已按绝对 `db_dir` 命名空间隔离，持久化索引支持多账号并存，并补了命名空间清理、复用和并发访问回归保护。
- [x] 评估解密后数据库的保留期限、清理策略或显式 opt-in 持久化机制。
  当前默认采用 24 小时 TTL 清理策略，并支持通过 `persist_decrypted_cache=true` 显式启用长期持久化；`decrypted_cache_ttl_hours` 可调整缓存保留时长。
- [x] 优化消息库发现与搜索流程，减少重复扫描所有 `message_*.db` 的成本。
  当前已把 `message_*.db` 的表发现和 `Name2Id` 解析收敛为按缓存实例隔离的元数据缓存，单聊/多聊上下文解析与全局搜索都会复用这层索引；同时按数据库版本令牌自动失效，避免库更新后继续复用旧扫描结果。
- [x] 梳理媒体路径解析策略，明确“精确定位”和“启发式猜测”的边界。
  当前 `--media` 已显式区分精确路径、候选路径、候选目录和视频缩略图回退；文件消息保留精确命中与文件名启发式匹配的差异，图片/语音/视频不再伪装成“精确文件路径”，并补了多目录歧义、缩略图回退等回归测试。
- [x] 重新定义 `new-messages` 的语义。
  现已显式定义为“基于 `session.db` 的会话级更新流”，并新增推荐命令 `session-updates`；`new-messages` 保留为兼容别名，JSON 结果也增加了 `stream_type`、`tracked_by`、`snapshot_kind` 来消除歧义。

## P3 补工程化和 Python 发布链路

- [x] 对齐 Python 发布元数据。
  当前已把 Python CLI 版本收敛到 `wechat_cli.__version__`，并新增 `scripts/check_release_metadata.py` 仅校验 `pyproject.toml` 与运行时版本是否一致；`package_smoke` 也会先跑这层校验，避免发布前版本漂移。
- [x] 增加 Python-only 基础 CI。
  当前 GitHub Actions 已覆盖跨平台 `compileall`、`unittest`，以及基于 `python -m build` 的打包 smoke check。
- [x] 补开发者文档。
  当前 `docs/development.md` 已从 README 链出，覆盖项目分层、数据库目录约定、缓存目录/TTL、Python-only 发布流程和已知兼容性边界。
- [x] 补 Python-only 发布辅助脚本。
  当前已新增 `scripts/prepare_release.py`，可把 `unittest`、`compileall` 与最终 `package_smoke` 串成单入口，并支持 `--skip-*` 与 `--dry-run`。
- [x] 清理历史发布残留。
  旧的多平台 wrapper、平台包 manifest 与校验脚本已经从仓库中移除，避免文档、测试、CI 和源码包再次误接回旧发布链路。
- [x] 补版本更新辅助脚本。
  当前已新增 `scripts/bump_version.py`，可同步更新 `pyproject.toml` 与 `wechat_cli.__version__`，并支持 `--dry-run`、`--print-current` 与 `--allow-misaligned`。
- [x] 补目标环境安装 smoke。
  当前 `scripts/package_smoke.py` 已在构建后自动创建临时虚拟环境，分别安装 wheel / sdist，并校验 `wechat-cli` 入口和模块导入可用，避免“能 build 但装完跑不起来”的回归。

## 建议执行顺序

1. 先考虑更细的发布产物校验，例如 GitHub Release 资产、哈希或多 Python 版本安装验证。
2. 然后再考虑更完整的 Python 发布编排，例如 changelog、tag 和 release 说明的自动化串联。
3. 最后再视实际维护成本决定是否把本地发布辅助脚本和 CI 做更紧密的统一编排。
