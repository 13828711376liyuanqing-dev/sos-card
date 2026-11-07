# CLAUDE.md

项目规范、目录结构、编译与验证要求见同目录 [AGENTS.md](AGENTS.md)，以其为准；本文件只补充与本工具相关的硬约束。

## 版本控制边界（用户 2026-11-02 指定，覆盖 2026-10-29 "允许只读 Git" 的旧规则）

只能处理普通文件。Git 和 SVN 一律不碰：

1. **不得执行任何 Git 命令**，包括只读的 `status`、`diff`、`log`、`show`、`blame`、`ls-files`、`rev-parse`；也不用 `gh`、TortoiseGit、gitk 等 Git 工具。
2. **不得读取、搜索或修改任何 `.git` 目录及其内容**；搜索和对比文件时必须排除 `.git`。`.gitignore` 这类普通文件可以读写。
3. **不得通过脚本、IDE、插件或其他工具间接操作 Git**，不得调用任何自动提交、同步或推送功能。
4. **SVN 同样**：不执行任何 svn 命令（含 TortoiseSVN），不访问 `.svn` 目录和 SVN 认证缓存（`%APPDATA%\Subversion`）；`D:\SVN` 下只做普通文件的读、改、复制。
5. 可以读取、修改、复制、备份普通文件，可以用普通文件对比工具核对差异。**需要历史版本时，查找本地备份（`D:\CODEX\_archive` 等）；找不到就告诉用户，由用户或 Codex 查 Git。**
6. 提交、回滚、建分支、SVN 提交一律交给用户或 Codex：完成一轮修改后报告改了哪些文件、如何验证、哪些仍需实板验证，并给出建议的提交信息；不要尝试代做，也不要请求放宽权限。
7. 不修改 Git 或 SVN 自身的任何配置。

以上已在 `.claude/settings.json` 中硬拦截：`permissions.deny`（命令与 `.git`/`.svn`/Subversion 路径），以及 PreToolUse 钩子 `.claude/hooks/block_svn.py`（检查 Bash/PowerShell/Read/Edit/Write/Grep/Glob 的命令和路径，解析失败或超时一律拒绝）。

该边界只约束版本控制，不约束编译与文件编辑；构建产物与源码修改照常进行。
