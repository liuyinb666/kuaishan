#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC28 定时预测 · GitHub Actions 版
每次运行抓取最新数据 → 自动预测 → 推送到指定用户/群组 → 退出
"""

import os
import asyncio
import itertools
from collections import Counter
from typing import List, Dict, Tuple, Optional

import requests
from telethon import TelegramClient

API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
TARGET_USER_ID = int(os.environ.get('TARGET_USER_ID', 0))

if not API_ID or not API_HASH or not BOT_TOKEN or not TARGET_USER_ID:
    raise Exception("❌ 环境变量缺失")

API_URL = 'http://pc28.help/api/kj.json?nbr=100'
MIN_MATCH_COUNT = 5
RANK_BACK_PERIODS = 50

def get_combo(s):
    s = max(0, min(27, s))
    return ("大" if s >= 14 else "小") + ("单" if s % 2 == 1 else "双")

def get_opposite(c):
    return {"小单": "大双", "小双": "大单", "大单": "小双", "大双": "小单"}.get(c, "小单")

def get_y_values_for_set(d, y_set):
    return {div: d['sum'] % div for div in y_set}

def match_y_set(d, latest_y_dict):
    for div, rem in latest_y_dict.items():
        if d['sum'] % div != rem:
            return False
    return True

def predict_by_y_set(data, y_set):
    if len(data) < 10 or not y_set:
        return None
    latest = data[-1]
    latest_y_dict = get_y_values_for_set(latest, y_set)
    matched_indices = []
    for i in range(len(data)-1):
        if match_y_set(data[i], latest_y_dict):
            matched_indices.append(i)
    current_set = sorted(y_set, reverse=True)
    while len(matched_indices) < MIN_MATCH_COUNT and len(current_set) > 1:
        current_set.pop()
        new_y_dict = {div: latest_y_dict[div] for div in current_set}
        matched_indices = [i for i in range(len(data)-1) if match_y_set(data[i], new_y_dict)]
        if len(matched_indices) >= MIN_MATCH_COUNT:
            break
    if len(matched_indices) < MIN_MATCH_COUNT and current_set:
        last_div = current_set[0]
        matched_indices = [i for i in range(len(data)-1) if data[i]['sum'] % last_div == latest_y_dict[last_div]]
    next_combos = []
    for idx in matched_indices:
        if idx + 1 < len(data):
            next_combos.append(data[idx+1]['combo'])
    if not next_combos:
        return None
    combo_counts = Counter(next_combos)
    sorted_combos = combo_counts.most_common()
    double_groups = [sorted_combos[0][0]]
    if len(sorted_combos) > 1:
        double_groups.append(sorted_combos[1][0])
    else:
        double_groups.append(get_opposite(double_groups[0]))
    if double_groups[0] == double_groups[1]:
        double_groups[1] = get_opposite(double_groups[0])
    all_four = ["小单", "小双", "大单", "大双"]
    if len(sorted_combos) >= 4:
        kill_group = sorted_combos[-1][0]
    else:
        present = set(c for c, _ in sorted_combos)
        missing = [c for c in all_four if c not in present]
        kill_group = missing[0] if missing else get_opposite(double_groups[0])
    tema_codes = tema_by_y_swap_set(data, latest, y_set)
    return kill_group, double_groups, tema_codes

def tema_by_y_swap_set(data, current, y_set):
    cur_nums = [current['a'], current['b'], current['c']]
    cur_sum = current['sum']
    candidates = set()
    max_lookback = min(200, len(data)-1)
    for y_div in y_set:
        cur_y = cur_sum % y_div
        ref = None
        for i in range(len(data)-2, max(len(data)-max_lookback, -1), -1):
            if data[i]['sum'] % y_div == cur_y:
                ref = data[i]
                break
        if ref is None:
            continue
        ref_nums = [ref['a'], ref['b'], ref['c']]
        pos = (y_div - 1) % 3
        new_nums = cur_nums.copy()
        new_nums[pos] = ref_nums[pos]
        candidates.add(sum(new_nums) % 28)
        new_nums2 = ref_nums.copy()
        new_nums2[pos] = cur_nums[pos]
        candidates.add(sum(new_nums2) % 28)
    tema = sorted(candidates)[:4]
    while len(tema) < 4:
        base = cur_sum % 28
        for i in range(1, 28):
            v = (base + i) % 28
            if v not in tema:
                tema.append(v)
                break
    return tema[:4]

def search_best_kill_double(data, back_periods, min_match=5):
    all_y_divisors = [2, 3, 4, 5, 6, 7]
    subsets = []
    for r in range(1, len(all_y_divisors)+1):
        subsets.extend(itertools.combinations(all_y_divisors, r))
    results = []
    for y_combo in subsets:
        y_set = set(y_combo)
        correct_kill = correct_double = total = 0
        for i in range(len(data)-back_periods, len(data)):
            test_data = data[:i]
            if len(test_data) < 10:
                continue
            kill, doubles, _ = predict_by_y_set(test_data, y_set)
            if kill is None:
                continue
            actual = data[i]
            total += 1
            if actual['combo'] != kill:
                correct_kill += 1
            if actual['combo'] in doubles:
                correct_double += 1
        if total == 0:
            continue
        results.append((y_set, correct_kill/total, correct_double/total, correct_kill, correct_double, total))
    results.sort(key=lambda x: (x[1] + x[2]) / 2, reverse=True)
    return results

def auto_predict(data):
    if len(data) < 50:
        y_set = {3, 4, 5}
        result = predict_by_y_set(data, y_set)
        if result:
            return (*result, y_set, y_set)
        return None
    best = search_best_kill_double(data, min(50, len(data)-10))
    if not best:
        return None
    y_set_kd = best[0][0]
    y_set_t = best[0][0]
    kill, doubles, _ = predict_by_y_set(data, y_set_kd)
    _, _, tema = predict_by_y_set(data, y_set_t)
    if kill and doubles and tema:
        return kill, doubles, tema, y_set_kd, y_set_t
    return None

def fetch_api_data():
    try:
        resp = requests.get(API_URL, timeout=15)
        data = resp.json()
        records = []
        if data.get("message") == "success" and "data" in data:
            for item in data["data"]:
                parts = item['number'].split('+')
                if len(parts) == 3:
                    a, b, c = map(int, parts)
                    s = a + b + c
                    records.append({
                        'period': str(item['nbr']),
                        'a': a,
                        'b': b,
                        'c': c,
                        'sum': s,
                        'combo': get_combo(s)
                    })
            records.sort(key=lambda x: int(x['period']))
            return records
    except Exception as e:
        print(f"抓取失败: {e}")
    return None

def format_prediction_line(period, kill, doubles, tema=None, prefix="", suffix=""):
    short = str(period)[-2:]
    if tema:
        base = f"{short}.杀{kill} {doubles[0]}{doubles[1]} {'/'.join(f'{t:02d}' for t in tema)}"
    else:
        base = f"{short}.杀{kill} {doubles[0]}{doubles[1]}"
    lines = []
    if prefix:
        lines.append(prefix)
    lines.append(base)
    if suffix:
        lines.append(suffix)
    return '\n'.join(lines)

async def main():
    print("📡 抓取最新数据...")
    data = fetch_api_data()
    if not data or len(data) < 10:
        print("❌ 数据不足")
        return
    print(f"✅ 获取 {len(data)} 条数据，最新期 {data[-1]['period']}")

    result = auto_predict(data)
    if not result:
        print("❌ 预测失败")
        return

    kill, doubles, tema, _, _ = result
    latest = data[-1]
    next_period = int(latest['period']) + 1
    prediction = format_prediction_line(
        next_period, kill, doubles, tema,
        prefix="📊 预测结果：",
        suffix="⚠️ 仅供参考"
    )
    print(prediction)

    try:
        client = TelegramClient('session', API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        full_msg = f"📊 最新开奖：{latest['period']}期  {latest['a']}+{latest['b']}+{latest['c']}={latest['sum']}  {latest['combo']}\n\n{prediction}"
        await client.send_message(TARGET_USER_ID, full_msg)
        print(f"✅ 已推送到 {TARGET_USER_ID}")
        await client.disconnect()
    except Exception as e:
        print(f"❌ 推送失败: {e}")

if __name__ == '__main__':
    asyncio.run(main())