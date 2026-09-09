# -*- coding: utf-8 -*-
"""
TE102 问卷 CSV → 报告生成器

用法:
  python report.py data.csv                  # 单份报告 (data_report.html)
  python report.py s001.csv s002.csv s003.csv  # 多份汇总 (all_reports.html)
  python report.py *.csv                     # 通配（PowerShell: python report.py *.csv）
  python report.py data.csv -o my_report.html  # 指定输出文件名

功能:
  - 读取与 exportCSV 格式一致的 CSV 文件
  - 解析每题答案（处理 | 分隔的复合格式）
  - 生成 HTML 报告：单份逐题详情 + 多份跨受访者汇总
  - 低分(<3.5)标红、NPS<6 标红
"""
import csv, json, sys, os, glob, argparse
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
QJSON = SCRIPT_DIR / 'questions.json'

# ── 加载问卷定义 ──
with open(QJSON, encoding='utf-8') as f:
    QDEF = json.load(f)
SECTIONS = QDEF['sections']
META = QDEF['meta']

# 构建题目映射
QMAP = {}  # id -> question dict
for s in SECTIONS:
    for q in s['questions']:
        QMAP[q['id']] = q

# 分类顺序
CATS = []
for s in SECTIONS:
    for q in s['questions']:
        if q['category'] not in CATS:
            CATS.append(q['category'])

LOW_THRESHOLD = 3.5

def parse_csv(filepath):
    """读取 CSV，返回 dict（header -> value）"""
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) < 2:
        return None
    headers = rows[0]
    values = rows[1]
    return dict(zip(headers, values))

def parse_answer(qid, raw, qdef):
    """解析 CSV 单元格为结构化答案"""
    if raw is None or raw == '' or raw == 'N/A':
        return {'raw': raw or '', 'display': 'N/A（条件隐藏）' if raw == 'N/A' else '未作答', 'score': None}

    qtype = qdef['type']
    parts = str(raw).split('|')

    result = {'raw': raw, 'display': '', 'score': None}

    if qtype in ('radio', 'yesno'):
        result['display'] = raw
        result['score'] = None
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
            result['display'] = f'{val} / 5' + (f'（{yn}）' if yn else '')
        except:
            result['display'] = raw
    elif qtype == 'rating_distance':
        d0 = parts[0] if len(parts) > 0 else ''
        d1 = parts[1] if len(parts) > 1 else ''
        try:
            d0v = int(d0)
        except:
            d0v = None
        try:
            d1v = int(d1)
        except:
            d1v = None
        result['display'] = f'1米内 {d0}/5，3米外 {d1}/5'
        result['score'] = None
        result['scores'] = [d0v, d1v]
    elif qtype == 'text':
        result['display'] = raw
    else:
        result['display'] = raw

    return result

def compute_category_scores(data):
    """从 CSV 数据计算各分类得分"""
    cats = {}
    for cat in CATS:
        cats[cat] = {'sum': 0, 'count': 0, 'scores': []}

    for s in SECTIONS:
        for q in s['questions']:
            qid = q['id']
            cat = q['category']
            col = f'{qid}_{cat}'
            if col not in data:
                continue
            parsed = parse_answer(qid, data[col], q)
            if parsed.get('score') is not None:
                cats[cat]['sum'] += parsed['score']
                cats[cat]['count'] += 1
                cats[cat]['scores'].append(parsed['score'])
            elif parsed.get('scores'):
                for sc in parsed['scores']:
                    if sc is not None:
                        cats[cat]['sum'] += sc
                        cats[cat]['count'] += 1
                        cats[cat]['scores'].append(sc)

    result = {}
    for cat, d in cats.items():
        avg = d['sum'] / d['count'] if d['count'] > 0 else None
        result[cat] = {
            'avg': avg,
            'count': d['count'],
            'total': d['count'],
            'low': avg is not None and avg < LOW_THRESHOLD
        }
    return result

