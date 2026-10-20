# 聚宽因子库 · AKShare 复现

把聚宽因子看板（`joinquant_factors.json`，285 个因子）里的自然语言公式，逐条翻译成
基于 AKShare 公开数据的开源实现，产出**因子值**。本阶段不计算 IC、IR、分层收益与多空净值。

网页看板：[docs/index.html](docs/index.html)（因子看板，双击即可离线打开）
覆盖率视图：[docs/values.html](docs/values.html)（因子值覆盖率与预览）
研究报告：[report.md](report.md)

## 目录结构

```text
2-all-factor-dashboard/
├── main.py                 # 唯一 Python 入口
├── configs/
│   ├── default.yaml        # 默认参数
│   └── variants/smoke.yaml # 3 只股票的冒烟验证
├── factor_dashboard/
│   ├── settings.py         # 配置加载与校验
│   ├── pipeline.py         # 流程编排
│   ├── data/               # AKShare 取数、缓存、面板构建
│   ├── core/               # 指标函数、因子实现、注册表
│   └── report/             # 汇总统计与网页数据
├── scripts/run.sh          # 前台 / 后台统一启动
├── tests/                  # 口径单元测试
├── joinquant_factors.json  # 因子目录（输入）
├── docs/                   # 离线网页看板
├── data/cache/             # 行情与财报缓存（不提交）
├── outputs/runs/<run_id>/  # 每次运行的产物
└── report.md               # 研究记录
```

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
# 或直接安装依赖
pip install akshare pandas numpy pyarrow PyYAML pytest
```

需要 Python 3.11+。数据来自 AKShare 公共接口，不需要任何密钥。

## 运行

```bash
# 前台，使用 configs/default.yaml
python main.py
bash scripts/run.sh

# 指定配置
python main.py --config configs/variants/smoke.yaml

# 后台运行（返回 run_id / pid / 日志路径）
bash scripts/run.sh --background
```

`--config` 可省略；变体配置只需要写与默认配置不同的字段，加载时会与
`configs/default.yaml` 递归合并。

## 配置说明

| 字段 | 含义 |
| --- | --- |
| `universe.index_code` | 股票池指数，默认中证 500（`000905`） |
| `universe.limit` | 只取前 N 只，`null` 为全量 |
| `data.start_date` | 行情起点；需预留 504 日动量窗口 |
| `data.end_date` | 行情终点，留空表示今天 |
| `data.max_workers` | 取数并发数 |
| `output.start_date` | 因子值输出的起始日，用于跳过回看期 |
| `output.min_coverage` | 写入长表的最低覆盖率 |

## 输出

每次运行写入 `outputs/runs/<run_id>/`：

| 文件 | 内容 |
| --- | --- |
| `factor_values.parquet` | 长表：`date, code, factor, value` |
| `factor_summary.csv` | 每个因子的状态、覆盖率、最新截面统计 |
| `factor_catalog.csv` | 因子名、中文名、聚宽原文公式、分组、未实现原因 |
| `metadata.json` | 运行参数、股票池、日期区间、因子计数 |
| `config.yaml` | 本次运行实际使用的配置快照 |

网页数据写入三类文件：

- `docs/data/factor-metrics.js`（`window.FACTOR_BOARD`）：285 个因子的聚宽绩效指标、实现状态与交易日历；
- `docs/data/series/<factor>.js`（`window.SERIES_POOL`）：每个已实现因子一份，含截面中位数、25/75 分位与覆盖率的日序列，详情页按需加载；
- `docs/data/page-data.js`（`window.PAGE_DATA`）：覆盖率、分组统计与因子值预览，供 `values.html` 使用。

## 每日自动更新与发布

仓库自带 GitHub Actions 工作流 `.github/workflows/update-dashboard.yml`：

- 每个交易日北京时间 18:30（UTC 10:30）自动运行，收盘后重建数据；
- 重新抓取行情与财报、计算全部因子、生成 `docs/`；
- 直接把 `docs/` 作为 Pages 产物发布，**不向仓库提交数据**，避免历史体积膨胀；
- 支持在 Actions 页面手动触发（`workflow_dispatch`）。

启用方式：仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**，
再手动运行一次 workflow，之后每天自动更新。页面顶部的「更新至 YYYY-MM-DD」取自本次运行的
最后一个交易日，页脚保留 RUN 编号便于追溯。

> 工作流按「本目录即仓库根目录」编排，即 `2-all-factor-dashboard/` 直接作为仓库根；
> 如果把它放在子目录里，需要相应调整 `working-directory` 与产物路径。

缓存策略：工作流用 `actions/cache` 缓存 `data/cache`；行情缓存要求覆盖最近一个工作日
（否则自动重取），财报缓存默认 7 天过期（`data.financial_cache_days`），保证新财报能被及时纳入。

## 因子口径要点

- **行情**：新浪日线（前复权），换手率由小数换算为百分数；不复权收盘价单独取一份，
  用于 `price_no_fq`。
- **财务**：新浪三大报表。利润表/现金流量表为年内累计值，先还原为单季，再滚动四季求和得到 TTM。
- **对齐**：财务指标按**公告日**（缺失时用报告期 + 75 天）对齐到交易日，避免前视偏差。
- **总股本**：用「归母净利润 ÷ 基本每股收益」反推，属近似口径。
- **复合存量指标**：如 ROIC、经营资产周转率的分母，按季末采样后再滚动四季平均。

## 未实现的因子

26 个因子因数据或公式缺失未实现，逐条原因写在 `factor_catalog.csv` 的 `reason` 列：

- 分析师一致预期类（7 个）：AKShare 无稳定历史接口；
- 扣非净利润 / 非经常性损益（2 个）：不在三大报表口径内；
- 净利息费用（1 个）：缺「利息收入」科目；
- 9 个 `*_v2` 风格因子：聚宽未提供公式；
- 复合因子子项未定义（5 个）：`relative_momentum`、`ltrevrsl`、`profit`、`invsqlty`、`earnqlty`；
- 其余复合因子依赖分析师预期（`growth`、`earnings_yield`、`divyild`、`long_growth`、`earnvar`、`earnyild`）。

## 测试

```bash
python -m pytest -q
```

覆盖季度还原、真幅、加权回归、横截面残差等关键口径。

## 数据来源

- 行情、三大报表：AKShare（新浪财经接口）
- 指数成分：中证指数官网（经 AKShare）
- 因子公式与绩效字段：聚宽因子看板导出的 `joinquant_factors.json`

仅供研究与学习使用，不构成投资建议。
