# -*- coding: utf-8 -*-
"""
BH-FDR 多重比较检验（q=0.10）与 Bonferroni 对照
================================================
只读三个现有 JSON，计算 BH 与 Bonferroni 通过集合，生成 Markdown 报告。
不修改任何现有文件。

p 值定义：p = 1 - pct，pct 为安慰剂中低于真实值的比例，属离散经验单尾 p 值。
比较时使用 round(p, 6) 并加 1e-9 容差，消除浮点表示误差（如 1-0.96 与 12*0.1/30 的边界）。
"""

import json
from pathlib import Path

OUT_DIR = Path(r"D:/我的工作台/02.输出区")
F_FAIR = OUT_DIR / "champion_verify_result_fairplacebo_20261122.json"
F_TIME = OUT_DIR / "champion_verify_result_timestamppit_20261122.json"
F_TOPN = OUT_DIR / "topn_sensitivity_result_newcal_20261122.json"
F_REPORT = OUT_DIR / "BH_FDR多重比较检验_2026-11-23.md"

Q = 0.10
EPS = 1e-9


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def pval(pct):
    """p = 1 - pct，四舍五入到 6 位，规避浮点尾数。"""
    return round(1.0 - float(pct), 6)


def pval_addone(pct, npl):
    """加一校正经验 p = (count_ge + 1)/(N + 1)，count_ge = (1-pct)*N。"""
    count_ge = round((1.0 - float(pct)) * npl)
    return round((count_ge + 1) / (npl + 1), 6)


def bh(pvalues, q=Q):
    """
    BH step-up：排序后找最大的 k 使 p_(k) <= k*q/m，拒绝前 k 个。
    返回 (k_star, 排序后的下标列表, 每秩临界值列表, 拒绝下标集合)。
    """
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    k_star = 0
    crit = [q * rank / m for rank in range(1, m + 1)]
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= crit[rank - 1] + EPS:
            k_star = rank
    rejected = set(order[:k_star])
    return k_star, order, crit, rejected


def bonferroni(pvalues, q=Q):
    m = len(pvalues)
    thr = q / m
    rejected = {i for i, p in enumerate(pvalues) if p <= thr + EPS}
    return thr, rejected


def sig(key):
    """从 '冠军A_xxx' / 'A_xxx' 提取 A/B/C 短标签。"""
    if key.startswith("冠军"):
        return "冠军" + key[2]
    return key[0]


# ---------------------------------------------------------------- 读取数据
fair = load(F_FAIR)
timep = load(F_TIME)
topn = load(F_TOPN)

npl_fair = fair["meta"]["placebo_n"]
npl_time = timep["meta"]["placebo_n"]
npl_topn = topn["meta"]["placebo_n"]

# 每条检验：label, p_full, p_oos, npl, group(champion/topn)
tests = []

# 冠军因子：3 信号 x 3 口径（main / pit 来自 fairplacebo；timestamppit 来自 timestamppit）
for sk in ["冠军A_神奇公式", "冠军B_经营现金净余率", "冠军C_价值现金合成"]:
    s = sig(sk)
    for mask in ["main", "pit"]:
        node = fair[sk][mask]
        tests.append({
            "label": f"{s}-{mask}",
            "p_full": pval(node["placebo_full_pct"]),
            "p_oos": pval(node["placebo_oos_pct"]),
            "p_add_full": pval_addone(node["placebo_full_pct"], npl_fair),
            "p_add_oos": pval_addone(node["placebo_oos_pct"], npl_fair),
            "npl": npl_fair,
            "group": "champion",
            "pctF": node["placebo_full_pct"],
            "pctO": node["placebo_oos_pct"],
        })
    node = timep[sk]["timestamppit"]
    tests.append({
        "label": f"{s}-timestamppit",
        "p_full": pval(node["placebo_full_pct"]),
        "p_oos": pval(node["placebo_oos_pct"]),
        "p_add_full": pval_addone(node["placebo_full_pct"], npl_time),
        "p_add_oos": pval_addone(node["placebo_oos_pct"], npl_time),
        "npl": npl_time,
        "group": "champion",
        "pctF": node["placebo_full_pct"],
        "pctO": node["placebo_oos_pct"],
    })

# topn：2 mask x 5 档 x 3 信号 = 30
for mask in ["main", "pit"]:
    for top in ["5", "10", "15", "20", "30"]:
        node = topn["data"][mask][top]
        npl_t = node.get("placebo_n", npl_topn)
        for sk, strat in node["strats"].items():
            tests.append({
                "label": f"{mask}-{top}-{sig(sk)}",
                "p_full": pval(strat["pctF"]),
                "p_oos": pval(strat["pctO"]),
                "p_add_full": pval_addone(strat["pctF"], npl_t),
                "p_add_oos": pval_addone(strat["pctO"], npl_t),
                "npl": npl_t,
                "group": "topn",
                "gate": strat["gate"]["result"],
                "pctF": strat["pctF"],
                "pctO": strat["pctO"],
            })

