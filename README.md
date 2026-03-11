# Project WickHunter

**动态单边 Stub Quote + 小盘先成交 + 大盘即时对冲** 的事件驱动量化系统。

## 关键决定

- 第一阶段交易所：**Binance USDⓈ-M Futures**
- 第二阶段交易所：**OKX Perpetual Swap**（可选保留 Bybit 作为第三适配器）
- 研究/回放/仿真框架：**Nautilus Trader**（你要求“应该选 Nautilus Trade”，此处按主流项目名称采用 Nautilus Trader）

## 本仓库当前内容

- `docs/wickhunter_prd.md`：完整 PRD、模块拆解、状态机、风险与开发里程碑。
- `反转链表.cpp`：历史示例文件（与 WickHunter 主体无关）。

## 下一步

1. 按 `docs/wickhunter_prd.md` 的 M0-M3 里程碑搭建代码骨架。
2. 先完成 Binance 行情与订单簿拼接，再接入 stub quote 状态机。
3. 接入 Nautilus Trader 回放和事件驱动仿真，先回放后模拟再小额实盘。

## 已开始开发（M0 骨架）

已新增最小可运行 Python 项目骨架：

- `pyproject.toml`：项目打包配置。
- `src/wickhunter/common/config.py`：基础运行配置与风控限制。
- `src/wickhunter/strategy/state_machine.py`：显式策略状态机与合法迁移约束。
- `src/wickhunter/strategy/quote_engine.py`：根据 fair price 生成 q1/q2/q3 报价层。
- `src/wickhunter/strategy/signal_engine.py`：联通订单簿同步、盘口指标与报价计划生成。
- `src/wickhunter/core/mature_engine.py`：成熟交易内核适配层（当前默认 Nautilus Trader 适配器）。
- `src/wickhunter/core/orchestrator.py`：将信号与执行结果提交到成熟内核后端。
- `src/wickhunter/exchange/binance_futures.py`：Binance USDⓈ-M 深度事件标准化解析器与客户端骨架。
- `src/wickhunter/exchange/bridge.py`：交易所标准化消息到 SignalEngine 的桥接层。
- `src/wickhunter/backtest/replay.py`：事件驱动回放器（M3 研究回放核心）。
- `src/wickhunter/simulation/hedge_latency.py`：对冲延迟与滑点仿真模型（M3）。
- `src/wickhunter/analytics/report.py`：事件级 PnL 与延迟/滑点报表汇总。
- `src/wickhunter/portfolio/position.py`：持仓、均价与组合名义敞口跟踪。
- `src/wickhunter/runtime.py`：运行时管线（交易所桥接 + 编排 + 组合持仓 + 停机保护）。
- `src/wickhunter/cli/main.py`：开发期 CLI 入口（`--demo` / `--book-demo` / `--sync-demo` / `--quote-demo` / `--signal-demo` / `--mature-demo` / `--exchange-demo` / `--exchange-signal-demo` / `--m3-demo` / `--bridge-demo` / `--portfolio-demo` / `--runtime-demo` / `--exec-demo` / `--cancel-demo`）。
- `src/wickhunter/marketdata/orderbook.py`：本地订单簿快照+增量同步与序列连续性校验。
- `src/wickhunter/marketdata/synchronizer.py`：快照到达前缓存增量并在快照后重放拼接。
- `src/wickhunter/execution/engine.py`：B 成交事件经过风控校验后生成 A 对冲订单。
- `src/wickhunter/execution/throttle.py`：撤单节流与最小存活时间保护。
- `src/wickhunter/risk/checks.py`：运行时风控检查（每日亏损、事件数、裸腿暴露）。
- `tests/`：状态机与 CLI 的基础单元测试。

本地运行示例：

```bash
PYTHONPATH=src python -m wickhunter.cli.main --demo
PYTHONPATH=src python -m wickhunter.cli.main --book-demo
PYTHONPATH=src python -m wickhunter.cli.main --sync-demo
PYTHONPATH=src python -m wickhunter.cli.main --quote-demo
PYTHONPATH=src python -m wickhunter.cli.main --signal-demo
PYTHONPATH=src python -m wickhunter.cli.main --mature-demo
PYTHONPATH=src python -m wickhunter.cli.main --exchange-demo
PYTHONPATH=src python -m wickhunter.cli.main --exchange-signal-demo
PYTHONPATH=src python -m wickhunter.cli.main --m3-demo
PYTHONPATH=src python -m wickhunter.cli.main --replay-file data/sample_events.jsonl
PYTHONPATH=src python -m wickhunter.cli.main --backtest-file data/sample_fills.jsonl
PYTHONPATH=src python -m wickhunter.cli.main --backtest-file data/sample_fills.jsonl --backtest-lenient
PYTHONPATH=src python -m wickhunter.cli.main --download-l2-snapshot BTCUSDT --snapshot-out data/l2_snapshot.jsonl
PYTHONPATH=src python -m wickhunter.cli.main --download-l2-snapshot BTCUSDT --snapshot-out data/l2_snapshot.jsonl --l2-base-url https://fapi.binance.com
PYTHONPATH=src python -m wickhunter.cli.main --convert-depth-jsonl data/raw_depth.jsonl --convert-out data/replay_depth.jsonl --convert-lenient
PYTHONPATH=src python -m wickhunter.cli.main --bridge-demo
PYTHONPATH=src python -m wickhunter.cli.main --portfolio-demo
PYTHONPATH=src python -m wickhunter.cli.main --runtime-demo
PYTHONPATH=src python -m wickhunter.cli.main --exec-demo
PYTHONPATH=src python -m wickhunter.cli.main --cancel-demo
PYTHONPATH=src python -m unittest discover -s tests -v
python -m unittest discover -s tests -v
```

说明：仓库根目录新增 `sitecustomize.py`，在本地直接执行 `python -m unittest ...` 时会自动把 `src/` 注入 `sys.path`，从而减少环境变量配置成本。

提交规范见 `docs/commit_conventions.md`（包含 commit message 建议、PR 内容模板与远程推送步骤）。

说明：`--download-l2-snapshot` 默认会优先使用 `--l2-base-url`，并自动回退尝试 `fapi1/fapi2/fapi3` 域名。
