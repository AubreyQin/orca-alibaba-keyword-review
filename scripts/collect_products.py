#!/usr/bin/env python3
"""可选：通过 opencli 读取计划“商品”页签的商品目录（ID、标题、类目、分组）。

只在需要核对某个词是否有对应在售商品时使用；不是审核的前置条件。
用法：先在页面切到“商品”页签第 1 页，再运行
    python3 scripts/collect_products.py --out 审核报告/<时间戳>/raw-pages

注意：切换页签可能重置搜索词表的日期和每页条数；回到搜索词表后请重新核对，不要在采集搜索词中途切换。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_search_terms import Cli, ROOT, load_settings, now  # noqa: E402

JS = r'''(() => {
const r = document.getElementById("p4p-root-content") || document.body;
const headers = Array.from(r.querySelectorAll("th")).map(e => e.innerText.trim());
const rows = Array.from(r.querySelectorAll("tbody tr")).map((e, i) => {
 const cells = Array.from(e.querySelectorAll("td")).map(c => c.innerText);
 return {dom_row: i + 1, cells, titles: Array.from(e.querySelectorAll("[title]")).map(n => n.title), links: Array.from(e.querySelectorAll("a[href]")).map(n => n.getAttribute("href"))};
}).filter(e => e.cells.some(c => /ID:\s*\d+/.test(c)));
return {url: location.href, headers, rows,
 total_text: Array.from(r.querySelectorAll("td,span,div")).map(e => e.childElementCount === 0 ? e.innerText.trim() : "").find(t => /^总计[:：]/.test(t)) || null,
 pagination: Array.from(r.querySelectorAll("button[aria-label]")).map(e => ({label: e.getAttribute("aria-label"), disabled: e.disabled}))};
})()'''


def current_page(data):
    nums = {int(m.group(1)) for e in data['pagination'] for m in [re.search(r'当前第(\d+)页', e['label'] or '')] if m}
    if len(nums) != 1:
        raise RuntimeError('无法识别商品页码')
    return nums.pop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-pages', type=int, default=20)
    args = ap.parse_args()
    cli = Cli(load_settings())
    out = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    products = []
    page = 1
    while True:
        text = cli.run('eval', JS)
        data = json.JSONDecoder().raw_decode(text[text.index('{'):])[0]
        if current_page(data) != page or not data['rows']:
            sys.exit(f'期望商品第{page}页且有数据，实际不符')
        data['page'], data['read_at'] = page, now()
        (out / f'products-{page:02d}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        for r in data['rows']:
            idm = next((re.search(r'ID:\s*(\d+)', c) for c in r['cells'] if re.search(r'ID:\s*(\d+)', c)), None)
            products.append({'product_id': idm.group(1) if idm else None, 'title': max(r['titles'], key=len) if r['titles'] else None,
                             'cells': r['cells'], 'links': r['links'], 'page': page, 'dom_row': r['dom_row']})
        print(json.dumps({'product_page': page, 'rows': len(data['rows']), 'total': data['total_text']}, ensure_ascii=False), flush=True)
        nxt = next((e for e in data['pagination'] if (e['label'] or '').startswith('下一页')), None)
        if not nxt or nxt['disabled'] or page >= args.max_pages:
            break
        state = cli.state()
        m = re.search(r'\[(\d+)\]<button aria-label=' + re.escape(nxt['label']) + r'\s*/>', state)
        if not m:
            sys.exit('找不到下一页按钮')
        cli.run('click', m.group(1))
        first = data['rows'][0]['cells']
        for _ in range(15):
            cli.run('wait', 'time', '1')
            t2 = cli.run('eval', JS)
            d2 = json.JSONDecoder().raw_decode(t2[t2.index('{'):])[0]
            if current_page(d2) == page + 1 and d2['rows'] and d2['rows'][0]['cells'] != first:
                break
        else:
            sys.exit('商品表未更新')
        page += 1
    ids = [p['product_id'] for p in products]
    catalog = {'read_at': now(), 'pages_read': page, 'rows_read': len(products), 'unique_product_ids': len(set(ids)), 'products': products}
    (out.parent / 'products-catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'done': True, 'products': len(products), 'unique': len(set(ids))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
