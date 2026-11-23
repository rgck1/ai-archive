# -*- coding: utf-8 -*-
"""
年份集中度提取_2026-11-23.py

从三份结果 JSON 读取 yearly 与 drop_best_year / drop_worst_year，输出年份集中度对照表。
本脚本只读数据，不改动任何现有文件，结果打印到标准输出。

数据来源：
  1. champion_verify_result_fairplacebo_20261122.json   （main / pit 双口径）
  2. champion_verify_result_timestamppit_20261122.json  （timestamppit 口径）
  3. topn_sensitivity_result_newcal_20261122.json       （topn 30 组）
"""

import json
from pathlib import Path

BASE = Path(r"D:/我的工作台/02.输出区")
F_FAIR = BASE / "champion_verify_result_fairplacebo_20261122.json"
F_TS = BASE / "champion_verify_result_timestamppit_20261122.json"
F_TOPN = BASE / "topn_sensitivity_result_newcal_20261122.json"

CHAMP_SIGS = [
    ("冠军A_神奇公式", "冠军A"),
    ("冠军B_经营现金净余率", "冠军B"),
    ("冠军C_价值现金合成", "冠军C"),
]
TOPN_SIGS = [
    ("A_神奇公式", "A"),
    ("B_现金净余率", "B"),
    ("C_价值现金合成", "C"),
]
PASS_GROUPS = [("main", "15", "B_现金净余率"),
               ("main", "30", "C_价值现金合成"),
               ("pit", "30", "C_价值现金合成")]
MAIN20_GROUP = [("main", "20", s) for s, _ in TOPN_SIGS]


