# wechat-cli 重构优先级清单

说明：当前仓库已经收口为 Python 3.14 only + GitHub Release 的发布链路。下面按“已完成 / 待继续”维护，方便后续继续推进时快速定位。

## P0 已完成

- [x] 修复 `members --format text` 的运行时错误，并补回归测试。
- [x] 让多聊天 `search` 明确返回“聊天存在但没有消息表”的失败信息。
- [x] 收紧 `stats` 和消息聚合路径里的吞异常逻辑，让坏库/坏表不再表现为“成功但为空”。
- [x] 统一 `sessions`、`unread`、`contacts`、`favorites`、`history`、`search`、`stats`、`members`、`session-updates` 的 JSON 返回结构。

## P1 已完成

- [x] 去掉 `core.contacts` 的模块级全局缓存，将联系人和自账号缓存收敛到 `DBCache` 实例。
- [x] 抽取 `session.db` 公共访问层，把 `sessions` / `unread` / `new-messages` 的重复逻辑下沉到 `core/session_data.py`。
- [x] 拆分 `contacts` / `messages` / `favorites` 的 repository/query 边界，让命令层只保留参数处理、错误输出和结果编排。
- [x] 明确 `new-messages` 的定位：它现在是 `session-updates` 的兼容别名，语义是“基于 session.db 的会话级更新流”。
- [x] 梳理 `--media` 路径解析边界，区分精确路径、候选路径、候选目录和缩略图回退，并补回归测试。

## P2 已完成

- [x] 避免 `dist/` 中旧 wheel / sdist 污染新的 release 构建。
  说明：`scripts/build_release_artifacts.py` 现在先在临时目录构建，再只同步当前版本产物到目标输出目录，清理旧发布产物但保留无关文件。
- [x] 补 `init` / `export` / `history` / `unread` 命令层回归测试。
  说明：新增覆盖退出码、标准 JSON 结构、文件输出路径，以及初始化错误提示等壳层行为。
- [x] 对齐 CI `compileall` 范围。
  说明：`.github/workflows/ci.yml` 现在与本地和 `scripts/prepare_release.py` 一致，统一检查 `wechat_cli`、`tests`、`scripts`。

## P3 已完成

- [x] 清理历史残留与死代码。
  说明：根目录 `entry.py` 已删除，CLI 入口明确固定为 `pyproject.toml` 中的 `wechat_cli.main:cli`；`wechat_cli/core/messages_repo.py` 中未使用的旧辅助函数也已移除，并补了元数据回归校验。

## P4 仍继续

- [x] 审核并收紧 `messages.py` / `db_cache.py` 中过宽的异常吞噬路径。
  说明：`messages.py` 现在只吞预期的数据库/媒体解析异常，避免把编程错误静默吃掉；`db_cache.py` 的临时文件清理改成 `finally` 路径，不再依赖 `except Exception` 做清理。
- [ ] 继续补命令壳层测试。
  说明：`export` 异常分支和 `history` 文本模式已补上；后续可继续覆盖帮助文本，以及其它用户可见错误提示。

## 发布前检查

1. `py -3.14 -m unittest discover -s tests -v`
2. `py -3.14 -m compileall wechat_cli tests scripts`
3. `py -3.14 scripts/package_smoke.py`
4. `py -3.14 scripts/check_release_tag.py --print-expected-tag`
