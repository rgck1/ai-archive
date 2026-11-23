# 逐日收益序列导出说明（2026-11-23）

## 结论

导出 39 个策略，每个策略 full 与 oos 两条序列，合计 78 条序列。倍数自检 78/78 条通过。总耗时 35.5 秒。

## npz 字段含义

文件：`daily_sequences_2026-11-23.npz`（numpy 压缩 npz）。

- `_dates`：全局交易日字符串数组，长度 2124，格式为 YYYY-MM-DD。
- `_meta`：JSON 字符串（0 维数组，用 `.item()` 取出），含 start、oos、容差、引擎口径、成本、掩码规模、各策略配置与逐条自检结果。
- 每个策略 key 存一个二维数组，形状 (n, 2)。第一列为日期序号，即该日相对 `_dates` 的整数索引；第二列为该交易日日收益（float）。
- key 后缀规则：`magic__main` 为 full 段（start=2018-01-02）；`magic__main__oos` 为样本外独立重跑段（start=2023-01-01）。其余以此类推。

## 如何读取

```python
import json, numpy as np
d = np.load(r'D:\我的工作台\02.输出区\daily_sequences_2026-11-23.npz')
meta = json.loads(d['_meta'].item())
dates_all = d['_dates']
arr = d['magic__main']              # (n,2): [date_index, daily_return]
idx = arr[:, 0].astype(int)
rets = arr[:, 1]
dates = dates_all[idx]
full_mult = float(np.prod(1 + rets))
```

## 策略清单（39 个）

冠军因子 9 条：magic、cash、combo 各乘 main、pit、timestamppit 三口径。

topn 敏感性 30 组：档位 5、10、15、20、30 各乘 main、pit 两口径，再乘 magic、cash、combo 三信号。

每个策略另有 `__oos` 后缀的样本外独立重跑序列，共 78 条。

## 自检对照表

口径：对每条序列算 `np.prod(1+rets)`，与权威 JSON 对应字段比对，容差 ±0.01。权威来源：冠军 main/pit 取 champion_verify_result_fairplacebo_20261122.json，timestamppit 取 champion_verify_result_timestamppit_20261122.json，topn 取 topn_sensitivity_result_newcal_20261122.json。