def generate_report(datasets, output_path):
    """生成 HTML 报告"""
    n = len(datasets)
    is_multi = n > 1

    # ── 汇总统计（多份时）──
    cross_cat = {}
    nps_values = []
    nps_promoters = 0
    nps_passives = 0
    nps_detractors = 0

    for ds in datasets:
        cs = ds['cat_scores']
        for cat, d in cs.items():
            if cat not in cross_cat:
                cross_cat[cat] = {'sum': 0, 'count': 0}
            if d['avg'] is not None:
                cross_cat[cat]['sum'] += d['avg']
                cross_cat[cat]['count'] += 1

        nps_raw = ds['data'].get('NPS', '')
        try:
            nps_val = int(nps_raw)
            nps_values.append(nps_val)
            if nps_val >= 9: nps_promoters += 1
            elif nps_val >= 7: nps_passives += 1
            else: nps_detractors += 1
        except:
            pass

    html_parts = []
    html_parts.append(f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TE102 问卷报告 - {datetime.now().strftime('%Y-%m-%d')}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; background:#f5f5f5; color:#1a2917; line-height:1.6; padding:20px; }}
  .app {{ max-width:900px; margin:0 auto; }}
  .hdr {{ background:#1a5632; color:#fff; padding:24px; border-radius:12px; margin-bottom:20px; }}
  .hdr h1 {{ font-size:20px; margin-bottom:4px; }}
  .hdr p {{ font-size:13px; opacity:.85; }}
  .card {{ background:#fff; border-radius:12px; padding:20px; margin-bottom:16px; box-shadow:0 1px 4px rgba(0,0,0,.08); }}
  .card-title {{ font-size:16px; font-weight:bold; margin-bottom:12px; padding-bottom:8px; border-bottom:2px solid #e5e7eb; }}
  .meta-row {{ display:flex; flex-wrap:wrap; gap:8px 24px; font-size:14px; margin-bottom:8px; }}
  .meta-row b {{ color:#1a5632; }}
  .score-table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  .score-table th {{ text-align:left; padding:8px; background:#f0fdf4; border-bottom:2px solid #d1fae5; }}
  .score-table td {{ padding:8px; border-bottom:1px solid #f3f4f6; }}
  .score-table .low {{ color:#dc2626; font-weight:bold; }}
  .nps-box {{ display:inline-block; padding:8px 16px; border-radius:8px; background:#f0fdf4; font-size:14px; margin:4px 8px 4px 0; }}
  .q-item {{ padding:10px 0; border-bottom:1px solid #f3f4f6; }}
  .q-item:last-child {{ border-bottom:none; }}
  .q-num {{ font-size:12px; color:#6b7280; }}
  .q-text {{ font-size:13px; color:#4b5563; margin:2px 0 4px; }}
  .q-ans {{ font-size:14px; font-weight:500; }}
  .q-ans.empty {{ color:#9ca3af; font-style:italic; }}
  .low-flag {{ display:inline-block; background:#fef2f2; color:#dc2626; padding:2px 8px; border-radius:4px; font-size:12px; margin-left:8px; }}
  .section-header {{ background:#f0fdf4; padding:8px 12px; border-radius:6px; font-size:14px; font-weight:bold; color:#1a5632; margin:12px 0 8px; }}
  @media print {{ body{{background:#fff;padding:0}} .card{{box-shadow:none;border:1px solid #ccc;break-inside:avoid}} }}
</style>
</head>
<body>
<div class="app">
''')

    # ── 标题 ──
    title = f'TE102 助听器用户内测问卷报告' if is_multi else f'TE102 助听器用户内测问卷 — 单份报告'
    subtitle = f'共 {n} 份问卷 | 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}'
    html_parts.append(f'<div class="hdr"><h1>{title}</h1><p>{subtitle}</p></div>')

    # ── 多份汇总 ──
    if is_multi:
        html_parts.append('<div class="card"><div class="card-title">📊 跨受访者汇总</div>')

        # 分类均分
        html_parts.append('<table class="score-table"><thead><tr><th>维度</th><th>平均分</th><th>样本数</th><th>状态</th></tr></thead><tbody>')
        for cat in CATS:
            d = cross_cat.get(cat, {'sum':0,'count':0})
            avg = d['sum'] / d['count'] if d['count'] > 0 else None
            avg_str = f'{avg:.2f}' if avg is not None else '-'
            low_flag = '<span class="low-flag">低分</span>' if avg is not None and avg < LOW_THRESHOLD else ''
            html_parts.append(f'<tr><td>{cat}</td><td class="{("low" if avg is not None and avg < LOW_THRESHOLD else "")}">{avg_str}</td><td>{d["count"]}</td><td>{low_flag}</td></tr>')
        html_parts.append('</tbody></table>')

        # NPS
        if nps_values:
            nps_avg = sum(nps_values) / len(nps_values)
            nps_score = round((nps_promoters - nps_detractors) / len(nps_values) * 100)
            html_parts.append(f'<div style="margin-top:16px"><div class="nps-box">NPS 均分：{nps_avg:.1f}</div>')
            html_parts.append(f'<div class="nps-box">NPS 指数：{nps_score}</div>')
            html_parts.append(f'<div class="nps-box">推荐者({nps_promoters}) / 被动者({nps_passives}) / 贬损者({nps_detractors})</div></div>')

        html_parts.append('</div>')

    # ── 逐份详情 ──
    for idx, ds in enumerate(datasets):
        data = ds['data']
        fname = ds['filename']
        subject = data.get('受试者编号', f'#{idx+1}')
        date = data.get('测试日期', '')
        tester = data.get('测试员', '')
        phone = data.get('联系电话', '')
        note = data.get('备注', '')

        html_parts.append(f'<div class="card"><div class="card-title">📋 {subject} {date}</div>')
        html_parts.append(f'<div class="meta-row"><span><b>来源文件：</b>{fname}</span></div>')
        html_parts.append(f'<div class="meta-row"><span><b>受试者编号：</b>{subject}</span><span><b>测试日期：</b>{date}</span></div>')
        html_parts.append(f'<div class="meta-row"><span><b>测试员：</b>{tester}</span><span><b>联系电话：</b>{phone}</span></div>')
        if note:
            html_parts.append(f'<div class="meta-row"><span><b>备注：</b>{note}</span></div>')

        # 分类得分
        cs = ds['cat_scores']
        html_parts.append('<table class="score-table" style="margin-top:12px"><thead><tr><th>维度</th><th>均分</th><th>题数</th></tr></thead><tbody>')
        for cat in CATS:
            d = cs.get(cat, {'avg':None,'count':0})
            avg = d['avg']
            avg_str = f'{avg:.2f}' if avg is not None else '-'
            cls = 'low' if avg is not None and avg < LOW_THRESHOLD else ''
            html_parts.append(f'<tr><td>{cat}</td><td class="{cls}">{avg_str}</td><td>{d["count"]}</td></tr>')
        html_parts.append('</tbody></table>')

        # NPS
        nps_raw = data.get('NPS', '')
        try:
            nps_val = int(nps_raw)
            nps_cls = 'low' if nps_val < 6 else ''
            html_parts.append(f'<div class="meta-row" style="margin-top:12px"><span><b>推荐意愿(NPS)：</b><span class="{nps_cls}">{nps_val}/10</span></span></div>')
        except:
            html_parts.append(f'<div class="meta-row" style="margin-top:12px"><span><b>推荐意愿(NPS)：</b>未作答</span></div>')

        html_parts.append('</div>')

        # 逐题详情
        html_parts.append('<div class="card"><div class="card-title">📝 答题详情</div>')
        num = 0
        for s in SECTIONS:
            html_parts.append(f'<div class="section-header">{s["title"]}</div>')
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

                html_parts.append(f'<div class="q-item"><span class="q-num">第{num}题 · {qid}</span>{low_flag}')
                html_parts.append(f'<div class="q-text">{q["text"]}</div>')
                html_parts.append(f'<div class="q-ans {ans_cls}">{disp}</div></div>')
        html_parts.append('</div>')

    html_parts.append('</div></body></html>')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(''.join(html_parts))
    print(f'✓ 报告已生成：{output_path}')

def main():
    parser = argparse.ArgumentParser(description='TE102 问卷 CSV → 报告生成器')
    parser.add_argument('files', nargs='+', help='CSV 文件路径（支持通配）')
    parser.add_argument('-o', '--output', default=None, help='输出 HTML 文件名')
    args = parser.parse_args()

    # 展开通配符
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

    # 去重
    seen = set()
    csv_files = [f for f in csv_files if not (f in seen or seen.add(f))]

    print(f'找到 {len(csv_files)} 份 CSV：')
    for f in csv_files:
        print(f'  - {f}')

    datasets = []
    for f in csv_files:
        data = parse_csv(f)
        if data is None:
            print(f'⚠ 跳过（空文件或格式不符）：{f}')
            continue
        cs = compute_category_scores(data)
        datasets.append({'data': data, 'filename': os.path.basename(f), 'cat_scores': cs})

    if not datasets:
        print('无有效数据')
        sys.exit(1)

    if args.output:
        output = args.output
    elif len(datasets) == 1:
        base = Path(csv_files[0]).stem
        output = f'{base}_report.html'
    else:
        output = 'all_reports.html'

    generate_report(datasets, output)

if __name__ == '__main__':
    main()
