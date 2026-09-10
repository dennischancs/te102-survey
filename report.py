# -*- coding: utf-8 -*-
"""
TE102 问卷 CSV → 报告生成器

用法:
  python report.py data.csv                  # 单份报告 (data_report.html)
  python report.py s001.csv s002.csv         # 多份汇总 (all_reports.html)
  python report.py data.csv -o my_report.html

功能:
  - 读取与 exportCSV 格式一致的 CSV 文件
  - 解析每题答案（处理 | 分隔的复合格式）
  - 生成 HTML 报告（样式参考问卷页面 result panel）
  - 各维度得分用颜色+比值展示，低分标红
  - 答题详情逐题展示（含题目原文）
"""
import csv, json, sys, os, glob, argparse
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
QJSON = SCRIPT_DIR / 'questions.json'

with open(QJSON, encoding='utf-8') as f:
    QDEF = json.load(f)
SECTIONS = QDEF['sections']

QMAP = {}
for s in SECTIONS:
    for q in s['questions']:
        QMAP[q['id']] = q

CATS = []
for s in SECTIONS:
    for q in s['questions']:
        if q['category'] not in CATS:
            CATS.append(q['category'])

LOW_THRESHOLD = 3.5

def parse_csv(filepath):
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) < 2:
        return None
    return dict(zip(rows[0], rows[1]))

def parse_answer(qid, raw, qdef):
    if raw is None or raw == '' or raw == 'N/A':
        return {'raw': raw or '', 'display': 'N/A（条件隐藏）' if raw == 'N/A' else '未作答', 'score': None}

    qtype = qdef['type']
    parts = str(raw).split('|')
    result = {'raw': raw, 'display': '', 'score': None}

    if qtype in ('radio', 'yesno'):
        result['display'] = raw
    elif qtype == 'radio_text':
        result['display'] = parts[0] + (f'（{parts[1]}）' if len(parts) > 1 and parts[1] else '')
    elif qtype == 'checkbox':
        result['display'] = '、'.join(parts)
    elif qtype in ('rating1_5', 'rating0_10', 'family_rating'):
        try:
            val = int(parts[0])
            result['score'] = val
            max_val = 10 if qtype == 'rating0_10' else 5
            result['display'] = f'{val} / {max_val}'
        except:
            result['display'] = raw
    elif qtype == 'rating_text':
        try:
            val = int(parts[0])
            result['score'] = val
            result['display'] = f'{val} / 5' + (f'（{parts[1]}）' if len(parts) > 1 and parts[1] else '')
        except:
            result['display'] = raw
    elif qtype == 'rating_yesno':
        try:
            val = int(parts[0])
            result['score'] = val
            yn = parts[1] if len(parts) > 1 else ''
            yl = qdef.get('yesnoLabel', '')
            if yn and yl:
                result['display'] = f'{val} / 5（{yl}{yn}）'
            elif yn:
                result['display'] = f'{val} / 5（{yn}）'
            else:
                result['display'] = f'{val} / 5'
        except:
            result['display'] = raw
    elif qtype == 'rating_distance':
        d0 = parts[0] if len(parts) > 0 else ''
        d1 = parts[1] if len(parts) > 1 else ''
        try: d0v = int(d0)
        except: d0v = None
        try: d1v = int(d1)
        except: d1v = None
        result['display'] = f'1米内 {d0}/5，3米外 {d1}/5'
        result['scores'] = [d0v, d1v]
    elif qtype == 'text':
        result['display'] = raw
    else:
        result['display'] = raw
    return result

def compute_category_scores(data):
    cats = {}
    for cat in CATS:
        cats[cat] = {'sum': 0, 'count': 0, 'total': 0}

    for s in SECTIONS:
        for q in s['questions']:
            cat = q['category']
            col = f'{q["id"]}_{cat}'
            cats[cat]['total'] += 1
            if col not in data:
                continue
            parsed = parse_answer(q['id'], data[col], q)
            if parsed.get('score') is not None:
                cats[cat]['sum'] += parsed['score']
                cats[cat]['count'] += 1
            elif parsed.get('scores'):
                for sc in parsed['scores']:
                    if sc is not None:
                        cats[cat]['sum'] += sc
                        cats[cat]['count'] += 1

    result = {}
    for cat, d in cats.items():
        avg = d['sum'] / d['count'] if d['count'] > 0 else None
        result[cat] = {'avg': avg, 'count': d['count'], 'total': d['total'],
                        'low': avg is not None and avg < LOW_THRESHOLD}
    return result