# 常规 PASS 列表（由 JSON gate 实读，不硬编码）
conventional_pass = [t["label"] for t in tests if t.get("gate") == "PASS"]

champ_idx = [i for i, t in enumerate(tests) if t["group"] == "champion"]
topn_idx = [i for i, t in enumerate(tests) if t["group"] == "topn"]
full_idx = list(range(len(tests)))


def analyze(indices, field):
    pv = [tests[i][field] for i in indices]
    k, order, crit, rej = bh(pv)
    bthr, brej = bonferroni(pv)
    return {
        "m": len(indices), "k": k, "order": order, "crit": crit,
        "bh_rej": rej, "bthr": bthr, "b_rej": brej, "pv": pv,
    }


A = {
    "full_full": analyze(full_idx, "p_full"),
    "topn_full": analyze(topn_idx, "p_full"),
    "full_oos": analyze(full_idx, "p_oos"),
    "topn_oos": analyze(topn_idx, "p_oos"),
}
A_ADD = {
    "full_full": analyze(full_idx, "p_add_full"),
    "topn_full": analyze(topn_idx, "p_add_full"),
    "full_oos": analyze(full_idx, "p_add_oos"),
    "topn_oos": analyze(topn_idx, "p_add_oos"),
}


# ---------------------------------------------------------------- 报告写出
L = []
add = L.append

def table(res, indices, field):
    """输出一族的全量排序审计表。"""
    add("| 排名 | 检验 | pct | p | BH临界 kq/m | BH判定 | Bonf判定 |")
    add("|---:|---|---:|---:|---:|:---:|:---:|")
    k = res["k"]
    for rank, li in enumerate(res["order"], start=1):
        idx = indices[li]
        t = tests[idx]
        pct = t["pctF"] if field == "p_full" else t["pctO"]
        p = res["pv"][li]
        bh_mark = "通过" if rank <= k else "-"
        b_mark = "通过" if li in res["b_rej"] else "-"
        add(f"| {rank} | {t['label']} | {pct} | {p:.3f} | {res['crit'][rank-1]:.5f} | {bh_mark} | {b_mark} |")

add("# BH-FDR 多重比较检验报告（q = 0.10）")
add("")
add("日期：2026-11-23。对照方法：Bonferroni。检验统计量：p = 1 - pct。")
add("")

add("## 1. 一句话结论")
add("")
add("全量族 39 个检验与 topn 族 30 个检验在 BH q=0.10 下通过数均为 0，与 Bonferroni 结论一致；此前 3 组常规 PASS（main-15-B、main-30-C、pit-30-C）在 BH q=0.10 下均不再属于通过集合，证据不足以支持其过门槛；加一校正敏感性对照下 full 端仍为 0 通过，不改变上述判断。")
add("")

add("## 2. p 值定义与精度限制")
add("")
add("pct 为安慰剂中低于真实值的比例，故单尾经验 p 值取 p = 1 - pct。原假设为真实策略与安慰剂同分布，p 越小表示真实值越极端。")
add("")
add(f"三个 JSON 实读的安慰剂次数：fairplacebo meta.placebo_n = {npl_fair}，timestamppit meta.placebo_n = {npl_time}，topn meta.placebo_n = {npl_topn}（每档亦标 {npl_topn}）。离散经验 p 值的最小分辨率分别为 1/{npl_fair} = {1.0/npl_fair:.3f}、1/{npl_time} = {1.0/npl_time:.3f}、1/{npl_topn} = {1.0/npl_topn:.3f}。任务说明曾提及 fairplacebo 用 NPL=200，与该文件实读值 {npl_fair} 不一致，本报告一律以 JSON 实读为准。")
add("")
add("pct = 1.0 时 p = 0，该 0 值表示分辨率以下的上界，其真实 p 至多为 1/NPL，不可解释为 p 精确等于 0。OOS 端出现多个 p = 0，相关结论需按此上界理解。")
add("")
add("比较时 p 取 6 位小数，判定条件 p_(k) <= k*q/m 加 1e-9 容差，用于消除浮点表示误差（例如 1 - 0.96 与 12*0.1/30 的边界相等情形）。")
add("")
add("另做加一校正敏感性对照：标准置换检验经验 p 值取 p = (count_ge + 1)/(N + 1)，其中 count_ge 为安慰剂中不低于真实值的个数，该口径保证原假设下 p 值的统计有效性。本报告主结果按任务要求用 p = 1 - pct，加一校正结果列于第 5 节末，仅作稳健性参照。")
add("")