| 类别 | 策略 key | 段 | 导出倍数 | 权威倍数 | 差值 | 是否通过 |
| --- | --- | --- | --- | --- | --- | --- |
| 冠军因子 | magic__main | full | 1.5011 | 1.5011 | -0.000010 | 通过 |
| 冠军因子 | magic__main | oos | 1.9911 | 1.9911 | -0.000008 | 通过 |
| 冠军因子 | magic__pit | full | 1.5302 | 1.5302 | -0.000035 | 通过 |
| 冠军因子 | magic__pit | oos | 1.8105 | 1.8105 | -0.000045 | 通过 |
| 冠军因子 | magic__timestamppit | full | 1.3496 | 1.3496 | -0.000030 | 通过 |
| 冠军因子 | magic__timestamppit | oos | 1.9033 | 1.9033 | +0.000019 | 通过 |
| 冠军因子 | cash__main | full | 1.8630 | 1.8630 | -0.000016 | 通过 |
| 冠军因子 | cash__main | oos | 1.4045 | 1.4045 | -0.000048 | 通过 |
| 冠军因子 | cash__pit | full | 1.7679 | 1.7679 | +0.000005 | 通过 |
| 冠军因子 | cash__pit | oos | 1.4359 | 1.4359 | +0.000019 | 通过 |
| 冠军因子 | cash__timestamppit | full | 1.6343 | 1.6343 | -0.000014 | 通过 |
| 冠军因子 | cash__timestamppit | oos | 1.3753 | 1.3753 | +0.000033 | 通过 |
| 冠军因子 | combo__main | full | 1.7272 | 1.7272 | -0.000049 | 通过 |
| 冠军因子 | combo__main | oos | 1.6576 | 1.6576 | -0.000046 | 通过 |
| 冠军因子 | combo__pit | full | 1.7739 | 1.7739 | +0.000044 | 通过 |
| 冠军因子 | combo__pit | oos | 1.5993 | 1.5993 | +0.000048 | 通过 |
| 冠军因子 | combo__timestamppit | full | 1.6805 | 1.6805 | -0.000014 | 通过 |
| 冠军因子 | combo__timestamppit | oos | 1.6470 | 1.6470 | -0.000044 | 通过 |
| topn敏感性 | topn5__main__magic | full | 0.8824 | 0.8824 | -0.000040 | 通过 |
| topn敏感性 | topn5__main__magic | oos | 1.5559 | 1.5559 | +0.000047 | 通过 |
| topn敏感性 | topn5__main__cash | full | 4.4329 | 4.4329 | +0.000036 | 通过 |
| topn敏感性 | topn5__main__cash | oos | 1.6970 | 1.6970 | +0.000014 | 通过 |
| topn敏感性 | topn5__main__combo | full | 0.9777 | 0.9777 | +0.000049 | 通过 |
| topn敏感性 | topn5__main__combo | oos | 1.7885 | 1.7885 | -0.000031 | 通过 |
| topn敏感性 | topn5__pit__magic | full | 1.1909 | 1.1909 | +0.000035 | 通过 |
| topn敏感性 | topn5__pit__magic | oos | 1.6795 | 1.6795 | +0.000014 | 通过 |
| topn敏感性 | topn5__pit__cash | full | 3.9040 | 3.9040 | +0.000008 | 通过 |
| topn敏感性 | topn5__pit__cash | oos | 1.8321 | 1.8321 | +0.000041 | 通过 |
| topn敏感性 | topn5__pit__combo | full | 1.7182 | 1.7182 | +0.000040 | 通过 |
| topn敏感性 | topn5__pit__combo | oos | 1.7416 | 1.7416 | -0.000049 | 通过 |
| topn敏感性 | topn10__main__magic | full | 1.2385 | 1.2385 | -0.000006 | 通过 |
| topn敏感性 | topn10__main__magic | oos | 1.9202 | 1.9202 | +0.000005 | 通过 |
| topn敏感性 | topn10__main__cash | full | 2.5763 | 2.5763 | -0.000020 | 通过 |
| topn敏感性 | topn10__main__cash | oos | 1.5858 | 1.5858 | +0.000007 | 通过 |
| topn敏感性 | topn10__main__combo | full | 1.5254 | 1.5254 | -0.000018 | 通过 |
| topn敏感性 | topn10__main__combo | oos | 1.6012 | 1.6012 | +0.000013 | 通过 |
| topn敏感性 | topn10__pit__magic | full | 1.5258 | 1.5258 | +0.000007 | 通过 |
| topn敏感性 | topn10__pit__magic | oos | 1.7150 | 1.7150 | -0.000046 | 通过 |
| topn敏感性 | topn10__pit__cash | full | 2.4022 | 2.4022 | +0.000044 | 通过 |
| topn敏感性 | topn10__pit__cash | oos | 1.6363 | 1.6363 | -0.000025 | 通过 |
| topn敏感性 | topn10__pit__combo | full | 1.6626 | 1.6626 | -0.000041 | 通过 |
| topn敏感性 | topn10__pit__combo | oos | 1.5772 | 1.5772 | -0.000042 | 通过 |
| topn敏感性 | topn15__main__magic | full | 1.5183 | 1.5183 | -0.000019 | 通过 |
| topn敏感性 | topn15__main__magic | oos | 2.0156 | 2.0156 | +0.000020 | 通过 |
| topn敏感性 | topn15__main__cash | full | 2.4475 | 2.4475 | +0.000027 | 通过 |
| topn敏感性 | topn15__main__cash | oos | 1.5599 | 1.5599 | +0.000026 | 通过 |
| topn敏感性 | topn15__main__combo | full | 1.6377 | 1.6377 | -0.000026 | 通过 |
| topn敏感性 | topn15__main__combo | oos | 1.6161 | 1.6161 | -0.000023 | 通过 |
| topn敏感性 | topn15__pit__magic | full | 1.4691 | 1.4691 | -0.000004 | 通过 |
| topn敏感性 | topn15__pit__magic | oos | 1.8976 | 1.8976 | -0.000027 | 通过 |
| topn敏感性 | topn15__pit__cash | full | 2.0689 | 2.0689 | +0.000041 | 通过 |
| topn敏感性 | topn15__pit__cash | oos | 1.5580 | 1.5580 | +0.000048 | 通过 |
| topn敏感性 | topn15__pit__combo | full | 1.8453 | 1.8453 | +0.000035 | 通过 |
| topn敏感性 | topn15__pit__combo | oos | 1.6212 | 1.6212 | -0.000027 | 通过 |
| topn敏感性 | topn20__main__magic | full | 1.5011 | 1.5011 | -0.000010 | 通过 |
| topn敏感性 | topn20__main__magic | oos | 1.9911 | 1.9911 | -0.000008 | 通过 |
| topn敏感性 | topn20__main__cash | full | 1.8630 | 1.8630 | -0.000016 | 通过 |
| topn敏感性 | topn20__main__cash | oos | 1.4045 | 1.4045 | -0.000048 | 通过 |
| topn敏感性 | topn20__main__combo | full | 1.7272 | 1.7272 | -0.000049 | 通过 |
| topn敏感性 | topn20__main__combo | oos | 1.6576 | 1.6576 | -0.000046 | 通过 |
| topn敏感性 | topn20__pit__magic | full | 1.5302 | 1.5302 | -0.000035 | 通过 |
| topn敏感性 | topn20__pit__magic | oos | 1.8105 | 1.8105 | -0.000045 | 通过 |
| topn敏感性 | topn20__pit__cash | full | 1.7679 | 1.7679 | +0.000005 | 通过 |
| topn敏感性 | topn20__pit__cash | oos | 1.4359 | 1.4359 | +0.000019 | 通过 |
| topn敏感性 | topn20__pit__combo | full | 1.7739 | 1.7739 | +0.000044 | 通过 |
| topn敏感性 | topn20__pit__combo | oos | 1.5993 | 1.5993 | +0.000048 | 通过 |
| topn敏感性 | topn30__main__magic | full | 1.3159 | 1.3159 | -0.000034 | 通过 |
| topn敏感性 | topn30__main__magic | oos | 1.7792 | 1.7792 | -0.000034 | 通过 |
| topn敏感性 | topn30__main__cash | full | 1.4497 | 1.4497 | -0.000023 | 通过 |
| topn敏感性 | topn30__main__cash | oos | 1.3592 | 1.3592 | -0.000028 | 通过 |
| topn敏感性 | topn30__main__combo | full | 1.8102 | 1.8102 | +0.000012 | 通过 |
| topn敏感性 | topn30__main__combo | oos | 1.5859 | 1.5859 | -0.000016 | 通过 |
| topn敏感性 | topn30__pit__magic | full | 1.3783 | 1.3783 | -0.000040 | 通过 |
| topn敏感性 | topn30__pit__magic | oos | 1.5842 | 1.5842 | -0.000040 | 通过 |
| topn敏感性 | topn30__pit__cash | full | 1.3905 | 1.3905 | -0.000028 | 通过 |
| topn敏感性 | topn30__pit__cash | oos | 1.3281 | 1.3281 | +0.000008 | 通过 |
| topn敏感性 | topn30__pit__combo | full | 1.9510 | 1.9510 | +0.000006 | 通过 |
| topn敏感性 | topn30__pit__combo | oos | 1.5659 | 1.5659 | +0.000025 | 通过 |

汇总：78/78 条通过。

全部序列与权威 JSON 在容差内一致，无未通过项。

## 口径说明

- 信号、成本、掩码与权威回测脚本逐行一致，冠军用 topn=20、hold=20，成本取 `cost_of(spec)[0]`；topn 逐档取 `cost_of(spec(tn))[0]`。
- timestamppit 口径在 signal 层注入时点化 ST/退市排除，mask 用纯板块 main，排除区间语义与第三口径脚本一致。
- 逐日收益来自 `cs_flex` 的 mark-to-market 口径，`rets[0]` 为空仓日 0，故 `np.prod(1+rets)` 与 `metrics.total_multiple` 等价。
- 本次只跑真实策略，跳过安慰剂循环，故耗时远低于全量重跑。