def score_color(avg):
    """返回得分对应的颜色"""
    if avg is None:
        return '#7a7f7c'
    if avg >= 4.5:
        return '#16a34a'  # green
    if avg >= 3.5:
        return '#0f766e'  # teal
    if avg >= 2.5:
        return '#92400e'  # amber
    return '#b91c1c'  # red

def score_bg(avg):
    """返回得分对应的背景色"""
    if avg is None:
        return '#f3f4f6'
    if avg >= 4.5:
        return '#dcfce7'
    if avg >= 3.5:
        return '#ccfbf1'
    if avg >= 2.5:
        return '#fef3c7'
    return '#fef2f2'

def score_bar_html(avg, max_val=5):
    """生成得分条 HTML"""
    if avg is None:
        return '<span style="color:#b8bdba;font-style:italic">无打分题</span>'
    pct = avg / max_val * 100
    color = score_color(avg)
    bg = score_bg(avg)
    return f'''<span style="display:inline-flex;align-items:center;gap:8px">
      <span style="display:inline-block;width:80px;height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden">
        <span style="display:block;height:100%;width:{pct:.0f}%;background:{color};border-radius:4px"></span>
      </span>
      <span style="font-weight:600;color:{color}">{avg:.2f}</span>
      <span style="color:#7a7f7c;font-size:12px">/ {max_val}</span>
    </span>'''

