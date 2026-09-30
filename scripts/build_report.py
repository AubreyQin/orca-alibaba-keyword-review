#!/usr/bin/env python3
"""把 raw-pages/page-NN.json 和 agent 写好的 judgments.json 合成 report.md / review.json / coverage.json。

用法：
    python3 scripts/build_report.py --run 审核报告/<时间戳>

judgments.json 由 agent 逐词写，格式为列表：
    {"term": "stainless steel tumbler", "zh": "不锈钢随行杯", "verdict": "✅", "note": ""}
verdict 只能是 ✅ / ⚠️ / ❌；note 是不超过 20 字的理由（❌ 必填）。
term 按页面原文精确匹配（区分大小写）；大小写变体各写一条。

规则：
- 只纳入页面显示点击占比 > 0 的行；0.00% 排除并计数；无法解析的记为未知，不当作零。
- 同一原词的大小写/空格变体在表里相邻显示，但各自保留原值，不合并。
- “建议新增降权”只列状态为未降权的 ❌ 词，按点击占比降序。
- “建议取消降权”列状态为已降权的 ✅ 词；已降权的 ⚠️ 词单独列为“可视情况取消”。
- 检查页面“最多 N 个”降权上限，超限时提示。
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
VERDICTS = ('✅', '⚠️', '❌')


def parse_share(raw):
    raw = (raw or '').strip()
    m = re.fullmatch(r'(\d+(?:\.\d+)?)%', raw)
    return float(m.group(1)) / 100 if m else None


def norm(term):
    return re.sub(r'\s+', ' ', term.strip().lower())


def load_pages(raw_dir):
    pages = []
    for f in sorted(raw_dir.glob('page-*.json')):
        d = json.loads(f.read_text())
        ci = d.get('column_index') or {'status': 1, 'term': 2, 'click_share': 3}
        rows = []
        for r in d['rows']:
            c = r['cells']
            if not any(x.strip() for x in c):
                continue
            rows.append({'page': d['page'], 'dom_row': r['dom_row'], 'business_row': len(rows) + 1, 'file': f.name,
                         'status': c[ci['status']].strip(), 'term': c[ci['term']].strip(), 'click_share_raw': c[ci['click_share']].strip(),
                         'click_share': parse_share(c[ci['click_share']]), 'read_at': d.get('read_at')})
        pages.append({'page': d['page'], 'file': f.name, 'rows': rows, 'pagination': d.get('pagination', []), 'date_inputs': d.get('date_inputs')})
    if not pages:
        sys.exit(f'{raw_dir} 下没有 page-*.json')
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True, help='本次审核目录，含 raw-pages/ 与 judgments.json')
    args = ap.parse_args()
    run = ROOT / args.run if not Path(args.run).is_absolute() else Path(args.run)
    raw = run / 'raw-pages'
    ctx = json.loads((raw / 'run-context.json').read_text()) if (raw / 'run-context.json').exists() else {}
    settings = json.loads((ROOT / '本地配置/settings.json').read_text()) if (ROOT / '本地配置/settings.json').exists() else {}
    product_images = settings.get('product_images') or f"产品资料/{settings.get('active_product', '<产品名>')}/图片/"
    judgments = json.loads((run / 'judgments.json').read_text())
    jmap = {}
    for j in judgments:
        if j['verdict'] not in VERDICTS:
            sys.exit(f'judgments.json 里 {j["term"]!r} 的 verdict 非法：{j["verdict"]}')
        if j['verdict'] == '❌' and not j.get('note'):
            sys.exit(f'{j["term"]!r} 判 ❌ 但没有理由')
        if j['term'] in jmap:
            sys.exit(f'judgments.json 重复：{j["term"]!r}')
        jmap[j['term']] = j

    pages = load_pages(raw)
    all_rows = [r for p in pages for r in p['rows']]
    positive = [r for r in all_rows if r['click_share'] is not None and r['click_share'] > 0]
    zero = [r for r in all_rows if r['click_share'] == 0]
    unknown = [r for r in all_rows if r['click_share'] is None]
    missing = [r['term'] for r in positive if r['term'] not in jmap]
    if missing:
        sys.exit(f'judgments.json 缺少 {len(missing)} 个纳入词的判断：{missing[:10]} ...')
    extra = sorted(set(jmap) - {r['term'] for r in positive})

    # 相同原词多处出现（含大小写变体）
    groups = defaultdict(list)
    for r in all_rows:
        groups[norm(r['term'])].append(r)
    # 只关注至少有一条被纳入（占比>0）的词组；全零的变体组与结果无关
    conflicts = {k: v for k, v in groups.items() if len(v) > 1 and any(r['click_share'] for r in v)}
    fingerprints = [(r['term'], r['status'], r['click_share_raw']) for r in all_rows]
    exact_dups = len(fingerprints) - len(set(fingerprints))

    # 结果行：按后台分页和页面上的顺序排列，# 就是该页第几条，方便对着后台核对
    positive.sort(key=lambda r: (r['page'], r['business_row']))
    result_rows = []
    for r in positive:
        j = jmap[r['term']]
        result_rows.append({'no': r['business_row'], 'page': r['page'], 'term': r['term'], 'zh': j['zh'], 'verdict': j['verdict'], 'note': j.get('note', ''),
                            'status': r['status'], 'click_share_raw': r['click_share_raw'], 'click_share': r['click_share'],
                            'source': {'file': f"raw-pages/{r['file']}", 'page': r['page'], 'business_row': r['business_row'], 'dom_row': r['dom_row'], 'read_at': r['read_at']},
                            'recommend': ('downweight' if j['verdict'] == '❌' and r['status'] == '未降权' else
                                          'cancel_downweight' if j['verdict'] == '✅' and r['status'] == '已降权' else
                                          'consider_cancel' if j['verdict'] == '⚠️' and r['status'] == '已降权' else 'keep')})
    add_dw = [r for r in result_rows if r['recommend'] == 'downweight']
    cancel = [r for r in result_rows if r['recommend'] == 'cancel_downweight']
    consider = [r for r in result_rows if r['recommend'] == 'consider_cancel']
    already_bad = [r for r in result_rows if r['verdict'] == '❌' and r['status'] == '已降权']

    notice = ctx.get('downweight_notice') or ''
    cap = int(m.group(1)) if (m := re.search(r'最多\s*(\d+)\s*个', notice)) else None
    tab_dw = next((int(m.group(1)) for t in ctx.get('tabs', []) if (m := re.search(r'已降权搜索词[（(](\d+)[)）]', t.get('text', '')))), None)

    total_pages = None
    for e in pages[-1]['pagination']:
        if (m := re.search(r'共(\d+)页', e.get('label') or '')):
            total_pages = int(m.group(1))
    last_next = next((e for e in pages[-1]['pagination'] if (e.get('label') or '').startswith('下一页')), None)
    date_inputs = ctx.get('date_inputs') or pages[0].get('date_inputs') or []
    now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    pages_read = [p['page'] for p in pages]

    coverage = {
        'pages_requested': ctx.get('requested_range'), 'pages_read': pages_read, 'total_pages_on_page': total_pages,
        'page_size_text': ctx.get('page_size_text'), 'rows_read': len(all_rows),
        'included_positive': len(positive), 'excluded_zero': len(zero), 'unknown_share_rows': len(unknown),
        'page_counts': [{'page': p['page'], 'rows': len(p['rows']), 'positive': sum(1 for r in p['rows'] if r['click_share'] and r['click_share'] > 0),
                         'zero': sum(1 for r in p['rows'] if r['click_share'] == 0), 'unknown': sum(1 for r in p['rows'] if r['click_share'] is None)} for p in pages],
        'last_read_page_next_button': last_next, 'read_reached_last_page': bool(last_next and last_next.get('disabled')),
        'exact_duplicate_rows': exact_dups,
        'same_term_variants': {k: [{'term': r['term'], 'page': r['page'], 'business_row': r['business_row'], 'click_share_raw': r['click_share_raw'], 'status': r['status']} for r in v] for k, v in conflicts.items()},
        'judgments_not_in_positive_rows': extra,
        'note': '只纳入页面显示点击占比>0的行；0.00%按显示值排除，四舍五入可能隐藏极小非零值；未读页不在覆盖范围内。'}

    review = {
        'run_status': 'complete' if not unknown else 'partial',
        'context': {'url': ctx.get('url'), 'campaign': settings.get('campaign'), 'account_scope': settings.get('account_scope'),
                    'date_inputs_on_page': date_inputs, 'date_range_setting': settings.get('date_range'),
                    'term_type': '买家搜索词', 'metric': '点击占比（不是点击率、不是点击数；分母范围页面未说明）',
                    'match_mode': settings.get('match_mode', 'category_rules'), 'product_images': product_images,
                    'downweight_notice': notice, 'downweight_cap': cap, 'downweighted_tab_count': tab_dw,
                    'read_started_at': ctx.get('started_at'), 'read_finished_at': ctx.get('finished_at'), 'report_written_at': now},
        'coverage': coverage, 'rows': result_rows,
        'summary': {'included': len(result_rows), 'verdict_counts': dict(Counter(r['verdict'] for r in result_rows)),
                    'status_counts': dict(Counter(r['status'] for r in result_rows)),
                    'add_downweight': [r['term'] for r in add_dw], 'cancel_downweight': [r['term'] for r in cancel],
                    'consider_cancel': [r['term'] for r in consider], 'already_downweighted_bad': [r['term'] for r in already_bad],
                    'cap_check': {'cap': cap, 'current_downweighted_tab': tab_dw, 'proposed_add': len(add_dw), 'proposed_cancel': len(cancel),
                                  'exceeds_cap': (cap is not None and tab_dw is not None and tab_dw + len(add_dw) - len(cancel) > cap)},
                    'advertising_changes_made': False}}
    (run / 'review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')
    (run / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + '\n')

    def md(v):
        return str(v).replace('|', '\\|').replace('\n', ' ')

    camp = settings.get('campaign') or {}
    L = [f"# 广告词审核报告：{camp.get('name', '未知计划')}", '',
         f"- 计划：{camp.get('name', '未知')}（ID {camp.get('id', '未知')}）；账户：{(settings.get('account_scope') or {}).get('account_label', '未知')}",
         f"- 页面：{ctx.get('url', '未知')}",
         f"- 页面日期框：{'；'.join(date_inputs) if date_inputs else '未读到'}（页面上有几个日期框就列几个，最后一个是搜索词表的日期；由用户在页面设置，agent 未改动）",
         f"- 读取页码：第 {pages_read[0]}–{pages_read[-1]} 页（用户指定），页面显示共 {total_pages if total_pages else '未知'} 页，每页 {ctx.get('page_size_text') or '未知'}",
         f"- 读取行数 {len(all_rows)}；点击占比 > 0 纳入 {len(positive)}；0.00% 排除 {len(zero)}；无法解析 {len(unknown)}",
         f"- 判断依据：产品图 `{product_images}` + 品类常识 + 需求记录中的用户纠正；点击占比只用于排序，不是点击率，不推算点击数或花费",
         f"- 生成时间：{now}；未执行任何降权/取消降权操作", '']
    if unknown:
        L += [f"**注意：{len(unknown)} 行点击占比无法解析，已按未知处理，未当作零。**", '']
    if pages_read[-1] != total_pages:
        L += [f"**覆盖说明：只读了第 {pages_read[0]}–{pages_read[-1]} 页，第 {pages_read[-1] + 1} 页起未读。**", '']
    def verdict_cell(r):
        return r['verdict'] + (f" {r['note']}" if r['note'] else '') + ('（已降权）' if r['status'] == '已降权' else '')

    def term_list(rows, with_reason=True):
        if not rows:
            return ['无。']
        return ['| # | 买家搜索词 | 中文 | 点击占比 | ' + ('原因' if with_reason else '说明') + ' |', '| --- | --- | --- | --- | --- |'] + \
               [f"| {r['no']} | {md(r['term'])} | {md(r['zh'])} | {r['click_share_raw']} | {md(r['note'])} |" for r in rows]

    # 逐页展示：每页一节，表内顺序 = 后台该页顺序，# = 该页第几条；表后紧跟本页的建议
    L += ['## 逐页结果（# 为后台该页的第几条；开着后台对应页即可核对）', '']
    for p in pages:
        prow = [r for r in result_rows if r['page'] == p['page']]
        p_add = [r for r in prow if r['recommend'] == 'downweight']
        p_cancel = [r for r in prow if r['recommend'] == 'cancel_downweight']
        p_consider = [r for r in prow if r['recommend'] == 'consider_cancel']
        L += [f"### 第 {p['page']} 页（{len(p['rows'])} 条；点击占比 > 0 的 {len(prow)} 条）", '']
        if not prow:
            L += ['本页没有点击占比 > 0 的词。', '']
            continue
        L += ['| # | 买家搜索词 | 中文 | 点击占比 | 判断 |', '| --- | --- | --- | --- | --- |']
        L += [f"| {r['no']} | {md(r['term'])} | {md(r['zh'])} | {r['click_share_raw']} | {md(verdict_cell(r))} |" for r in prow]
        L += ['', f"**本页建议新增降权（{len(p_add)} 个）**", ''] + term_list(p_add)
        L += ['', f"**本页建议取消降权（{len(p_cancel)} 个）**", ''] + term_list(p_cancel, False)
        if p_consider:
            L += ['', f"**本页已降权的 ⚠️ 泛词（{len(p_consider)} 个，是否取消由你定）**", ''] + term_list(p_consider, False)
        L.append('')
    L += ['## 数量与上限', '',
          f"- 建议新增降权共 {len(add_dw)} 个，建议取消降权共 {len(cancel)} 个，已降权的 ⚠️ 泛词共 {len(consider)} 个，见各页",
          f"- 判断分布：✅ {review['summary']['verdict_counts'].get('✅', 0)}，⚠️ {review['summary']['verdict_counts'].get('⚠️', 0)}，❌ {review['summary']['verdict_counts'].get('❌', 0)}",
          f"- 纳入词中已降权 {review['summary']['status_counts'].get('已降权', 0)}，未降权 {review['summary']['status_counts'].get('未降权', 0)}；页签显示已降权 {tab_dw if tab_dw is not None else '未知'}",
          f"- 已降权且 ❌ 的词 {len(already_bad)} 个，维持即可"]
    if cap is not None and tab_dw is not None:
        after = tab_dw + len(add_dw) - len(cancel)
        L.append(f"- 页面上限：最多 {cap} 个降权词。当前 {tab_dw} + 新增 {len(add_dw)} − 取消 {len(cancel)} = {after}" + ("，**超过上限，需按占比从高到低取舍**" if after > cap else "，未超上限"))
    L += ['', '[结构化结果 review.json](review.json) · [覆盖统计 coverage.json](coverage.json) · [原始页面 raw-pages/](raw-pages/)']
    (run / 'report.md').write_text('\n'.join(L) + '\n')
    print(json.dumps({'included': len(result_rows), 'add_downweight': len(add_dw), 'cancel_downweight': len(cancel), 'consider_cancel': len(consider),
                      'cap': cap, 'current': tab_dw, 'report': str(run / 'report.md')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
