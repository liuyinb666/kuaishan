#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC28 预测机器人 · 终极缝合版
- 安全：使用 Bot Token，无封号风险
- 付费：卡密激活 + 订阅推送
- 智能：动态 Y 值算法，自动回测选优
- 交互：回复排行榜消息切换算法
"""

import os
import json
import time
import random
import string
import asyncio
import itertools
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import requests
from telethon import TelegramClient, events

# ============================================================
# 配置（所有敏感信息从环境变量读取）
# ============================================================
API_ID = int(os.environ.get('API_ID', '123456'))
API_HASH = os.environ.get('API_HASH', 'your_api_hash')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '7123456789:AAFxxxxxxxxxxxxx')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '123456789'))  # 你的 Telegram 用户 ID

DATA_API_URL = 'https://super.pc28998.com/history/JND28'  # 可换成其他数据源
CHECK_INTERVAL = 15          # 自动监控间隔（秒）
MIN_MATCH = 5                # Y值匹配最小样本数
RANK_BACK_PERIODS = 50       # 回测期数（用于排行榜）

# ============================================================
# 卡密系统（完全复制第一个文件）
# ============================================================
class CardSystem:
    def __init__(self):
        self.cards_file = 'cards.json'
        self.users_file = 'users.json'
        self.cards = self.load_cards()
        self.users = self.load_users()

    def load_cards(self):
        if os.path.exists(self.cards_file):
            with open(self.cards_file, 'r') as f:
                return json.load(f)
        return {}

    def save_cards(self):
        with open(self.cards_file, 'w') as f:
            json.dump(self.cards, f, indent=2)

    def load_users(self):
        if os.path.exists(self.users_file):
            with open(self.users_file, 'r') as f:
                return json.load(f)
        return {}

    def save_users(self):
        with open(self.users_file, 'w') as f:
            json.dump(self.users, f, indent=2)

    def generate_cards(self, count: int, days: int, prefix: str = 'PC28') -> List[str]:
        new_cards = []
        for _ in range(count):
            code = f"{prefix}-{self._random_str(4)}-{self._random_str(4)}-{self._random_str(4)}"
            self.cards[code] = {
                'days': days,
                'used': False,
                'used_by': None,
                'used_at': None,
                'created': datetime.now().isoformat()
            }
            new_cards.append(code)
        self.save_cards()
        return new_cards

    def _random_str(self, length: int) -> str:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def activate(self, user_id: int, card_code: str) -> Tuple[bool, str]:
        card_code = card_code.strip().upper()
        if card_code not in self.cards:
            return False, "❌ 卡密无效，请检查后重试"
        card = self.cards[card_code]
        if card['used']:
            return False, f"❌ 该卡密已被使用（{card['used_at']}）"
        expire_date = datetime.now() + timedelta(days=card['days'])
        card['used'] = True
        card['used_by'] = user_id
        card['used_at'] = datetime.now().isoformat()
        user_id_str = str(user_id)
        if user_id_str not in self.users:
            self.users[user_id_str] = {
                'activated': False,
                'expire_date': None,
                'history': []
            }
        user = self.users[user_id_str]
        if user['activated'] and user['expire_date']:
            old_expire = datetime.fromisoformat(user['expire_date'])
            if old_expire > datetime.now():
                expire_date = old_expire + timedelta(days=card['days'])
        user['activated'] = True
        user['expire_date'] = expire_date.isoformat()
        user['history'].append({
            'card': card_code,
            'days': card['days'],
            'activated_at': datetime.now().isoformat()
        })
        self.save_cards()
        self.save_users()
        return True, f"✅ 激活成功！到期时间：{expire_date.strftime('%Y-%m-%d %H:%M')}（{card['days']}天）"

    def check_user(self, user_id: int) -> Tuple[bool, str]:
        user_id_str = str(user_id)
        if user_id_str not in self.users:
            return False, "❌ 您还未激活，请使用 /activate 卡密 激活"
        user = self.users[user_id_str]
        if not user['activated']:
            return False, "❌ 您还未激活"
        if user['expire_date']:
            expire = datetime.fromisoformat(user['expire_date'])
            if expire < datetime.now():
                return False, f"❌ 已过期（{expire.strftime('%Y-%m-%d')}），请续费"
            remaining = expire - datetime.now()
            days = remaining.days
            hours = remaining.seconds // 3600
            return True, f"✅ 有效期至 {expire.strftime('%Y-%m-%d %H:%M')}（剩余{days}天{hours}小时）"
        return False, "❌ 状态异常"

    def get_all_users(self) -> List[Dict]:
        active_users = []
        for uid, info in self.users.items():
            if info['activated'] and info['expire_date']:
                expire = datetime.fromisoformat(info['expire_date'])
                remaining = (expire - datetime.now()).days
                active_users.append({
                    'user_id': int(uid),
                    'expire_date': info['expire_date'],
                    'remaining_days': remaining,
                    'is_active': expire > datetime.now()
                })
        return active_users

# ============================================================
# Y值预测核心算法（从第二个文件移植）
# ============================================================
def get_combo(total: int) -> str:
    total = max(0, min(27, total))
    return ("大" if total >= 14 else "小") + ("单" if total % 2 == 1 else "双")

def get_opposite(combo: str) -> str:
    m = {"小单": "大双", "小双": "大单", "大单": "小双", "大双": "小单"}
    return m.get(combo, "小单")

def get_y_values(record: dict, y_set: set) -> dict:
    """计算一组Y值余数"""
    s = record['total']
    return {div: s % div for div in y_set}

def match_y_set(record: dict, latest_y_dict: dict) -> bool:
    for div, rem in latest_y_dict.items():
        if record['total'] % div != rem:
            return False
    return True

def predict_by_y_set(data: List[dict], y_set: set) -> Optional[Tuple[str, List[str], List[int]]]:
    """
    基于给定Y值组合进行预测
    返回：(杀组, [双组1, 双组2], [特码1..4])
    """
    if len(data) < 10 or not y_set:
        return None
    latest = data[-1]
    latest_y_dict = get_y_values(latest, y_set)

    # 匹配历史中Y值完全一致的期数（除了最新一期）
    matched_indices = []
    for i in range(len(data) - 1):
        if match_y_set(data[i], latest_y_dict):
            matched_indices.append(i)

    # 如果匹配样本太少，逐步丢弃Y值（从最大的开始），直到样本足够
    current_set = sorted(y_set, reverse=True)
    while len(matched_indices) < MIN_MATCH and len(current_set) > 1:
        current_set.pop()
        new_y_dict = {div: latest_y_dict[div] for div in current_set}
        matched_indices = [i for i in range(len(data)-1) if match_y_set(data[i], new_y_dict)]
        if len(matched_indices) >= MIN_MATCH:
            break

    # 极端情况：只剩一个除数也凑不够，就用最后一个除数强行匹配
    if len(matched_indices) < MIN_MATCH and current_set:
        last_div = current_set[0]
        matched_indices = [i for i in range(len(data)-1) if data[i]['total'] % last_div == latest_y_dict[last_div]]

    if len(matched_indices) < MIN_MATCH:
        return None

    # 统计这些匹配期的下一期组合
    next_combos = []
    for idx in matched_indices:
        if idx + 1 < len(data):
            next_combos.append(data[idx + 1]['combo'])
    if not next_combos:
        return None

    combo_counts = Counter(next_combos)
    sorted_combos = combo_counts.most_common()

    # 双组：取前两个出现最多的组合
    double_groups = [sorted_combos[0][0]]
    if len(sorted_combos) > 1:
        double_groups.append(sorted_combos[1][0])
    else:
        double_groups.append(get_opposite(double_groups[0]))
    if double_groups[0] == double_groups[1]:
        double_groups[1] = get_opposite(double_groups[0])

    # 杀组：取出现最少的组合，或缺失的组合
    all_four = ["小单", "小双", "大单", "大双"]
    if len(sorted_combos) >= 4:
        kill_group = sorted_combos[-1][0]
    else:
        present = set(c for c, _ in sorted_combos)
        missing = [c for c in all_four if c not in present]
        kill_group = missing[0] if missing else get_opposite(double_groups[0])

    # 特码：用“交换法”根据Y值推算
    tema = tema_by_y_swap(data, latest, y_set)
    return kill_group, double_groups, tema

def tema_by_y_swap(data: List[dict], current: dict, y_set: set) -> List[int]:
    """
    根据Y值交换个位/十位/百位来生成特码候选
    """
    cur_nums = [current['a'], current['b'], current['c']]
    cur_sum = current['total']
    candidates = set()
    max_lookback = min(200, len(data) - 1)

    for y_div in y_set:
        cur_y = cur_sum % y_div
        ref = None
        # 向前找第一个余数相同的期
        for i in range(len(data)-2, max(len(data)-max_lookback, -1), -1):
            if data[i]['total'] % y_div == cur_y:
                ref = data[i]
                break
        if ref is None:
            continue
        ref_nums = [ref['a'], ref['b'], ref['c']]
        pos = (y_div - 1) % 3  # 将除数映射到三个位置（2→1, 3→2, 4→0, 5→1, 6→2, 7→0）
        # 方案1：将当前期对应位置替换为参考期对应位置
        new_nums = cur_nums.copy()
        new_nums[pos] = ref_nums[pos]
        candidates.add(sum(new_nums) % 28)
        # 方案2：将参考期对应位置替换为当前期对应位置
        new_nums2 = ref_nums.copy()
        new_nums2[pos] = cur_nums[pos]
        candidates.add(sum(new_nums2) % 28)

    tema = sorted(candidates)[:4]
    # 补位：如果不足4个，用当前和值附近的数填充
    while len(tema) < 4:
        base = cur_sum % 28
        for i in range(1, 28):
            v = (base + i) % 28
            if v not in tema:
                tema.append(v)
                break
    return tema[:4]

def search_best_y_sets(data: List[dict], back_periods: int, min_match: int = 5) -> List[Tuple[set, float, float, int, int, int]]:
    """
    回测所有Y值组合（2~7除数的所有非空子集），按综合胜率排序
    返回：[(y_set, 杀组胜率, 双组胜率, 杀中次数, 双中次数, 总测试次数), ...]
    """
    all_y = [2,3,4,5,6,7]
    subsets = []
    for r in range(1, len(all_y)+1):
        subsets.extend(itertools.combinations(all_y, r))

    results = []
    for y_combo in subsets:
        y_set = set(y_combo)
        correct_kill = 0
        correct_double = 0
        total = 0
        start = max(10, len(data) - back_periods)
        for i in range(start, len(data)):
            test_data = data[:i]
            if len(test_data) < 10:
                continue
            res = predict_by_y_set(test_data, y_set)
            if res is None:
                continue
            kill, doubles, _ = res
            actual = data[i]
            total += 1
            if actual['combo'] != kill:
                correct_kill += 1
            if actual['combo'] in doubles:
                correct_double += 1
        if total == 0:
            continue
        kill_rate = correct_kill / total
        double_rate = correct_double / total
        results.append((y_set, kill_rate, double_rate, correct_kill, correct_double, total))

    # 按综合期望值（杀+双）/2 降序排列
    results.sort(key=lambda x: (x[1] + x[2]) / 2, reverse=True)
    return results

def auto_predict(data: List[dict]) -> Optional[Tuple[str, List[str], List[int], set]]:
    """
    自动选择最优Y值组合进行预测
    返回：(杀组, 双组列表, 特码列表, 使用的y_set)
    """
    if len(data) < 50:
        # 数据不足时用默认 {3,4,5}
        y_set = {3,4,5}
        res = predict_by_y_set(data, y_set)
        if res:
            return (*res, y_set)
        return None

    best = search_best_y_sets(data, min(RANK_BACK_PERIODS, len(data)-10))
    if not best:
        return None
    y_set = best[0][0]      # 最优Y值组合
    kill, doubles, tema = predict_by_y_set(data, y_set)
    if kill and doubles and tema:
        return kill, doubles, tema, y_set
    return None

# ============================================================
# 数据管理
# ============================================================
class DataManager:
    def __init__(self):
        self.data_file = 'pc28_data.json'
        self.data = self.load()

    def load(self) -> List[Dict]:
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []

    def save(self):
        if len(self.data) > 500:
            self.data = self.data[-500:]
        with open(self.data_file, 'w') as f:
            json.dump(self.data, f, indent=2)

    def fetch_and_update(self) -> int:
        try:
            resp = requests.get(DATA_API_URL, headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
                'Referer': 'https://super.pc28998.com/'
            }, timeout=15)
            data = resp.json()
            if data.get('code') != 1 or 'data' not in data:
                return 0
            existing = {d['expect'] for d in self.data}
            added = 0
            for item in data['data']:
                if item['expect'] not in existing:
                    parts = item['opencode'].split(',')
                    if len(parts) == 3:
                        a, b, c = int(parts[0]), int(parts[1]), int(parts[2])
                        total = a + b + c
                        self.data.append({
                            'expect': item['expect'],
                            'a': a, 'b': b, 'c': c,
                            'total': total,
                            'combo': get_combo(total),
                            'is_big': total >= 14,
                            'is_single': total % 2 == 1,
                            'yu5': total % 5
                        })
                        existing.add(item['expect'])
                        added += 1
            if added > 0:
                self.data.sort(key=lambda x: int(x['expect']))
                self.save()
            return added
        except Exception as e:
            print(f"数据获取失败: {e}")
            return 0

# ============================================================
# 格式化输出
# ============================================================
def format_prediction(period: str, kill: str, doubles: List[str], tema: List[int]) -> str:
    short = str(period)[-2:]
    code_str = '/'.join(f"{c:02d}" for c in tema)
    text = f"🎯 **{short}.杀{kill} {doubles[0]}{doubles[1]} {code_str}**\n\n"
    text += f"📊 预测期号：{period}期\n"
    text += f"🔴 杀组：{kill}\n"
    text += f"🟢 双组：{' '.join(doubles)}\n"
    text += f"💎 特码：{'/'.join(f'{c:02d}' for c in tema)}\n"
    return text

# ============================================================
# 主机器人
# ============================================================
card_system = CardSystem()
data_manager = DataManager()
monitor_users = set()          # 订阅用户集合
algorithm_map = {}             # 缓存排行榜消息ID → Y值组合列表
bot = TelegramClient('pc28_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

def require_activation(func):
    async def wrapper(event):
        user_id = event.sender_id
        is_valid, msg = card_system.check_user(user_id)
        if not is_valid:
            await event.respond(msg)
            return
        await func(event)
    return wrapper

# ---------- 基础命令 ----------
@bot.on(events.NewMessage(pattern='/start'))
async def cmd_start(event):
    user_id = event.sender_id
    is_valid, msg = card_system.check_user(user_id)
    text = "🤖 **PC28预测机器人（终极版）**\n\n"
    text += "📋 命令列表：\n"
    text += "/activate 卡密 - 激活机器人\n"
    text += "/predict - 手动预测（自动最优算法）\n"
    text += "/rank - 查看算法排行榜\n"
    text += "/status - 查看状态\n"
    text += "/sub - 订阅自动推送\n"
    text += "/unsub - 取消订阅\n"
    text += "/help - 帮助\n\n"
    if is_valid:
        text += f"✅ {msg}\n"
    else:
        text += f"{msg}\n"
    await event.respond(text)

@bot.on(events.NewMessage(pattern='/activate'))
async def cmd_activate(event):
    parts = event.text.split()
    if len(parts) < 2:
        await event.respond("使用方法：/activate PC28-XXXX-XXXX-XXXX")
        return
    card_code = parts[1]
    user_id = event.sender_id
    success, msg = card_system.activate(user_id, card_code)
    await event.respond(msg)

@bot.on(events.NewMessage(pattern='/predict'))
@require_activation
async def cmd_predict(event):
    if len(data_manager.data) < 10:
        await event.respond(f"⚠️ 数据不足（当前{len(data_manager.data)}期），请等待数据更新...")
        return
    result = auto_predict(data_manager.data)
    if result is None:
        await event.respond("❌ 预测失败，数据不足或算法异常")
        return
    kill, doubles, tema, y_set = result
    latest = data_manager.data[-1]
    next_period = str(int(latest['expect']) + 1)
    text = format_prediction(next_period, kill, doubles, tema)
    text += f"\n📌 使用Y值：{sorted(y_set)}"
    await event.respond(text, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/rank'))
@require_activation
async def cmd_rank(event):
    if len(data_manager.data) < 20:
        await event.respond("⚠️ 数据不足，至少需要20期才能排行")
        return
    back = min(RANK_BACK_PERIODS, len(data_manager.data) - 10)
    results = search_best_y_sets(data_manager.data, back, MIN_MATCH)
    if not results:
        await event.respond("❌ 回测失败，请稍后重试")
        return
    topN = results[:10]
    lines = []
    for i, (y_set, kr, dr, kh, dh, tot) in enumerate(topN, 1):
        exp = (kr + dr) / 2
        # 中文数字
        cn = ['一','二','三','四','五','六','七','八','九','十'][i-1]
        lines.append(f"算法{cn}：Y{list(y_set)} 杀{kr*100:.0f}%（{kh}/{tot}）双{dr*100:.0f}%（{dh}/{tot}）期望{exp*100:.0f}%")
    sent = await event.respond("📊 **算法排行榜（近{}期）**\n\n".format(back) + '\n'.join(lines), parse_mode='markdown')
    # 缓存排行榜对应的算法列表（用于后续引用回复）
    algorithm_map[(event.chat_id, sent.id)] = [ys for ys, _, _, _, _, _ in topN]

@bot.on(events.NewMessage(pattern='/status'))
@require_activation
async def cmd_status(event):
    user_id = event.sender_id
    is_valid, msg = card_system.check_user(user_id)
    text = f"📊 **系统状态**\n\n"
    text += f"💾 数据量：{len(data_manager.data)} 条\n"
    text += f"🤖 订阅用户：{len(monitor_users)} 人\n"
    if data_manager.data:
        latest = data_manager.data[-1]
        text += f"📅 最新期：{latest['expect']}\n"
        text += f"🔢 号码：{latest['a']}+{latest['b']}+{latest['c']}={latest['total']}\n"
        text += f"🏷️ 组合：{latest['combo']}\n"
    text += f"\n{msg}"
    await event.respond(text)

@bot.on(events.NewMessage(pattern='/sub'))
@require_activation
async def cmd_sub(event):
    monitor_users.add(event.sender_id)
    await event.respond("✅ 已订阅自动推送，每期开奖后自动发送预测")

@bot.on(events.NewMessage(pattern='/unsub'))
async def cmd_unsub(event):
    monitor_users.discard(event.sender_id)
    await event.respond("✅ 已取消自动推送")

@bot.on(events.NewMessage(pattern='/help'))
async def cmd_help(event):
    text = "📋 **帮助**\n\n"
    text += "1️⃣ 首先使用 /activate 卡密 激活\n"
    text += "2️⃣ 激活后可使用 /predict 预测（自动最优算法）\n"
    text += "3️⃣ 使用 /rank 查看排行榜，然后 **回复排行榜消息** 发送 `算法三` 调用对应算法\n"
    text += "4️⃣ 使用 /sub 订阅自动推送\n"
    text += "5️⃣ 机器人会自动监控数据，推送预测结果\n\n"
    text += "🔑 获取卡密请联系管理员"
    await event.respond(text)

# ---------- 引用回复处理（选择算法） ----------
@bot.on(events.NewMessage)
async def handle_algorithm_selection(event):
    if not event.is_reply:
        return
    # 只处理回复排行榜消息的情况
    key = (event.chat_id, event.reply_to_msg_id)
    if key not in algorithm_map:
        return
    # 检查回复内容是否是 "算法X"
    import re
    match = re.match(r'^算法([一二三四五六七八九十])$', event.text.strip())
    if not match:
        return
    cn = match.group(1)
    cn_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
    idx = cn_map.get(cn, 0)
    if idx < 1 or idx > len(algorithm_map[key]):
        await event.reply("❌ 序号超出范围")
        return
    y_set = algorithm_map[key][idx-1]
    # 使用该Y值进行预测
    data = data_manager.data
    if len(data) < 10:
        await event.reply("⚠️ 数据不足")
        return
    res = predict_by_y_set(data, y_set)
    if res is None:
        await event.reply("⚠️ 该算法无法预测")
        return
    kill, doubles, tema = res
    latest = data[-1]
    next_period = str(int(latest['expect']) + 1)
    text = format_prediction(next_period, kill, doubles, tema)
    text += f"\n📌 使用Y值：{sorted(y_set)}"
    await event.reply(text, parse_mode='markdown')

# ---------- 管理员命令 ----------
@bot.on(events.NewMessage(pattern='/admin'))
async def cmd_admin(event):
    if event.sender_id != ADMIN_ID:
        await event.respond("❌ 无权限")
        return
    text = "🔧 **管理员面板**\n\n"
    text += "/gencards 数量 天数 - 生成卡密\n"
    text += "/listusers - 查看激活用户\n"
    text += "/broadcast 消息 - 群发消息\n"
    await event.respond(text)

@bot.on(events.NewMessage(pattern='/gencards'))
async def cmd_gencards(event):
    if event.sender_id != ADMIN_ID:
        return
    parts = event.text.split()
    count = int(parts[1]) if len(parts) > 1 else 5
    days = int(parts[2]) if len(parts) > 2 else 30
    cards = card_system.generate_cards(count, days)
    text = f"✅ 已生成 {count} 张卡密（{days}天）：\n\n"
    text += '\n'.join(f"`{c}`" for c in cards)
    text += "\n\n可直接复制发送给用户"
    await event.respond(text, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/listusers'))
async def cmd_listusers(event):
    if event.sender_id != ADMIN_ID:
        return
    users = card_system.get_all_users()
    if not users:
        await event.respond("暂无激活用户")
        return
    text = f"📊 **激活用户（{len(users)}人）**\n\n"
    for u in sorted(users, key=lambda x: x['remaining_days']):
        status = "✅" if u['is_active'] else "❌"
        text += f"{status} `{u['user_id']}` - 剩余{u['remaining_days']}天\n"
    await event.respond(text, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/broadcast'))
async def cmd_broadcast(event):
    if event.sender_id != ADMIN_ID:
        return
    msg = event.text.replace('/broadcast', '').strip()
    if not msg:
        await event.respond("用法：/broadcast 消息内容")
        return
    users = card_system.get_all_users()
    success = 0
    for u in users:
        if u['is_active']:
            try:
                await bot.send_message(u['user_id'], f"📢 **管理员通知**\n\n{msg}", parse_mode='markdown')
                success += 1
            except:
                pass
    await event.respond(f"✅ 已发送给 {success}/{len(users)} 位活跃用户")

# ---------- 自动监控循环 ----------
async def monitor_loop():
    print("🔄 监控循环启动...")
    last_period = None
    data_manager.fetch_and_update()
    if data_manager.data:
        last_period = data_manager.data[-1]['expect']

    while True:
        try:
            added = data_manager.fetch_and_update()
            if added > 0 and data_manager.data:
                latest = data_manager.data[-1]
                new_period = latest['expect']
                if new_period != last_period:
                    print(f"📡 新数据: {new_period}")
                    last_period = new_period
                    if len(data_manager.data) >= 10:
                        result = auto_predict(data_manager.data)
                        if result:
                            kill, doubles, tema, y_set = result
                            next_period = str(int(latest['expect']) + 1)
                            text = format_prediction(next_period, kill, doubles, tema)
                            text += f"\n📌 使用Y值：{sorted(y_set)}"
                            full_text = f"🔔 **新一期开奖！**\n{latest['expect']}期 {latest['a']}+{latest['b']}+{latest['c']}={latest['total']} {latest['combo']}\n\n" + text
                            for user_id in list(monitor_users):
                                try:
                                    is_valid, _ = card_system.check_user(user_id)
                                    if is_valid:
                                        await bot.send_message(user_id, full_text, parse_mode='markdown')
                                except Exception as e:
                                    print(f"推送失败 {user_id}: {e}")
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"监控错误: {e}")
            await asyncio.sleep(30)

# ============================================================
# 启动
# ============================================================
async def main():
    print("🤖 PC28 终极缝合版启动...")
    asyncio.create_task(monitor_loop())
    print("✅ 机器人已启动，等待消息...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())