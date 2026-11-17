# -*- coding: utf-8 -*-
"""v99 线上真浏览器核验（TAT + 服务器 Playwright，自签只读会话）。"""
import os, sys, json, hmac, hashlib, time

BASE = "https://wt.likeke.top/"
SECRET = "/opt/invest-workbench/.session_secret"

def main():
    with open(SECRET, encoding="utf-8") as fh:
        s = fh.read().strip()
    p = "user|%d" % (int(time.time()) + 3600)
    cv = p + "|" + hmac.new(s.encode(), p.encode(), hashlib.sha256).hexdigest()

    from playwright.sync_api import sync_playwright
    results = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900},
                            device_scale_factor=1)
        ctx.add_cookies([{"name": "xq_sess", "value": cv, "url": BASE, "secure": True}])
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(2500)

        results["pageerror_count"] = len(errs)
        results["pageerror_sample"] = errs[:3]
        # 新函数存在（启动并行、按页渲染、图表降采样、博客分页）
        for fn in ("renderLive", "_thinToPixels", "blogShowMore"):
            results["fn_" + fn] = pg.evaluate("typeof %s === 'function'" % fn)
        # Promise.allSettled 出现在启动代码里
        results["boot_parallel"] = "Promise.allSettled" in (pg.content() or "")
        # canvas 真实像素（净值图）
        painted = pg.evaluate("""() => {
          var ids=['poolChartTodayNav','poolChartTodaySub'];
          var out={};
          ids.forEach(function(id){
            var cv=document.getElementById(id);
            if(!cv){out[id]='missing';return;}
            var c=cv.getContext('2d');
            var d=c.getImageData(0,0,Math.min(cv.width,200),Math.min(cv.height,80)).data;
            var nz=0; for(var i=3;i<d.length;i+=4){ if(d[i]>0) nz++; }
            out[id]=nz;
          });
          return out;
        }""")
        results["canvas_pixels"] = painted
        # 博客分页：切到博客页看是否有「加载更多」或条目数受控
        try:
            pg.evaluate("switchTab('blog')")
            pg.wait_for_timeout(800)
            txt = pg.evaluate("document.body.innerText")
            results["blog_has_more_or_all"] = ("加载更多" in txt) or ("已显示全部" in txt)
        except Exception as e:
            results["blog_has_more_or_all"] = "ERR:" + str(e)[:80]
        b.close()

    checks = {
        "pageerror=0": results["pageerror_count"] == 0,
        "renderLive存在": results["fn_renderLive"] is True,
        "thinToPixels存在": results["fn__thinToPixels"] is True,
        "blogShowMore存在": results["fn_blogShowMore"] is True,
        "启动并行化": results["boot_parallel"] is True,
        "净值图画布有像素": all(isinstance(v, int) and v > 50 for v in results["canvas_pixels"].values()),
        "博客分页生效": results["blog_has_more_or_all"] is True,
    }
    print("=== v99 核验明细 ===")
    print(json.dumps(results, ensure_ascii=False, indent=1))
    print("=== 断言 ===")
    for k, v in checks.items():
        print(("PASS" if v else "FAIL"), k)
    print("ALL=", all(checks.values()))
    return 0 if all(checks.values()) else 2

if __name__ == "__main__":
    sys.exit(main())
