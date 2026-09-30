#!/usr/bin/env python3
"""通过 opencli 逐页读取阿里国际站全站推广“买家搜索词”表格。

用法（页码范围由用户指定，日期由用户在页面上设置好）：
    python3 scripts/collect_search_terms.py --out 审核报告/<时间戳>/raw-pages --start 1 --end 4

规则：
- 只读取 --start 到 --end 指定的页码；不自动往后翻。
- 开始前读取页面日期框和每页条数并写入 run-context.json；之后每页核对未变，变了就停止报错，不重设。
- 若 本地配置/settings.json 的 date_range 已填写，会与页面日期核对，不一致即停止。
- 只保存表格数据（page-NN.json），不保存整页 state 快照。
- 只点击分页按钮；不点击降权/取消降权或任何业务按钮。
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / '本地配置/settings.json'

JS = r'''(() => {
 const r = document.getElementById("p4p-root-content") || document.body;
 const tabs = Array.from(r.querySelectorAll("[role=tab]")).map(e => ({text: e.innerText.trim(), selected: e.getAttribute("aria-selected")}));
 const notice = Array.from(r.querySelectorAll("*")).map(e => e.childElementCount === 0 ? e.innerText : "").find(t => t && t.includes("最多") && t.includes("降权")) || null;
 return {
  url: location.href,
  date_inputs: Array.from(r.querySelectorAll("input")).map(e => e.value).filter(v => /^\d{4}-\d{2}-\d{2} - \d{4}-\d{2}-\d{2}$/.test(v)),
  page_size_text: (Array.from(r.querySelectorAll("*")).map(e => e.childElementCount === 0 ? (e.innerText || "").trim() : "").find(t => /^\d+\s*条\s*\/\s*页$/.test(t)) || null),
  headers: Array.from(r.querySelectorAll("th")).map(e => e.innerText.trim()),
  rows: Array.from(r.querySelectorAll("tbody tr")).map((e, i) => ({dom_row: i + 1, cells: Array.from(e.querySelectorAll("td")).map(c => c.innerText)})).filter(e => e.cells.length >= 4),
  pagination: Array.from(r.querySelectorAll("button[aria-label]")).map(e => ({text: e.innerText.trim(), label: e.getAttribute("aria-label"), disabled: e.disabled})),
  tabs, notice
 }; })()'''


def load_settings():
    if not SETTINGS_PATH.exists():
        sys.exit('缺少 本地配置/settings.json，请先按 AGENTS.md 初始化')
    return json.loads(SETTINGS_PATH.read_text())


class Cli:
    def __init__(self, settings):
        b = settings['browser']
        self.base = [b.get('executable') or 'opencli']
        if b.get('profile'):
            self.base += ['--profile', b['profile']]
        self.base += ['browser', b.get('session') or 'alibaba-keyword-review']

    def run(self, *args, timeout=45):
        p = subprocess.run(self.base + list(args), capture_output=True, text=True, timeout=timeout)
        if p.returncode:
            raise RuntimeError((p.stderr + p.stdout)[-1500:])
        return p.stdout

    def eval_json(self):
        text = self.run('eval', JS)
        return json.JSONDecoder().raw_decode(text[text.index('{'):])[0]

    def state(self):
        return self.run('state')


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')


def current_page(data):
    nums = {int(m.group(1)) for e in data['pagination'] for m in [re.search(r'当前第(\d+)页', e['label'] or '')] if m}
    if len(nums) != 1:
        raise RuntimeError(f'无法唯一识别当前页码：{nums}')
    return nums.pop()


def total_pages(data):
    nums = {int(m.group(1)) for e in data['pagination'] for m in [re.search(r'共(\d+)页', e['label'] or '')] if m}
    return max(nums) if nums else None


def business_rows(data):
    return [r for r in data['rows'] if any(c.strip() for c in r['cells'])]


def col_index(headers, name):
    for i, h in enumerate(headers):
        if h == name:
            return i
    raise RuntimeError(f'表头缺少“{name}”：{headers}')


def snapshot(data):
    """本次运行不允许变化的页面条件。"""
    return {'date_inputs': data['date_inputs'], 'page_size_text': data['page_size_text'], 'url_path': data['url'].split('#')[0]}


def next_page(cli, data):
    p = current_page(data)
    label = f'下一页，当前第{p}页'
    ctrl = next((e for e in data['pagination'] if e['label'] == label), None)
    if not ctrl or ctrl['disabled']:
        raise RuntimeError(f'第{p}页没有可用的下一页按钮')
    state = cli.state()
    m = re.search(r'\[(\d+)\]<button aria-label=' + re.escape(label) + r'\s*/>', state)
    if not m:
        raise RuntimeError('最新 state 中找不到下一页按钮')
    cli.run('click', m.group(1))
    previous = [e['cells'] for e in data['rows']]
    for _ in range(15):
        cli.run('wait', 'time', '1')
        observed = cli.eval_json()
        if current_page(observed) == p + 1 and observed['rows'] and [e['cells'] for e in observed['rows']] != previous:
            cli.run('wait', 'time', '1')
            return
    raise RuntimeError('翻页后表格内容未更新，拒绝采集陈旧行')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='raw-pages 输出目录')
    ap.add_argument('--start', type=int, required=True)
    ap.add_argument('--end', type=int, required=True)
    args = ap.parse_args()
    if args.start < 1 or args.end < args.start:
        sys.exit('页码范围无效')

    settings = load_settings()
    cli = Cli(settings)
    out = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    data = cli.eval_json()
    if '买家搜索词' not in data['headers'] or '点击占比' not in data['headers']:
        sys.exit(f'当前页面不是买家搜索词表格，表头：{data["headers"]}')
    baseline = snapshot(data)
    if not baseline['date_inputs']:
        sys.exit('页面上没有读到日期框，请先在页面设置日期')
    expected = settings.get('date_range') or {}
    if expected.get('start') and expected.get('end'):
        want = f"{expected['start']} - {expected['end']}"
        if want not in baseline['date_inputs']:
            sys.exit(f'settings.json 的日期 {want} 与页面日期 {baseline["date_inputs"]} 不一致；请核对页面设置，脚本不会改日期')
    page = current_page(data)
    if page != args.start:
        sys.exit(f'当前在第{page}页，请先把页面翻到第{args.start}页（脚本不跨页跳转，避免漏页）')

    ctx = {'started_at': now(), 'url': data['url'], 'date_inputs': baseline['date_inputs'], 'page_size_text': baseline['page_size_text'],
           'total_pages_on_page': total_pages(data), 'requested_range': [args.start, args.end], 'tabs': data['tabs'],
           'downweight_notice': data['notice'], 'headers': data['headers'], 'pages': []}
    (out / 'run-context.json').write_text(json.dumps(ctx, ensure_ascii=False, indent=2) + '\n')

    i_status, i_term, i_share = col_index(data['headers'], '状态'), col_index(data['headers'], '买家搜索词'), col_index(data['headers'], '点击占比')
    for page in range(args.start, args.end + 1):
        if page != args.start:
            next_page(cli, data)
            data = cli.eval_json()
        actual = current_page(data)
        if actual != page:
            sys.exit(f'期望第{page}页，实际第{actual}页')
        if snapshot(data) != baseline:
            sys.exit(f'第{page}页的日期/每页条数/地址发生变化：{snapshot(data)} ≠ {baseline}；已停止，不重设页面')
        data['page'] = page
        data['read_at'] = now()
        data['column_index'] = {'status': i_status, 'term': i_term, 'click_share': i_share}
        data['source_method'] = 'opencli eval 读取当前 DOM；未访问接口或浏览器存储'
        (out / f'page-{page:02d}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        rows = business_rows(data)
        pos = sum(1 for r in rows if re.fullmatch(r'\d+(?:\.\d+)?%', r['cells'][i_share].strip()) and float(r['cells'][i_share].strip()[:-1]) > 0)
        zero = sum(1 for r in rows if r['cells'][i_share].strip() == '0.00%')
        summary = {'page': page, 'rows': len(rows), 'positive': pos, 'zero': zero, 'unknown': len(rows) - pos - zero,
                   'first_term': rows[0]['cells'][i_term] if rows else None, 'last_term': rows[-1]['cells'][i_term] if rows else None}
        ctx['pages'].append(summary)
        (out / 'run-context.json').write_text(json.dumps(ctx, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    ctx['finished_at'] = now()
    (out / 'run-context.json').write_text(json.dumps(ctx, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'done': True, 'pages': [p['page'] for p in ctx['pages']], 'out': str(out)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