def load(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def f4(x):
    return "%.4f" % x


def pct1(x):
    return "%.1f%%" % (100.0 * x)


def row(full, best_year, best_contrib, drop_best, worst_year, worst_contrib,
        drop_worst, pct_2024, contrib_2024, contrib_rank_2024):
    """汇总一行；下降幅度按倍数差与相对比例两种口径呈现。"""
    return {
        "full": full,
        "best_year": str(best_year),
        "best_contrib": best_contrib,
        "drop_best": drop_best,
        "decline_abs": full - drop_best,
        "decline_rel": 1.0 - drop_best / full if full else float("nan"),
        "worst_year": str(worst_year),
        "worst_contrib": worst_contrib,
        "drop_worst": drop_worst,
        "pct_2024": pct_2024,
        "contrib_2024": contrib_2024,
        "contrib_rank_2024": contrib_rank_2024,
    }


def from_champion(o):
    yearly = o["yearly"]
    db = o["drop_best_year"]
    dw = o["drop_worst_year"]
    pb = o["placebo_yearly_all"]["2024"]
    rank = 1 + sum(1 for v in yearly.values() if v > yearly["2024"])
    return row(
        full=o["full"]["total_multiple"],
        best_year=db["year"], best_contrib=yearly[db["year"]],
        drop_best=db["mult"],
        worst_year=dw["year"], worst_contrib=yearly[dw["year"]],
        drop_worst=dw["mult"],
        pct_2024=pb["pct"], contrib_2024=yearly["2024"],
        contrib_rank_2024=rank,
    )


def from_topn(s):
    yearly = s["yearly"]
    rank = 1 + sum(1 for v in yearly.values() if v > yearly["2024"])
    return row(
        full=s["full_mult"],
        best_year=s["drop_best_year"], best_contrib=yearly[str(s["drop_best_year"])],
        drop_best=s["drop_best"],
        worst_year=s["drop_worst_year"], worst_contrib=yearly[str(s["drop_worst_year"])],
        drop_worst=s["drop_worst"],
        pct_2024=None, contrib_2024=yearly["2024"],
        contrib_rank_2024=rank,
    )


def md_table(header, lines):
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for line in lines:
        print("| " + " | ".join(line) + " |")


def row_cells(name, r):
    pct_cell = "不适用" if r["pct_2024"] is None else pct1(r["pct_2024"])
    return [
        name, f4(r["full"]), r["best_year"], f4(r["best_contrib"]),
        f4(r["drop_best"]), f4(r["decline_abs"]), pct1(r["decline_rel"]),
        f4(r["drop_worst"]), pct_cell, f4(r["contrib_2024"]),
        str(r["contrib_rank_2024"]),
    ]


HEADER = ["策略/口径", "全期倍数", "最好年", "最好年贡献", "剔除后倍数",
          "下降(倍数)", "下降(比例)", "剔除最差年后倍数",
          "2024分位", "2024贡献", "2024贡献排名"]


def main():
    fair = load(F_FAIR)
    ts = load(F_TS)
    topn = load(F_TOPN)

    print("# 年份集中度提取结果（脚本直出，供核对）")
    print()

    # ---------- 表 1：冠军因子 9 组 ----------
    print("## 表1 冠军因子 × 三口径 × 剔除最好/最差年")
    print()
    champ_rows = []
    for cal, data in [("main", fair), ("pit", fair), ("timestamppit", ts)]:
        for sig, tag in CHAMP_SIGS:
            r = from_champion(data[sig][cal])
            champ_rows.append((tag + " " + cal, r))
    md_table(HEADER, [row_cells(n, r) for n, r in champ_rows])
    print()

    # ---------- 表 2：topn 选定 6 组逐年 ----------
    print("## 表2 topn 选定组（3 个常规 PASS + 主口径 main20 三策略）")
    print()
    topn_rows = []
    for cal, tier, sig in PASS_GROUPS + MAIN20_GROUP:
        s = topn["data"][cal][tier]["strats"][sig]
        tag = sig[0]
        label = "%s top%s %s [%s]" % (cal, tier, tag,
                                      "PASS" if (cal, tier, sig) in PASS_GROUPS else "基准")
        topn_rows.append((label, from_topn(s)))
    md_table(HEADER, [row_cells(n, r) for n, r in topn_rows])
    print()

    # ---------- 表 3：逐年贡献明细（选定组） ----------
    print("## 表3 逐年贡献明细（贡献语义：正数代表当年正贡献）")
    print()
    years = [str(y) for y in range(2018, 2027)]
    yearly_lines = []
    for label, o in (
        [(tag + " " + cal, fair[sig][cal])
         for cal in ("main", "pit") for sig, tag in CHAMP_SIGS] +
        [(tag + " timestamppit", ts[sig]["timestamppit"]) for sig, tag in CHAMP_SIGS]
    ):
        yearly_lines.append([label] + [f4(o["yearly"][y]) for y in years])
    md_table(["策略/口径"] + years, yearly_lines)
    print()

    # ---------- 全 30 组 best year 分布 ----------
    print("## 表4 topn 全 30 组最好年份分布")
    print()
    all_topn = []
    for cal in ("main", "pit"):
        for tier in ("5", "10", "15", "20", "30"):
            for sig, _ in TOPN_SIGS:
                all_topn.append(from_topn(topn["data"][cal][tier]["strats"][sig]))
    dist = {}
    for r in all_topn:
        dist[r["best_year"]] = dist.get(r["best_year"], 0) + 1
    for y in sorted(dist):
        print("  %s : %d 组" % (y, dist[y]))
    print()

    # ---------- 2024 分位专项 ----------
    print("## 表5 冠军因子 9 组 2024 安慰剂分位")
    print()
    pct_lines = []
    for name, r in champ_rows:
        pct_lines.append([name, pct1(r["pct_2024"]), f4(r["contrib_2024"])])
    md_table(["策略/口径", "2024 安慰剂分位", "2024 贡献"], pct_lines)
    print()

    # ---------- 汇总判断量 ----------
    print("## 汇总判断量")
    print()
    champ_2024 = sum(1 for _, r in champ_rows if r["best_year"] == "2024")
    topn_2024 = sum(1 for r in all_topn if r["best_year"] == "2024")
    print("  冠军因子 9 组中 2024 为最好年：%d 组" % champ_2024)
    print("  topn 30 组中 2024 为最好年：%d 组" % topn_2024)
    print("  合计 39 组中 2024 为最好年：%d 组" % (champ_2024 + topn_2024))
    print()
    print("  冠军因子 9 组下降幅度（相对比例）降序：")
    for name, r in sorted(champ_rows, key=lambda x: -x[1]["decline_rel"]):
        print("    %-20s 最好年=%s  %s" % (name, r["best_year"], pct1(r["decline_rel"])))
    print()
    print("  topn 30 组下降幅度（相对比例）降序前 5：")
    for r in sorted(all_topn, key=lambda x: -x["decline_rel"])[:5]:
        print("    最好年=%s 下降=%s 全期倍数=%.4f 剔除后=%.4f" %
              (r["best_year"], pct1(r["decline_rel"]), r["full"], r["drop_best"]))


if __name__ == "__main__":
    main()
