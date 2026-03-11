# Project WickHunter PRD（V1）

## 1. 项目目标

捕捉小盘标的 B 在单一 venue 的局部“下插针”，并在 B 被动成交后立即用高流动性领导标的 A 进行对冲，仅交易 B 相对 A/外部 fair value 的瞬时残差回归。

---

## 2. 非目标

V1 不做跨交易所搬砖、不做超低延迟撮合级优化、不做海量标的并发、不做自动参数在线自适应。

---

## 3. 技术选型

### 3.1 交易所适配顺序

1. **Binance USDⓈ-M Futures**（优先）
2. **OKX Perpetual Swap**（第二阶段）
3. **Bybit Linear Perps**（第三阶段，可选）

### 3.2 回测/仿真引擎

- 采用 **Nautilus Trader** 做事件驱动回放与仿真（按“先研究回放 → 再仿真 → 再小额实盘”流程）。
- 核心执行编排优先挂接成熟内核（当前默认 Nautilus Trader 适配层），策略模块仅输出意图，不直接绑定底层撮合实现。

### 3.3 存储与分析

- 行情与事件日志：Parquet
- 元数据：DuckDB（可辅以 SQLite）

---

## 4. 核心策略定义

### 4.1 核心对象

```text
spread_t = log(P_B_local) - β_A * log(P_A) - γ * log(P_sector_or_mkt)
gap_t    = mid_B_local / fair_B_t - 1
fair_B_t = w * fair_cross_venue_B_t + (1-w) * fair_model_B_t
```

### 4.2 报价原则

- 对 B 维护单边多层动态 deep bid（q1/q2/q3）。
- 挂单价随 A、外部 fair、盘口脆弱度实时更新。
- 以事件驱动重报价为主，避免蛮力撤单刷单。

---

## 5. 系统模块

```text
wickhunter/
  configs/
  docs/
  data/
  src/
    main.py
    common/
    exchange/
    marketdata/
    strategy/
    execution/
    risk/
    portfolio/
    backtest/
    simulation/
    analytics/
    storage/
    cli/
  tests/
```

### 5.1 exchange/

- Binance / OKX（预留 Bybit）适配
- 下单、撤单、查单、查仓
- 订单状态归一化与错误码重试

### 5.2 marketdata/

- WS 连接管理
- 快照 + 增量簿重建
- 逐笔成交缓存
- 中间价、深度、簿脆弱度指标

### 5.3 strategy/

- Universe 与 A/B 配对
- beta 与残差统计
- fair value 估计
- wick detector
- quote engine
- 显式状态机

### 5.4 execution/

- B 挂单管理（post-only/GTX）
- B 成交驱动 A 对冲（IOC / aggressive limit）
- 撤单节流、最小存活时间、限频保护

### 5.5 risk/

- 单币/单事件/单日风控
- 数据与系统 kill switch
- 裸腿暴露时长约束

### 5.6 backtest + simulation/

- 订单簿事件驱动回放
- 部分成交与对冲延迟建模
- 成本、滑点、尾损归因

---

## 6. 状态机（必须显式实现）

```text
DISCOVER -> ARM -> QUOTE -> FILL_B -> HEDGE_A -> MANAGE -> EXIT -> RESET
```

### 状态说明（摘要）

- **DISCOVER**：30 分钟更新 B 池、A/B 配对、beta/R²/半衰期。
- **ARM**：检查是否允许武装报价（簿变薄、外部 fair 稳定、A 未同步崩）。
- **QUOTE**：维护动态 q1/q2/q3，按事件驱动改价。
- **FILL_B**：B 任意部分成交即进入对冲。
- **HEDGE_A**：按已成交量立刻对冲 A，失败重试并降风险。
- **MANAGE**：按 gap 回填/外部 fair 变化管理持仓。
- **EXIT/RESET**：平仓、归档、清理挂单。

---

## 7. 信号与阈值（V1 默认）

### 7.1 配对筛选

```text
score(B,A) =
  0.40 * Corr_30d_5m
+ 0.35 * R2_6h_1s
- 0.15 * BetaInstability_6h
- 0.10 * LiquidityPenalty
```

阈值建议：

- Corr_30d_5m > 0.70
- R2_6h_1s > 0.35
- HalfLife in [10s, 10m]

### 7.2 Stub quote 参数

- theta1 = 0.6%
- theta2 = 1.0%
- theta3 = 1.6%
- size1/2/3 = max name risk 的 10% / 15% / 25%

### 7.3 改价/撤单触发

任一满足即撤单重挂：

- fair_B 显著变动
- A 单秒异常波动
- 外部 B 中位价同方向显著下移
- spread 异常扩大
- 行情延迟超阈值
- 订单簿序列断裂

---

## 8. 交易所规则保护

### Binance

- 处理限频与退避（429/418）
- 监控 5 秒窗口高撤单行为
- 监控 invalid cancellation / 下单撤单比

### OKX

- REST / WS 限频保护
- 支持私有频道订单状态回报与重连恢复
- 预留交易行为监控（撤单率、成单比）

### Bybit（可选第三阶段）

- 保留兼容接口，复用 OKX/Binance 的统一执行抽象

---

## 9. 风控

### 账户级

- 日内最大亏损：2%
- 策略最大回撤停机：5%
- 单日最大事件数：20
- 裸 B 腿暴露时长上限：1 秒

### 单事件级

- 单事件风险上限：0.25% 权益
- 单 B 挂单最大名义：0.5x 账户权益

### Kill Switch

任一触发即停机：

- 订单簿断档
- 行情延迟 > 250ms
- 连续两次对冲失败
- 交易所风控限制
- 下单/撤单错误率突增

---

## 10. 里程碑（可执行）

### M0（1 周）基础设施

- 项目脚手架
- 配置系统
- 日志与事件总线
- 指标与告警骨架

### M1（2 周）Binance 行情与执行 MVP

- diff depth + snapshot 拼接与一致性
- B 端被动挂单与状态回报
- A 端 IOC 对冲通道

### M2（2 周）策略状态机 MVP

- DISCOVER/ARM/QUOTE/FILL/HEDGE/MANAGE 全链路
- 撤单节流 + 最小存活时间
- 风控与 kill switch

### M3（2 周）Nautilus Trader 回放仿真

- 事件级回放
- fill/hedge 延迟与滑点建模
- 事件归因报表

### M4（1~2 周）小额实盘

- 白名单标的 1~2 个
- 小仓位、灰度开关
- 每日复盘与参数冻结

---

## 11. 验收标准（V1）

1. 能在 Binance 上稳定重建 A/B 订单簿并通过一致性检查。
2. 能跑通单事件：B 被动成交 → A 即时对冲 → 持仓管理 → 退出。
3. 具备撤单节流与风险停机，不触发明显交易所限制。
4. 回放与仿真输出完整指标：PnL、fill ratio、hedge latency、尾损。
5. 小额实盘连续运行并可追溯每个事件链路。