def generate_report(datasets, output_path):
    n = len(datasets)
    is_multi = n > 1

    cross_cat = {}
    nps_values = []
    nps_promoters = nps_passives = nps_detractors = 0

    for ds in datasets:
        for cat, d in ds['cat_scores'].items():
            if cat not in cross_cat:
                cross_cat[cat] = {'sum': 0, 'count': 0, 'total': d['total']}
            if d['avg'] is not None:
                cross_cat[cat]['sum'] += d['avg']
                cross_cat[cat]['count'] += 1
        try:
            nps_val = int(ds['data'].get('NPS', ''))
            nps_values.append(nps_val)
            if nps_val >= 9: nps_promoters += 1
            elif nps_val >= 7: nps_passives += 1
            else: nps_detractors += 1
        except: pass

    # ── CSS (matching reference HTML) ──
    css = '''
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f4f6f5;--surface:#fff;--bd:#e2e5e3;--bd2:#cfd3d0;
  --text:#1a1d1b;--muted:#7a7f7c;--faint:#b8bdba;
  --primary:#1a5632;--primary-light:#e8f2ec;--primary-bd:#7ab894;
  --accent:#0f766e;--accent-bg:#f0fdfa;
  --warn:#92400e;--warn-bg:#fffbeb;--warn-bd:#fbbf24;
  --danger:#b91c1c;--danger-bg:#fef2f2;
  --r:10px;--rl:14px;
  --shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04)
}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans SC","Helvetica Neue",Arial,sans-serif;background:var(--bg);color:var(--text);font-size:15px;line-height:1.65;min-height:100vh;padding:20px}
.app{max-width:640px;margin:0 auto}
.hdr{background:linear-gradient(135deg,var(--primary),#2d7a4a);color:#fff;border-radius:var(--rl);padding:18px 20px;margin-bottom:14px;box-shadow:var(--shadow)}
.hdr h1{font-size:17px;font-weight:600;margin-bottom:4px}
.hdr .sub{font-size:12px;opacity:.85}
.card{background:var(--surface);border:1px solid var(--bd);border-radius:var(--rl);padding:16px 18px;margin-bottom:12px;box-shadow:var(--shadow)}
.section-title{font-size:15px;font-weight:600;color:var(--primary);margin-bottom:4px;padding-bottom:8px;border-bottom:2px solid var(--primary-light);display:flex;align-items:center;gap:8px}
.section-title .num{background:var(--primary);color:#fff;width:24px;height:24px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0}
.result-summary{background:var(--accent-bg);border:1px solid #99f6e4;border-radius:var(--rl);padding:14px 16px}
.result-summary h3{font-size:14px;color:var(--accent);margin-bottom:8px}
.score-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #ccfbf1;font-size:13px}
.score-row:last-child{border-bottom:none}
.score-row .label{color:var(--text)}
.meta-row{display:flex;flex-wrap:wrap;gap:8px 24px;font-size:14px;margin-bottom:8px}
.meta-row b{color:var(--primary)}
.review-item{padding:8px 0;border-bottom:1px solid var(--bd);font-size:13px}
.review-item:last-child{border-bottom:none}
.review-item .q-label{color:var(--muted);font-size:11px;margin-bottom:2px}
.review-item .q-answer{font-weight:500}
.review-item .q-answer.empty{color:var(--faint);font-style:italic}
.section-header{background:var(--primary-light);padding:8px 12px;border-radius:6px;font-size:14px;font-weight:bold;color:var(--primary);margin:12px 0 4px}
.low-flag{display:inline-block;background:var(--danger-bg);color:var(--danger);padding:2px 8px;border-radius:4px;font-size:11px;margin-left:8px}
.nps-box{display:inline-block;padding:8px 16px;border-radius:8px;background:var(--accent-bg);font-size:14px;margin:4px 8px 4px 0}
@media print{body{background:#fff;padding:0}.app{max-width:100%;padding:0}.card{box-shadow:none;border:1px solid #ccc;break-inside:avoid}.hdr{background:var(--primary)!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
'''

    parts = []
    parts.append(f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>TE102 问卷报告 - {datetime.now().strftime('%Y-%m-%d')}</title>
<style>{css}</style>
</head>
<body>
<div class="app">
''')

    title = 'TE102 助听器用户内测问卷报告' if is_multi else 'TE102 助听器用户内测问卷 — 单份报告'
    subtitle = f'共 {n} 份问卷 | 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}'
    parts.append(f'<div class="hdr"><h1>{title}</h1><div class="sub">{subtitle}</div></div>')

    # ── 多份汇总 ──
    if is_multi:
        parts.append('<div class="card"><div class="section-title"><span class="num">📊</span> 跨受访者汇总</div>')
        parts.append('<div class="result-summary"><h3>各维度平均得分（1-5 分制）</h3>')
        for cat in CATS:
            d = cross_cat.get(cat, {'sum':0,'count':0,'total':0})
            avg = d['sum'] / d['count'] if d['count'] > 0 else None
            parts.append(f'<div class="score-row"><span class="label">{cat}</span>'
                        f'<span style="display:flex;align-items:center;gap:8px">'
                        f'{score_bar_html(avg)}'
                        f'<span style="color:#7a7f7c;font-size:12px">（{d["count"]}/{d["total"]} 题）</span>'
                        f'</span></div>')
        if nps_values:
            nps_avg = sum(nps_values) / len(nps_values)
            nps_score = round((nps_promoters - nps_detractors) / len(nps_values) * 100)
            nps_color = score_color(nps_avg)
            parts.append(f'<div class="score-row" style="margin-top:8px;border-top:2px solid #99f6e4;padding-top:10px">'
                        f'<span class="label">推荐意愿 (NPS 0-10)</span>'
                        f'<span style="font-weight:600;color:{nps_color}">{nps_avg:.1f} / 10</span></div>')
        parts.append('</div>')

        if nps_values:
            parts.append(f'<div style="margin-top:12px">'
                        f'<div class="nps-box">NPS 指数：<b>{nps_score}</b></div>'
                        f'<div class="nps-box">推荐者 {nps_promoters} / 被动者 {nps_passives} / 贬损者 {nps_detractors}</div>'
                        f'</div>')
        parts.append('</div>')

    # ── 逐份详情 ──
    for idx, ds in enumerate(datasets):
        data = ds['data']
        fname = ds['filename']
        subject = data.get('受试者编号', f'#{idx+1}')
        date = data.get('测试日期', '')
        tester = data.get('测试员', '')
        phone = data.get('联系电话/邮箱', data.get('联系电话', ''))
        note = data.get('备注', '')

        parts.append(f'<div class="card"><div class="section-title"><span class="num">📋</span> {subject} {date}</div>')
        parts.append(f'<div class="meta-row"><span><b>来源：</b>{fname}</span></div>')
        parts.append(f'<div class="meta-row"><span><b>受试者编号：</b>{subject}</span><span><b>测试日期：</b>{date}</span></div>')
        parts.append(f'<div class="meta-row"><span><b>测试员：</b>{tester}</span><span><b>联系电话/邮箱：</b>{phone}</span></div>')
        if note:
            parts.append(f'<div class="meta-row"><span><b>备注：</b>{note}</span></div>')

        # 分类得分
        cs = ds['cat_scores']
        parts.append('<div class="result-summary" style="margin-top:12px"><h3>各维度平均得分（1-5 分制）</h3>')
        for cat in CATS:
            d = cs.get(cat, {'avg':None,'count':0,'total':0})
            avg = d['avg']
            parts.append(f'<div class="score-row"><span class="label">{cat}</span>'
                        f'<span style="display:flex;align-items:center;gap:8px">'
                        f'{score_bar_html(avg)}'
                        f'<span style="color:#7a7f7c;font-size:12px">（{d["count"]}/{d["total"]} 题）</span>'
                        f'</span></div>')
        # NPS
        try:
            nps_val = int(data.get('NPS', ''))
            nps_color = score_color(nps_val) if nps_val < 6 else score_color(nps_val * 0.5)
            parts.append(f'<div class="score-row" style="margin-top:8px;border-top:2px solid #99f6e4;padding-top:10px">'
                        f'<span class="label">推荐意愿 (NPS 0-10)</span>'
                        f'<span style="font-weight:600;color:{score_color(nps_val) if nps_val >= 6 else "#b91c1c"}">{nps_val} / 10</span></div>')
        except:
            parts.append('<div class="score-row" style="margin-top:8px;border-top:2px solid #99f6e4;padding-top:10px">'
                        '<span class="label">推荐意愿 (NPS 0-10)</span>'
                        '<span style="color:#b8bdba;font-style:italic">未作答</span></div>')
        parts.append('</div></div>')

        # 逐题详情
        parts.append('<div class="card"><div class="section-title"><span class="num">📝</span> 答题详情</div>')
        num = 0
        for s in SECTIONS:
            parts.append(f'<div class="section-header">{s["title"]}</div>')
            for q in s['questions']:
                num += 1
                qid = q['id']
                col = f'{qid}_{q["category"]}'
                raw = data.get(col, '')
                parsed = parse_answer(qid, raw, q)
                disp = parsed['display']
                empty = disp.startswith('未作答') or disp == 'N/A（条件隐藏）'
                ans_cls = 'empty' if empty else ''
                low_flag = ''
                if parsed.get('score') is not None and parsed['score'] < 3:
                    low_flag = '<span class="low-flag">低分</span>'
                elif parsed.get('scores'):
                    if any(sc is not None and sc < 3 for sc in parsed['scores']):
                        low_flag = '<span class="low-flag">低分</span>'

                # 得分着色
                ans_style = ''
                if parsed.get('score') is not None:
                    sc = parsed['score']
                    if sc >= 4:
                        ans_style = f'color:{score_color(sc)};font-weight:600'
                    elif sc < 3:
                        ans_style = f'color:{score_color(sc)};font-weight:600'

                parts.append(f'<div class="review-item">'
                            f'<div class="q-label">第 {num} · {q["category"]} · {qid}{low_flag}</div>'
                            f'<div style="font-size:12px;color:var(--muted);margin-bottom:2px">{q["text"]}</div>'
                            f'<div class="q-answer {ans_cls}" style="{ans_style}">{disp}</div>'
                            f'</div>')
        parts.append('</div>')

    parts.append('</div></body></html>')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(''.join(parts))
    print(f'✓ 报告已生成：{output_path}')

def main():
    parser = argparse.ArgumentParser(description='TE102 问卷 CSV → 报告生成器')
    parser.add_argument('files', nargs='+', help='CSV 文件路径')
    parser.add_argument('-o', '--output', default=None, help='输出 HTML 文件名')
    args = parser.parse_args()

    csv_files = []
    for pattern in args.files:
        matched = glob.glob(pattern)
        if matched:
            csv_files.extend(matched)
        elif os.path.exists(pattern):
            csv_files.append(pattern)
        else:
            print(f'⚠ 文件不存在：{pattern}')

    if not csv_files:
        print('未找到 CSV 文件')
        sys.exit(1)

    seen = set()
    csv_files = [f for f in csv_files if not (f in seen or seen.add(f))]

    print(f'找到 {len(csv_files)} 份 CSV：')
    for f in csv_files:
        print(f'  - {f}')

    datasets = []
    for f in csv_files:
        data = parse_csv(f)
        if data is None:
            print(f'⚠ 跳过（空文件）：{f}')
            continue
        cs = compute_category_scores(data)
        datasets.append({'data': data, 'filename': os.path.basename(f), 'cat_scores': cs})

    if not datasets:
        print('无有效数据')
        sys.exit(1)

    if args.output:
        output = args.output
    elif len(datasets) == 1:
        output = f'{Path(csv_files[0]).stem}_report.html'
    else:
        output = 'all_reports.html'

    generate_report(datasets, output)

if __name__ == '__main__':
    main()
