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

- [x] 对齐 Python 包、npm 主包和各平台包版本号。
  当前已把 Python CLI 版本收敛到 `wechat_cli.__version__`，并新增 `scripts/check_release_metadata.py` 校验 `pyproject.toml`、npm 主包、平台包和可选依赖版本是否一致；`package_smoke` 也会先跑这层校验，避免发布前版本漂移。
- [x] 修正 npm wrapper 里的错误提示与包名文案。
  当前 npm wrapper 已共享 `package-metadata.json` 中的主包名与平台包映射，`install.js` 和 `bin/wechat-cli.js` 的错误提示会明确指向真实发布包 `@canghe_ai/wechat-cli`，README 里的 npm 安装命令也已改成显式包名。
- [x] 增加基础 CI。
  当前已新增 GitHub Actions 工作流，覆盖跨平台 `compileall`、`unittest`，以及基于 `python -m build` + `npm pack` 的打包 smoke check；同时补了本地可复用的 `scripts/package_smoke.py` 入口，方便在发布前手动复跑。
- [x] 补开发者文档。
  当前已新增 `docs/development.md` 并从 README 链出，覆盖项目分层、数据库目录约定、缓存目录/TTL、发布流程和已知兼容性边界。
- [x] 补平台包内容校验。
  当前已新增 `scripts/check_platform_packages.py`，并把 `package_smoke` 接到这层校验上；开发态默认校验 `os/cpu/files` 等 manifest 约定，发布态可通过 `--require-platform-binaries` 或现有 `bin/` 产物自动切换到严格模式，进一步校验 `npm/platforms/*/bin/` 和最终 tarball 内容。
- [ ] 补发布辅助脚本。
  当前发布仍需要人工串联改版本、运行 `npm/scripts/build.py`、再跑 `package_smoke --require-platform-binaries`，可以考虑补一个单入口脚本收敛这条链路。

## 建议执行顺序

1. 优先补发布辅助脚本，把版本校验、平台构建和严格 smoke 串成单入口。
2. 然后根据发布体验决定是否补充更细的构建/发布检查，例如平台包内容清单或二进制元数据校验。
3. 最后再按实际发布流程补充自动化发布或版本变更辅助脚本。