add("## 3. 全量族（39 个检验）的 BH 与 Bonferroni 结果")
add("")
add("族的划分：30 组 topn 的 full 端（2 mask x 5 档 x 3 信号）+ 9 组冠军因子 full 端（3 信号 x 3 口径 main / pit / timestamppit）。这是覆盖全部搜索维度的最保守口径。q = 0.10，m = 39。")
add("")
r = A["full_full"]
add(f"BH：最大满足 p_(k) <= k*q/m 的秩 k = {r['k']}，通过数 = {len(r['bh_rej'])}。Bonferroni：阈值 q/m = {r['bthr']:.6f}，通过数 = {len(r['b_rej'])}。")
add("")
table(r, full_idx, "p_full")
add("")
add("差异与解释：两法均未拒绝任何原假设，通过集合相同且为空。最小 p 值 = "
    f"{min(r['pv']):.3f}，大于 BH 首位临界值 {r['crit'][0]:.6f} 与 Bonferroni 阈值 {r['bthr']:.6f}，"
    "查找空间扩张到 39 个检验后，门槛随 m 线性抬升，所有候选均落在门槛之外。")
add("")

add("## 4. topn 族（30 个检验）的 BH 与 Bonferroni 结果")
add("")
add("族的划分：仅 30 组 topn 的 full 端，单独成族。理由是 topn 档位（5/10/15/20/30）与信号、mask 共同构成事后搜索维度，需独立控制。q = 0.10，m = 30。")
add("")
r = A["topn_full"]
add(f"BH：最大满足秩 k = {r['k']}，通过数 = {len(r['bh_rej'])}。Bonferroni：阈值 q/m = {r['bthr']:.6f}，通过数 = {len(r['b_rej'])}。")
add("")
table(r, topn_idx, "p_full")
add("")
add("差异与解释：两法通过集合同为空。常规 PASS 的 3 组 p 值虽在 0.07 至 0.08 区间，仍高于 BH 在 m=30 下的首位临界值 "
    f"{r['crit'][0]:.6f}，也高于 Bonferroni 阈值 {r['bthr']:.6f}，故不进入通过集合。")
add("")

add("## 5. OOS 端稳健性对照")
add("")
add("OOS 端取 p = 1 - pctO。full 与 oos 是同一批检验的两个评价窗口，指标相关且样本重叠（oos 为 full 的后段），本报告将其作为稳健性对照分别成族，不与 full 端合并进同一族，避免同一假设被重复计数。")
add("")
for key, name, idxs in [("full_oos", "全量族 OOS（39）", full_idx), ("topn_oos", "topn 族 OOS（30）", topn_idx)]:
    r = A[key]
    add(f"### {name}")
    add("")
    add(f"BH q=0.10：最大满足秩 k = {r['k']}，通过数 = {len(r['bh_rej'])}。Bonferroni：阈值 q/m = {r['bthr']:.6f}，通过数 = {len(r['b_rej'])}。")
    add("")
    bh_names = [tests[idxs[li]]["label"] for li in r["order"][:r["k"]]]
    b_names = [tests[idxs[li]]["label"] for li in sorted(r["b_rej"])]
    add(f"BH 通过集合（{len(bh_names)}）：" + ("、".join(bh_names) if bh_names else "空") + "。")
    add("")
    add(f"Bonferroni 通过集合（{len(b_names)}）：" + ("、".join(b_names) if b_names else "空") + "。")
    add("")
    add(f"差异：BH 比 Bonferroni 多 {len(r['bh_rej']) - len(r['b_rej'])} 个通过。这部分为秩 {len(r['b_rej']) + 1} 至 {r['k']} 的检验，其 p 值高于 Bonferroni 统一阈值 q/m，但低于 BH 的逐级临界值 k*q/m，属 BH step-up 相对 Bonferroni 的标准功效增益。")
    add("")
    table(r, idxs, "p_oos")
    add("")

add("### 加一校正敏感性（p = (count_ge + 1)/(N + 1)）")
add("")
add("| 族（检验数） | 主口径 BH 通过 | 主口径 Bonf 通过 | 加一 BH 通过 | 加一 Bonf 通过 |")
add("|---|---:|---:|---:|---:|")
for key, name in [("full_full", "full 全量族（39）"), ("topn_full", "full topn 族（30）"),
                  ("full_oos", "OOS 全量族（39）"), ("topn_oos", "OOS topn 族（30）")]:
    main_r, add_r = A[key], A_ADD[key]
    add(f"| {name} | {len(main_r['bh_rej'])} | {len(main_r['b_rej'])} | {len(add_r['bh_rej'])} | {len(add_r['b_rej'])} |")
