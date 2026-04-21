# wechat-cli 重构优先级清单

这份清单按 `P0` 到 `P3` 排序，优先处理会影响可用性、正确性和后续维护成本的问题。

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

## P3 补工程化和发布链路

- [ ] 对齐 Python 包、npm 主包和各平台包版本号。
  需要避免发布链路里的版本漂移，让安装和排障信息保持一致。
- [ ] 修正 npm wrapper 里的错误提示与包名文案。
  安装失败时给出的提示应该准确反映真实发布包名，减少用户排障摩擦。
- [ ] 增加基础 CI。
  最低建议包含依赖安装、`compileall`、单元测试，以及打包 smoke check。
- [ ] 补开发者文档。
  建议覆盖项目分层、数据库目录约定、缓存目录、发布流程和已知兼容性边界。

## 建议执行顺序

1. 优先补齐 `P3` 的基础 CI，把 `compileall`、单测和打包 smoke check 固化下来。
2. 然后处理版本对齐与 npm wrapper 文案，减少发布链路里的版本漂移和排障摩擦。
3. 最后补开发者文档，沉淀当前分层、缓存与发布流程约定。
