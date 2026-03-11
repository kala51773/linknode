# Commit / PR 提交流程约定

为保证 WickHunter 的迭代可追踪性，建议按以下规范提交。

## 1) 本地 Git 基础配置

```bash
git config user.name "<your-name>"
git config user.email "<your-email>"
```

## 2) 提交信息格式

采用简洁前缀 + 动词短语：

```text
<scope>: <imperative summary>
```

示例：

- `execution: support side-aware hedge direction`
- `backtest: add jsonl replay loader`
- `risk: add cooldown auto-reset checks`

## 3) 每次提交建议内容

- 仅包含一个逻辑改动主题（便于回滚与定位）。
- 至少包含一项可运行验证（单元测试或命令行检查）。
- 在 PR 描述中写明：
  - 动机（Why）
  - 改动（What）
  - 验证（Testing）

## 4) 推荐提交流程

```bash
git status
git add <files>
git commit -m "<scope>: <summary>"
git show --stat --oneline HEAD
```

## 5) 推送与远程

如仓库未配置远程：

```bash
git remote add origin <repo-url>
git push -u origin <branch>
```

如已配置远程：

```bash
git push
```