add("")
add("解释：加一后 pct = 1.0 的 p 由 0 变为 1/(N+1)，N=200 时为 0.00498，N=100 时为 0.00990，均高于 OOS 两族的 Bonferroni 阈值（0.002564 / 0.003333），故 OOS 端 Bonferroni 通过数归零。BH 各减少 1 组，退出项均为 main-15-C，其加一后 p = (8+1)/201 = 0.04478，高于全量族秩 17 临界 0.04359 与 topn 族秩 12 临界 0.04000。full 端（pctF 口径）最小 p 由 0.020 变为 0.02488，仍高于两族首位临界，通过数保持 0。")
add("")

add("## 6. 三组此前常规 PASS 在 BH 下的判定")
add("")
add("JSON gate.result = PASS 的 topn 检验共 "
    f"{len(conventional_pass)} 组：" + ("、".join(conventional_pass) if conventional_pass else "无") + "。")
add("")
add("| 检验 | pctF | full p | 全量族 BH q=0.10 | topn 族 BH q=0.10 | 全量族 Bonf | topn 族 Bonf |")
add("|---|---:|---:|:---:|:---:|:---:|:---:|")
for label in conventional_pass:
    idx = next(i for i, t in enumerate(tests) if t["label"] == label)
    p = tests[idx]["p_full"]
    ff = A["full_full"]
    tf = A["topn_full"]
    tf_pos = topn_idx.index(idx)
    def mark(res, li, rank=None):
        if rank is None:
            return "通过" if li in res["bh_rej"] else "不通过"
        return "通过" if rank <= res["k"] else "不通过"
    fr = ff["order"].index(idx) + 1
    tr = tf["order"].index(tf_pos) + 1
    add(f"| {label} | {tests[idx]['pctF']} | {p:.3f} | {mark(ff, idx, fr)} | {mark(tf, tf_pos, tr)} | "
        f"{'通过' if idx in ff['b_rej'] else '不通过'} | {'通过' if tf_pos in tf['b_rej'] else '不通过'} |")
add("")
add("解读：上述判定表示在 q=0.10 的 FDR 控制下未进入通过集合，属证据不足，等同于未过门槛。该结论不涉及因子负收益，也不构成对因子无效性的证明。")
add("")

add("## 7. 边界与局限")
add("")
add("BH 控制的是错误发现率，含义为在通过集合的期望中错误拒绝的比例不超过 q。它不控制任一单次结论的犯错概率，也不等于证明因子有效。")
add("")
add("p 值由安慰剂分位近似得到，精度受 NPL 限制（0.01 或 0.005），属离散经验值，解析分布尾概率在此不适用。p = 0 仅代表低于分辨率，不能按精确零解释。")
add("")
add("安慰剂在逐信号独立域内抽样，三者分位互不可比，各自与自身真实值可比。族内合并排序用于多重比较控制，不用于跨信号强弱排序。")
add("")
add("全量族与 topn 族存在包含关系，属两种口径并列报告，不构成相互独立的两次验证。OOS 端与 full 端共享样本区间，结论仅作稳健性参照。")
add("")
add("加一校正对照显示 OOS 端通过集合对 p = 0 的处理方式敏感，Bonferroni 通过数由 7/5 降为 0/0，BH 由 17/12 降为 16/11。OOS 端本作稳健性参照，该敏感性不改变 full 端 0 通过的核心结论，也不改变 3 组常规 PASS 不可采信的判断。")
add("")
add("所有结论措辞限定为证据不足与未过门槛，不涉及因子有效性定性。")
add("")

with open(F_REPORT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

# ---------------------------------------------------------------- 控制台摘要
print("=== BH-FDR q=0.10 摘要 ===")
print("JSON 实读 placebo_n:", {"fairplacebo": npl_fair, "timestamppit": npl_time, "topn": npl_topn})
print("常规 PASS（gate 实读）:", conventional_pass)
for key, name in [("full_full", "全量族 full"), ("topn_full", "topn族 full"),
                  ("full_oos", "全量族 oos"), ("topn_oos", "topn族 oos")]:
    r, ra = A[key], A_ADD[key]
    print(f"{name}: m={r['m']} BH k*={r['k']} BH通过={len(r['bh_rej'])} "
          f"Bonf阈值={r['bthr']:.6f} Bonf通过={len(r['b_rej'])} | "
          f"加一: BH={len(ra['bh_rej'])} Bonf={len(ra['b_rej'])}")
print("报告已写入:", F_REPORT)
