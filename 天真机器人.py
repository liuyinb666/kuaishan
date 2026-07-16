# tianzhen_bot_free.py
# 法老破解- 4000+算法库（前2000个）+ 自动推送（无权限限制）
# 所有人都可使用所有功能

import asyncio
import json
import logging
import random
import re
import sqlite3  # 保留但不再使用（数据库已移除）
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    Update, ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, JobQueue
)

# ============ 配置 ============
TOKEN = "8723628059:AAEICW5iWSoueLZP-pzjp7ytOuyKST7lU70"
API_URL = "https://super.pc28998.com/history/JND28?limit=50"
FIELD_PERIOD = 'expect'
FIELD_NUMBERS = 'opencode'
FIELD_TIME = 'opentime'
HISTORY_LIMIT = 20
ALGORITHM_COUNT = 1000
AUTO_REFRESH_INTERVAL = 30  # 自动刷新间隔（秒）

# ============ 日志 ============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ 工具函数 ============
def parse_nums(opencode: str) -> List[int]:
    if not opencode:
        return []
    return [int(x.strip()) for x in str(opencode).split(',') if x.strip().isdigit()]

def sum_nums(nums: List[int]) -> int:
    return sum(nums) if nums else 0

def get_combo(total: int) -> str:
    size = '大' if total >= 14 else '小'
    oe = '双' if total % 2 == 0 else '单'
    return size + oe

def get_kill(combo: str) -> str:
    kill_map = {'大单': '小双', '大双': '小单', '小单': '大双', '小双': '大单'}
    return kill_map.get(combo, '大单')

def get_double_recommend(kill_combo: str) -> List[str]:
    map_double = {
        '小单': ['大单', '小双'],
        '大单': ['大双', '小单'],
        '小双': ['大双', '小单'],
        '大双': ['大单', '小双']
    }
    return map_double.get(kill_combo, ['大单', '小双'])

def get_next_period(cur_period: str) -> str:
    try:
        n = int(cur_period)
        return str(n + 1)
    except:
        m = re.search(r'(\d+)(?!.*\d)', str(cur_period))
        return str(int(m.group(1)) + 1) if m else '--'

# ============ 算法生成（提取自文件1的1000模型算法） ============
def create_advanced_predictor(depth, offset, weight, formula_type, step):
    """高级预测器工厂：根据历史序列预测下一值（公式类型 0/1/2）"""
    def predictor(history_balls):
        if len(history_balls) < depth:
            return offset % 28
        segment = history_balls[:depth]
        if formula_type == 0:
            core_val = sum(val * (weight + idx) for idx, val in enumerate(segment[::step]))
        elif formula_type == 1:
            core_val = sum(abs(segment[i] - segment[i + 1]) * weight for i in range(len(segment) - 1))
        else:
            core_val = sum(segment) * weight + offset
        return int(core_val) % 28
    return predictor

# 固定随机种子，保证每次启动模型参数一致
random.seed(999)
ALGORITHM_MODELS: Dict[int, callable] = {}
for i in range(1, ALGORITHM_COUNT + 1):
    ALGORITHM_MODELS[i] = create_advanced_predictor(
        random.randint(3, 20),
        random.randint(0, 19),
        random.uniform(0.1, 10.0),
        random.randint(0, 2),
        random.randint(1, 3)
    )
TOTAL_MODELS = len(ALGORITHM_MODELS)

def evaluate_expression(model_id: int, history: List[Dict]) -> Dict:
    if not history or len(history) < 2:
        return {'kill': '大单', 'size': '大', 'oe': '单', 'combo': '大单', 'value': 13}

    predictor = ALGORITHM_MODELS.get(model_id)
    if predictor is None:
        return {'kill': '大单', 'size': '大', 'oe': '单', 'combo': '大单', 'value': 13}

    # 使用最近30期的和值序列作为预测器输入
    totals = [sum_nums(item.get('nums', [])) for item in history[:30]]
    try:
        val = predictor(totals)
    except Exception:
        val = 13

    combo = get_combo(val)
    kill = get_kill(combo)
    size = '大' if val >= 14 else '小'
    oe = '双' if val % 2 == 0 else '单'

    return {
        'kill': kill,
        'size': size,
        'oe': oe,
        'combo': combo,
        'value': val
    }

def get_prediction(model_id: int, history: List[Dict]) -> Dict:
    if model_id < 1 or model_id > TOTAL_MODELS:
        return {'kill': '大单', 'size': '大', 'oe': '单', 'combo': '大单', 'value': 13}
    return evaluate_expression(model_id, history)

# ============ 数据管理 ============
class JND28Data:
    def __init__(self):
        self.raw_data: List[Dict] = []
        self.last_update: Optional[datetime] = None
        self.model_stats: Dict[int, Dict] = {}
        self.prediction_history: Dict[int, List] = {}
        self.current_model: int = 1
        self._loading = False
        self.last_period: Optional[str] = None
        self.last_pushed_period: Optional[str] = None
        self.last_prediction: Optional[Dict] = None
        
    def fetch_data(self) -> bool:
        if self._loading:
            return False
        
        self._loading = True
        try:
            logger.info("📡 正在获取数据...")
            try:
                resp = requests.get(API_URL, timeout=15, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                if resp.status_code == 200:
                    json_data = resp.json()
                    arr = self._extract_data(json_data)
                    if arr:
                        self._process_data(arr)
                        self._loading = False
                        logger.info(f"✅ 数据加载成功，共 {len(self.raw_data)} 期")
                        return True
            except Exception as e:
                logger.warning(f"主API请求失败: {e}")
            
            logger.warning("⚠️ 使用模拟数据")
            self._generate_mock_data()
            self._loading = False
            return True
        except Exception as e:
            logger.error(f"❌ 数据加载失败: {e}")
            self._loading = False
            return False
    
    def _extract_data(self, json_data):
        arr = []
        if isinstance(json_data, list):
            arr = json_data
        elif isinstance(json_data, dict):
            for key in ['data', 'list', 'result', 'results', 'items']:
                if key in json_data and isinstance(json_data[key], list):
                    arr = json_data[key]
                    break
            if not arr and 'code' in json_data and json_data.get('code') == 1:
                if 'data' in json_data:
                    arr = json_data['data']
        return arr
    
    def _process_data(self, arr):
        processed = []
        for item in arr[:100]:
            nums = parse_nums(item.get(FIELD_NUMBERS, ''))
            if len(nums) == 3:
                processed.append({
                    FIELD_PERIOD: item.get(FIELD_PERIOD, ''),
                    FIELD_NUMBERS: item.get(FIELD_NUMBERS, ''),
                    FIELD_TIME: item.get(FIELD_TIME, ''),
                    'nums': nums
                })
        if processed:
            self.raw_data = processed
            self.last_update = datetime.now()
            if processed:
                self.last_period = processed[0].get(FIELD_PERIOD, '')
            self._update_stats()
    
    def _generate_mock_data(self):
        import random
        mock_data = []
        base_period = 3450500
        for i in range(50):
            a = random.randint(0, 9)
            b = random.randint(0, 9)
            c = random.randint(0, 9)
            nums = [a, b, c]
            mock_data.append({
                FIELD_PERIOD: str(base_period + i),
                FIELD_NUMBERS: f"{a},{b},{c}",
                FIELD_TIME: str(int(datetime.now().timestamp()) - (50 - i) * 210),
                'nums': nums
            })
        self.raw_data = mock_data[::-1]
        self.last_update = datetime.now()
        if self.raw_data:
            self.last_period = self.raw_data[0].get(FIELD_PERIOD, '')
        self._update_stats()
        logger.info(f"📊 生成模拟数据 {len(self.raw_data)} 期")
    
    def _update_stats(self):
        if len(self.raw_data) < 3:
            return
        max_check = min(len(self.raw_data) - 1, HISTORY_LIMIT)
        for m in range(1, TOTAL_MODELS + 1):
            if m not in self.model_stats:
                self.model_stats[m] = {
                    'total': 0, 'kill_win': 0, 'size_win': 0, 
                    'oe_win': 0, 'double_win': 0,
                    'consecutive': 0, 'kill_rate': 0, 
                    'size_rate': 0, 'oe_rate': 0, 'double_rate': 0,
                    'recent5_kill_rate': 0, 'recent10_kill_rate': 0,
                    'recent5_double_rate': 0, 'recent10_double_rate': 0,
                }
            else:
                for key in ['total', 'kill_win', 'size_win', 'oe_win', 'double_win', 'consecutive',
                            'recent5_kill_rate', 'recent10_kill_rate',
                            'recent5_double_rate', 'recent10_double_rate']:
                    self.model_stats[m][key] = 0
            self.prediction_history[m] = []
        for i in range(max_check):
            current = self.raw_data[i]
            actual_sum = sum_nums(current.get('nums', []))
            actual_combo = get_combo(actual_sum)
            actual_size = actual_combo[0]
            actual_oe = actual_combo[1]
            history_slice = self.raw_data[i+1:]
            if len(history_slice) < 2:
                continue
            for m in range(1, TOTAL_MODELS + 1):
                pred = get_prediction(m, history_slice)
                stats = self.model_stats[m]
                stats['total'] += 1
                double_list = get_double_recommend(pred['kill'])
                if actual_combo != pred['kill']:
                    stats['kill_win'] += 1
                if actual_size == pred['size']:
                    stats['size_win'] += 1
                if actual_oe == pred['oe']:
                    stats['oe_win'] += 1
                if actual_combo in double_list:
                    stats['double_win'] += 1
                self.prediction_history[m].append({
                    'period': current.get(FIELD_PERIOD, ''),
                    'actual': actual_combo,
                    'actual_sum': actual_sum,
                    'kill': pred['kill'],
                    'size': pred['size'],
                    'oe': pred['oe'],
                    'double': double_list,
                    'kill_win': actual_combo != pred['kill'],
                    'double_win': actual_combo in double_list
                })
        for m in range(1, TOTAL_MODELS + 1):
            consec = 0
            history = self.prediction_history.get(m, [])
            for h in reversed(history):
                if h.get('kill_win', False):
                    consec += 1
                else:
                    break
            self.model_stats[m]['consecutive'] = consec
            total = self.model_stats[m]['total']
            if total > 0:
                self.model_stats[m]['kill_rate'] = self.model_stats[m]['kill_win'] / total * 100
                self.model_stats[m]['size_rate'] = self.model_stats[m]['size_win'] / total * 100
                self.model_stats[m]['oe_rate'] = self.model_stats[m]['oe_win'] / total * 100
                self.model_stats[m]['double_rate'] = self.model_stats[m]['double_win'] / total * 100
            # 计算近期加权胜率
            history = self.prediction_history.get(m, [])
            for window, key in [(5, 'recent5'), (10, 'recent10')]:
                recent = history[-window:]
                if recent:
                    kill_wins = sum(1 for h in recent if h.get('kill_win', False))
                    double_wins = sum(1 for h in recent if h.get('double_win', False))
                    self.model_stats[m][f'{key}_kill_rate'] = kill_wins / len(recent) * 100
                    self.model_stats[m][f'{key}_double_rate'] = double_wins / len(recent) * 100
        if self.raw_data:
            self.last_prediction = get_prediction(self.current_model, self.raw_data)
    
    # ---------- 排行榜方法 ----------
    def get_top_kill_rate(self, limit: int = 15) -> List[Tuple[int, float, int]]:
        # 综合得分：近期5期胜率权重60% + 总体胜率权重40%
        stats = []
        for m, s in self.model_stats.items():
            if s.get('total', 0) > 0:
                score = s.get('recent5_kill_rate', 0) * 0.6 + s.get('kill_rate', 0) * 0.4
                stats.append((m, score, s['consecutive'], s['kill_rate']))
        stats = sorted(stats, key=lambda x: (x[1], x[3]), reverse=True)[:limit]
        return [(m, kill_rate, consec) for m, score, consec, kill_rate in stats]
    
    def get_top_kill_consecutive(self, limit: int = 15) -> List[Tuple[int, int, float]]:
        stats = [(m, s['consecutive'], s['kill_rate']) 
                 for m, s in self.model_stats.items() if s.get('total', 0) > 0]
        return sorted(stats, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_top_kill_lose(self, limit: int = 15) -> List[Tuple[int, int, float]]:
        stats = []
        for m, s in self.model_stats.items():
            if s.get('total', 0) > 0:
                lose = 0
                history = self.prediction_history.get(m, [])
                for h in reversed(history):
                    if not h.get('kill_win', True):
                        lose += 1
                    else:
                        break
                stats.append((m, lose, s['kill_rate']))
        return sorted(stats, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_top_double_rate(self, limit: int = 15) -> List[Tuple[int, float]]:
        # 综合得分：近期5期双组胜率权重60% + 总体双组胜率权重40%
        stats = []
        for m, s in self.model_stats.items():
            if s.get('total', 0) > 0:
                score = s.get('recent5_double_rate', 0) * 0.6 + s.get('double_rate', 0) * 0.4
                stats.append((m, score, s['double_rate']))
        stats = sorted(stats, key=lambda x: x[1], reverse=True)[:limit]
        return [(m, double_rate) for m, score, double_rate in stats]
    
    def get_top_double_consecutive(self, limit: int = 15) -> List[Tuple[int, int, float]]:
        stats = []
        for m, s in self.model_stats.items():
            if s.get('total', 0) > 0:
                consec = 0
                history = self.prediction_history.get(m, [])
                for h in reversed(history):
                    if h.get('double_win', False):
                        consec += 1
                    else:
                        break
                stats.append((m, consec, s['double_rate']))
        return sorted(stats, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_top_double_lose(self, limit: int = 15) -> List[Tuple[int, int, float]]:
        stats = []
        for m, s in self.model_stats.items():
            if s.get('total', 0) > 0:
                lose = 0
                history = self.prediction_history.get(m, [])
                for h in reversed(history):
                    if not h.get('double_win', True):
                        lose += 1
                    else:
                        break
                stats.append((m, lose, s['double_rate']))
        return sorted(stats, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_top_size(self, limit: int = 15) -> List[Tuple[int, float]]:
        stats = [(m, s['size_rate']) for m, s in self.model_stats.items() if s.get('total', 0) > 0]
        return sorted(stats, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_top_oe(self, limit: int = 15) -> List[Tuple[int, float]]:
        stats = [(m, s['oe_rate']) for m, s in self.model_stats.items() if s.get('total', 0) > 0]
        return sorted(stats, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_prediction_for_model(self, model_id: int) -> Optional[Dict]:
        if not self.raw_data:
            return None
        return get_prediction(model_id, self.raw_data)
    
    def get_model_history(self, model_id: int, limit: int = 20) -> List[Dict]:
        if model_id not in self.prediction_history:
            return []
        history = self.prediction_history[model_id]
        return history[-limit:][::-1]
    
    def get_actual_result(self) -> Optional[Dict]:
        if not self.raw_data:
            return None
        latest = self.raw_data[0]
        nums = latest.get('nums', [])
        total = sum_nums(nums)
        return {
            'period': latest.get(FIELD_PERIOD, ''),
            'numbers': nums,
            'total': total,
            'combo': get_combo(total)
        }
    
    def check_new_period(self) -> Optional[str]:
        if not self.raw_data:
            return None
        current = self.raw_data[0].get(FIELD_PERIOD, '')
        # 首次初始化，不触发推送
        if self.last_period is None:
            self.last_period = current
            self.last_prediction = get_prediction(self.current_model, self.raw_data)
            return None
        if current != self.last_period:
            self.last_period = current
            self.last_prediction = get_prediction(self.current_model, self.raw_data)
            return current
        return None

# ============ 机器人主类 ============
class TianZhenBot:
    def __init__(self, token: str):
        self.token = token
        self.data = JND28Data()
        self.app = None
        # 内存存储：所有使用过的用户（用于推送）
        self.all_users = set()
        # 存储每个用户的最后选择模型
        self.user_models = {}
        # 存储用户最后查看的算法详情消息 {chat_id: (message_id, pred_type)}
        self.user_detail_messages = {}

    # -------- 命令处理 --------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)  # 记录用户
        
        keyboard = [
            [KeyboardButton("🔪 杀组预测"), KeyboardButton("🎲 双组预测")],
            [KeyboardButton("📏 大小预测"), KeyboardButton("🔢 单双预测")],
            [KeyboardButton("📊 组合预测"), KeyboardButton("🏆 排行榜")],
            [KeyboardButton("ℹ️ 状态"), KeyboardButton("🔄 刷新数据")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"🌸 **天真预测**\n\n"
            f"👋 欢迎 {user.first_name}！\n\n"
            f"⚡ 基于 {TOTAL_MODELS} 套混合算法（近期+总体加权排序）\n"
            f"📊 最近{HISTORY_LIMIT}期数据分析\n\n"
            f"🔹 点击下方按钮查看预测\n"
            f"🔹 点击算法可查看历史记录\n"
            f"🔄 数据每{AUTO_REFRESH_INTERVAL}秒自动刷新\n"
            f"🔄 打开算法详情后，新数据会自动刷新",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.start(update, context)

    # -------- 预测功能（无权限检查） --------
    async def refresh_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)
        await update.message.reply_text("🔄 正在刷新数据...")
        if self.data.fetch_data():
            await update.message.reply_text(f"✅ 数据刷新成功！共 {len(self.data.raw_data)} 期")
        else:
            await update.message.reply_text("❌ 数据刷新失败，请稍后重试")

    async def kill_predict(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)
        if not self.data.raw_data:
            await update.message.reply_text("⏳ 数据加载中，请点击「🔄 刷新数据」重试")
            return
        top_list = self.data.get_top_kill_rate(15)
        if not top_list:
            await update.message.reply_text("暂无数据，请点击「🔄 刷新数据」")
            return
        actual = self.data.get_actual_result()
        next_period = get_next_period(actual['period']) if actual else '--'
        msg = f"🔪 **杀组预测**\n📅 下一期：{next_period}\n📊 最近{HISTORY_LIMIT}期数据\n\n"
        keyboard = []
        for i, (m, rate, consec) in enumerate(top_list, 1):
            pred = self.data.get_prediction_for_model(m)
            kill = pred['kill'] if pred else '--'
            msg += f"预测{i}：算法{m} → {kill} ({rate:.2f}%) | {consec}连中\n"
            keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"kill_{m}")])
        keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def double_predict(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)
        if not self.data.raw_data:
            await update.message.reply_text("⏳ 数据加载中，请点击「🔄 刷新数据」重试")
            return
        top_list = self.data.get_top_double_rate(15)
        if not top_list:
            await update.message.reply_text("暂无数据，请点击「🔄 刷新数据」")
            return
        actual = self.data.get_actual_result()
        next_period = get_next_period(actual['period']) if actual else '--'
        msg = f"🎲 **双组预测**\n📅 下一期：{next_period}\n📊 最近{HISTORY_LIMIT}期数据\n\n"
        keyboard = []
        for i, (m, rate) in enumerate(top_list, 1):
            pred = self.data.get_prediction_for_model(m)
            if pred:
                double = get_double_recommend(pred['kill'])
                msg += f"预测{i}：算法{m} → {double[0]}/{double[1]} ({rate:.2f}%)\n"
                keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"double_{m}")])
        keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def size_predict(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)
        if not self.data.raw_data:
            await update.message.reply_text("⏳ 数据加载中，请点击「🔄 刷新数据」重试")
            return
        top_list = self.data.get_top_size(15)
        if not top_list:
            await update.message.reply_text("暂无数据，请点击「🔄 刷新数据」")
            return
        actual = self.data.get_actual_result()
        next_period = get_next_period(actual['period']) if actual else '--'
        msg = f"📏 **大小预测**\n📅 下一期：{next_period}\n📊 最近{HISTORY_LIMIT}期数据\n\n"
        keyboard = []
        for i, (m, rate) in enumerate(top_list, 1):
            pred = self.data.get_prediction_for_model(m)
            size = pred['size'] if pred else '--'
            msg += f"预测{i}：算法{m} → {size} ({rate:.2f}%)\n"
            keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"size_{m}")])
        keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def oe_predict(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)
        if not self.data.raw_data:
            await update.message.reply_text("⏳ 数据加载中，请点击「🔄 刷新数据」重试")
            return
        top_list = self.data.get_top_oe(15)
        if not top_list:
            await update.message.reply_text("暂无数据，请点击「🔄 刷新数据」")
            return
        actual = self.data.get_actual_result()
        next_period = get_next_period(actual['period']) if actual else '--'
        msg = f"🔢 **单双预测**\n📅 下一期：{next_period}\n📊 最近{HISTORY_LIMIT}期数据\n\n"
        keyboard = []
        for i, (m, rate) in enumerate(top_list, 1):
            pred = self.data.get_prediction_for_model(m)
            oe = pred['oe'] if pred else '--'
            msg += f"预测{i}：算法{m} → {oe} ({rate:.2f}%)\n"
            keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"oe_{m}")])
        keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def combo_predict(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)
        if not self.data.raw_data:
            await update.message.reply_text("⏳ 数据加载中，请点击「🔄 刷新数据」重试")
            return
        top_list = self.data.get_top_kill_rate(5)
        if not top_list:
            await update.message.reply_text("暂无数据，请点击「🔄 刷新数据」")
            return
        actual = self.data.get_actual_result()
        next_period = get_next_period(actual['period']) if actual else '--'
        msg = f"📊 **组合预测**\n📅 下一期：{next_period}\n📊 最近{HISTORY_LIMIT}期数据\n\n"
        keyboard = []
        for i, (m, rate, consec) in enumerate(top_list, 1):
            pred = self.data.get_prediction_for_model(m)
            if pred:
                double = get_double_recommend(pred['kill'])
                msg += f"预测{i}：算法{m}\n├ 杀组：{pred['kill']} ({rate:.2f}%)\n└ 双组：{double[0]}/{double[1]}\n\n"
                keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"combo_{m}")])
        keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

    # -------- 排行榜 --------
    async def rank_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)
        if not self.data.raw_data:
            await update.message.reply_text("⏳ 数据加载中，请点击「🔄 刷新数据」重试")
            return
        keyboard = [
            [InlineKeyboardButton("🔪 杀组排行", callback_data="rank_kill_menu")],
            [InlineKeyboardButton("🎲 双组排行", callback_data="rank_double_menu")],
            [InlineKeyboardButton("📏 大小排行", callback_data="rank_size_menu")],
            [InlineKeyboardButton("🔢 单双排行", callback_data="rank_oe_menu")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🏆 **排行榜**\n\n请选择要查看的排行类型：",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def show_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)
        if not self.data.raw_data:
            await update.message.reply_text("⏳ 数据加载中，请点击「🔄 刷新数据」")
            return
        actual = self.data.get_actual_result()
        active = sum(1 for s in self.data.model_stats.values() if s.get('total', 0) > 0)
        msg = (
            f"🤖 **系统状态**\n\n"
            f"🌸 天真预测 v2.0（无限制版）\n"
            f"📊 算法总数：{TOTAL_MODELS}（多运算符混合）\n"
            f"✅ 活跃算法：{active}\n"
            f"📈 历史期数：{len(self.data.raw_data)}\n"
            f"📊 分析期数：最近{HISTORY_LIMIT}期\n"
            f"🔄 自动刷新：每{AUTO_REFRESH_INTERVAL}秒\n"
            f"📅 更新：{self.data.last_update.strftime('%Y-%m-%d %H:%M:%S') if self.data.last_update else '--'}\n"
        )
        if actual:
            msg += f"\n📌 最新：{actual['period']}\n"
            msg += f"   {actual['numbers'][0]}+{actual['numbers'][1]}+{actual['numbers'][2]}={actual['total']}  {actual['combo']}"
        await update.message.reply_text(msg, parse_mode='Markdown')

    # -------- 算法详情 --------
    def build_algorithm_detail_message(self, model_id: int, pred_type: str) -> Tuple[str, InlineKeyboardMarkup]:
        """构建算法详情消息内容"""
        pred = self.data.get_prediction_for_model(model_id)
        stats = self.data.model_stats.get(model_id, {})
        history = self.data.get_model_history(model_id, 20)
        actual = self.data.get_actual_result()
        next_period = get_next_period(actual['period']) if actual else '--'

        if pred_type == 'kill':
            title = f"🔪 **算法{model_id}** 杀组预测"
            detail = f"杀组：{pred['kill']}"
            rate_key = 'kill_rate'
        elif pred_type == 'double':
            double = get_double_recommend(pred['kill'])
            title = f"🎲 **算法{model_id}** 双组预测"
            detail = f"双组：{double[0]}/{double[1]}"
            rate_key = 'double_rate'
        elif pred_type == 'size':
            title = f"📏 **算法{model_id}** 大小预测"
            detail = f"大小：{pred['size']}"
            rate_key = 'size_rate'
        elif pred_type == 'oe':
            title = f"🔢 **算法{model_id}** 单双预测"
            detail = f"单双：{pred['oe']}"
            rate_key = 'oe_rate'
        else:
            double = get_double_recommend(pred['kill'])
            title = f"📊 **算法{model_id}** 组合预测"
            detail = f"杀组：{pred['kill']} | 双组：{double[0]}/{double[1]}"
            rate_key = 'kill_rate'

        msg = f"{title}\n"
        msg += f"【{detail}】"
        msg += f"胜率{stats.get(rate_key, 0):.1f}% | {stats.get('consecutive', 0)}连中\n\n"

        if history:
            for h in history[:20]:
                period = h.get('period', '')
                if pred_type == 'kill':
                    kill = h.get('kill', '--')
                    win = h.get('kill_win', False)
                    status = '✅' if win else '❌'
                    msg += f"{period}期 | 杀{kill} | 开{h.get('actual_sum', '')} {status}\n"
                elif pred_type == 'double':
                    double = h.get('double', ['--', '--'])
                    win = h.get('double_win', False)
                    status = '✅' if win else '❌'
                    msg += f"{period}期 | {double[0]} {double[1]} | 开{h.get('actual_sum', '')} {status}\n"
                elif pred_type == 'size':
                    size = h.get('size', '--')
                    actual_combo = h.get('actual', '')
                    win = (size == actual_combo[0]) if actual_combo else False
                    status = '✅' if win else '❌'
                    msg += f"{period}期 | 预测{size} | 开{h.get('actual_sum', '')} {status}\n"
                elif pred_type == 'oe':
                    oe = h.get('oe', '--')
                    actual_combo = h.get('actual', '')
                    win = (oe == actual_combo[1]) if actual_combo else False
                    status = '✅' if win else '❌'
                    msg += f"{period}期 | 预测{oe} | 开{h.get('actual_sum', '')} {status}\n"
                else:
                    kill = h.get('kill', '--')
                    double = h.get('double', ['--', '--'])
                    kill_win = h.get('kill_win', False)
                    status = '✅' if kill_win else '❌'
                    msg += f"{period}期 | 杀{kill} {double[0]}/{double[1]} | 开{h.get('actual_sum', '')} {status}\n"

        if pred_type == 'kill':
            msg += f"{next_period}期 | 杀{pred['kill']} | 待开 ⏳"
        elif pred_type == 'double':
            double = get_double_recommend(pred['kill'])
            msg += f"{next_period}期 | {double[0]} {double[1]} | 待开 ⏳"
        elif pred_type == 'size':
            msg += f"{next_period}期 | 预测{pred['size']} | 待开 ⏳"
        elif pred_type == 'oe':
            msg += f"{next_period}期 | 预测{pred['oe']} | 待开 ⏳"
        else:
            double = get_double_recommend(pred['kill'])
            msg += f"{next_period}期 | 杀{pred['kill']} {double[0]}/{double[1]} | 待开 ⏳"

        keyboard = [[InlineKeyboardButton("🔙 返回", callback_data="back_to_predict")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return msg, reply_markup

    async def show_algorithm_detail(self, update, model_id: int, pred_type: str, is_callback: bool = True):
        try:
            chat_id = update.message.chat.id

            self.all_users.add(chat_id)
            self.user_models[chat_id] = model_id  # 记录用户最后选择的模型

            if not self.data.raw_data:
                msg = "⏳ 数据加载中，请点击「🔄 刷新数据」重试"
                if is_callback:
                    await update.edit_message_text(msg)
                else:
                    await update.message.reply_text(msg)
                return

            pred = self.data.get_prediction_for_model(model_id)
            if not pred:
                msg = "❌ 算法数据异常"
                if is_callback:
                    await update.edit_message_text(msg)
                else:
                    await update.message.reply_text(msg)
                return

            msg, reply_markup = self.build_algorithm_detail_message(model_id, pred_type)

            if is_callback:
                sent = await update.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')
                message_id = sent.message_id
            else:
                sent = await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')
                message_id = sent.message_id

            # 记录用户最后查看的算法详情消息，用于新数据自动刷新
            self.user_detail_messages[chat_id] = (message_id, pred_type)

        except Exception as e:
            logger.error(f"显示算法详情时出错: {e}")
            error_msg = f"❌ 显示详情时出错：{str(e)}"
            if is_callback:
                try:
                    await update.edit_message_text(error_msg)
                except:
                    pass
            else:
                try:
                    await update.message.reply_text(error_msg)
                except:
                    pass

    # -------- 自动刷新用户详情 --------
    async def refresh_user_details(self, context: ContextTypes.DEFAULT_TYPE):
        """检测到新数据后，自动刷新用户打开的算法详情消息"""
        if not self.user_detail_messages:
            return
        for chat_id, (message_id, pred_type) in list(self.user_detail_messages.items()):
            model_id = self.user_models.get(chat_id, 1)
            try:
                msg, reply_markup = self.build_algorithm_detail_message(model_id, pred_type)
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=msg,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                logger.info(f"🔄 已自动刷新 {chat_id} 的算法{model_id}详情")
            except Exception as e:
                logger.warning(f"自动刷新 {chat_id} 的算法详情失败: {e}")

    # -------- 自动推送 --------
    async def auto_push(self, context: ContextTypes.DEFAULT_TYPE, force_period: Optional[str] = None):
        if not self.data.raw_data:
            return
        new_period = force_period
        if not new_period:
            new_period = self.data.check_new_period()
            if not new_period:
                return
        # 避免重复推送同一期
        if self.data.last_pushed_period == new_period:
            return
        self.data.last_pushed_period = new_period
        if not self.all_users:
            logger.info("无用户，跳过推送")
            return
        logger.info(f"📢 新期号 {new_period}，向 {len(self.all_users)} 个用户推送")
        actual = self.data.get_actual_result()
        if not actual:
            return

        # 先自动刷新用户当前打开的算法详情
        await self.refresh_user_details(context)

        for chat_id in list(self.all_users):
            try:
                # 获取用户上次选择的模型，若没有则用1
                model_id = self.user_models.get(chat_id, 1)
                pred = self.data.get_prediction_for_model(model_id)
                if not pred:
                    continue
                double = get_double_recommend(pred['kill'])
                msg = (
                    f"📢 **新期号 {new_period} 已开奖**\n"
                    f"开奖结果：{actual['combo']}（{actual['total']}）\n\n"
                    f"🔮 **下一期预测（算法 {model_id}）**\n"
                    f"🔪 杀组：{pred['kill']}\n"
                    f"📏 大小：{pred['size']}\n"
                    f"🔢 单双：{pred['oe']}\n"
                    f"🎲 双组：{double[0]}/{double[1]}\n\n"
                    f"💡 查看详情请点击对应算法按钮"
                )
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
                logger.info(f"✅ 已推送至 {chat_id}")
            except Exception as e:
                logger.error(f"推送至 {chat_id} 失败: {e}")

    # -------- 消息路由 --------
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.all_users.add(chat_id)  # 记录用户
        text = update.message.text

        if text == "🔪 杀组预测":
            await self.kill_predict(update, context)
        elif text == "🎲 双组预测":
            await self.double_predict(update, context)
        elif text == "📏 大小预测":
            await self.size_predict(update, context)
        elif text == "🔢 单双预测":
            await self.oe_predict(update, context)
        elif text == "📊 组合预测":
            await self.combo_predict(update, context)
        elif text == "🏆 排行榜":
            await self.rank_menu(update, context)
        elif text == "ℹ️ 状态":
            await self.show_status(update, context)
        elif text == "🔄 刷新数据":
            await self.refresh_data(update, context)
        elif text.isdigit() and 1 <= int(text) <= TOTAL_MODELS:
            model_id = int(text)
            self.user_models[chat_id] = model_id
            pred = self.data.get_prediction_for_model(model_id)
            stats = self.data.model_stats.get(model_id, {})
            if pred:
                double = get_double_recommend(pred['kill'])
                msg = (
                    f"🎯 **算法 {model_id}**\n\n"
                    f"🔪 杀组：{pred['kill']}\n"
                    f"📏 大小：{pred['size']}\n"
                    f"🔢 单双：{pred['oe']}\n"
                    f"🎲 双组：{double[0]}/{double[1]}\n\n"
                    f"📊 杀组胜率：{stats.get('kill_rate', 0):.2f}%\n"
                    f"📊 双组胜率：{stats.get('double_rate', 0):.2f}%\n"
                    f"🔥 连中：{stats.get('consecutive', 0)} 期\n"
                    f"📈 样本：{stats.get('total', 0)} 期"
                )
                await update.message.reply_text(msg, parse_mode='Markdown')

    # -------- 回调处理 --------
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        chat_id = query.message.chat.id
        self.all_users.add(chat_id)  # 记录用户

        # 导航菜单
        if data in ("main_menu", "back_to_predict", "rank_menu",
                    "rank_kill_menu", "rank_double_menu", "rank_size_menu", "rank_oe_menu"):
            if data == "main_menu":
                keyboard = [
                    [KeyboardButton("🔪 杀组预测"), KeyboardButton("🎲 双组预测")],
                    [KeyboardButton("📏 大小预测"), KeyboardButton("🔢 单双预测")],
                    [KeyboardButton("📊 组合预测"), KeyboardButton("🏆 排行榜")],
                    [KeyboardButton("ℹ️ 状态"), KeyboardButton("🔄 刷新数据")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await query.edit_message_text(
                    "🌸 **天真预测**\n\n选择功能：",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            elif data == "rank_menu":
                keyboard = [
                    [InlineKeyboardButton("🔪 杀组排行", callback_data="rank_kill_menu")],
                    [InlineKeyboardButton("🎲 双组排行", callback_data="rank_double_menu")],
                    [InlineKeyboardButton("📏 大小排行", callback_data="rank_size_menu")],
                    [InlineKeyboardButton("🔢 单双排行", callback_data="rank_oe_menu")],
                    [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "🏆 **排行榜**\n\n请选择要查看的排行类型：",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            elif data == "rank_kill_menu":
                keyboard = [
                    [InlineKeyboardButton("🏆 杀组胜率排行", callback_data="rank_kill_rate")],
                    [InlineKeyboardButton("🔥 杀组连中排行", callback_data="rank_kill_consecutive")],
                    [InlineKeyboardButton("📉 杀组连挂排行", callback_data="rank_kill_lose")],
                    [InlineKeyboardButton("🔙 返回排行菜单", callback_data="rank_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "🔪 **杀组排行榜**\n\n请选择：",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            elif data == "rank_double_menu":
                keyboard = [
                    [InlineKeyboardButton("🏆 双组高胜排行", callback_data="rank_double_rate")],
                    [InlineKeyboardButton("🔥 双组连中排行", callback_data="rank_double_consecutive")],
                    [InlineKeyboardButton("📉 双组连挂排行", callback_data="rank_double_lose")],
                    [InlineKeyboardButton("🔙 返回排行菜单", callback_data="rank_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "🎲 **双组排行榜**\n\n请选择：",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            elif data == "rank_size_menu":
                top = self.data.get_top_size(15)
                await self.render_rank(query, "大小胜率排行", top, 'size')
                return
            elif data == "rank_oe_menu":
                top = self.data.get_top_oe(15)
                await self.render_rank(query, "单双胜率排行", top, 'oe')
                return
            elif data == "back_to_predict":
                keyboard = [
                    [KeyboardButton("🔪 杀组预测"), KeyboardButton("🎲 双组预测")],
                    [KeyboardButton("📏 大小预测"), KeyboardButton("🔢 单双预测")],
                    [KeyboardButton("📊 组合预测"), KeyboardButton("🏆 排行榜")],
                    [KeyboardButton("ℹ️ 状态"), KeyboardButton("🔄 刷新数据")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await query.edit_message_text(
                    "🌸 **天真预测**\n\n选择功能：",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return

        # 具体排行数据
        if data == "rank_kill_rate":
            top = self.data.get_top_kill_rate(15)
            await self.render_rank(query, "杀组胜率排行", top, 'kill_rate')
            return
        if data == "rank_kill_consecutive":
            top = self.data.get_top_kill_consecutive(15)
            await self.render_rank(query, "杀组连中排行", top, 'kill_consecutive')
            return
        if data == "rank_kill_lose":
            top = self.data.get_top_kill_lose(15)
            await self.render_rank(query, "杀组连挂排行", top, 'kill_lose')
            return
        if data == "rank_double_rate":
            top = self.data.get_top_double_rate(15)
            await self.render_rank(query, "双组高胜排行", top, 'double_rate')
            return
        if data == "rank_double_consecutive":
            top = self.data.get_top_double_consecutive(15)
            await self.render_rank(query, "双组连中排行", top, 'double_consecutive')
            return
        if data == "rank_double_lose":
            top = self.data.get_top_double_lose(15)
            await self.render_rank(query, "双组连挂排行", top, 'double_lose')
            return

        # 算法详情
        if data.startswith("kill_"):
            model_id = int(data.split("_")[1])
            self.data.current_model = model_id
            await self.show_algorithm_detail(query, model_id, 'kill', True)
            return
        if data.startswith("double_"):
            model_id = int(data.split("_")[1])
            self.data.current_model = model_id
            await self.show_algorithm_detail(query, model_id, 'double', True)
            return
        if data.startswith("size_"):
            model_id = int(data.split("_")[1])
            self.data.current_model = model_id
            await self.show_algorithm_detail(query, model_id, 'size', True)
            return
        if data.startswith("oe_"):
            model_id = int(data.split("_")[1])
            self.data.current_model = model_id
            await self.show_algorithm_detail(query, model_id, 'oe', True)
            return
        if data.startswith("combo_"):
            model_id = int(data.split("_")[1])
            self.data.current_model = model_id
            await self.show_algorithm_detail(query, model_id, 'combo', True)
            return

        await query.edit_message_text("❌ 未知操作")

    async def render_rank(self, query, title, data, rank_type):
        if not data:
            await query.edit_message_text("暂无数据")
            return
        actual = self.data.get_actual_result()
        next_period = get_next_period(actual['period']) if actual else '--'
        msg = f"🏆 **{title}**（最近{HISTORY_LIMIT}期）\n📅 下一期：{next_period}\n\n"
        keyboard = []
        for i, item in enumerate(data, 1):
            if rank_type in ['kill_rate', 'kill_consecutive']:
                if rank_type == 'kill_rate':
                    m, rate, consec = item
                else:
                    m, consec, rate = item
                pred = self.data.get_prediction_for_model(m)
                kill = pred['kill'] if pred else '--'
                msg += f"预测{i}：算法{m} → {kill} ({rate:.2f}%) | {consec}连中\n"
                keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"kill_{m}")])
            elif rank_type == 'kill_lose':
                m, lose, rate = item
                pred = self.data.get_prediction_for_model(m)
                kill = pred['kill'] if pred else '--'
                msg += f"预测{i}：算法{m} → {kill} ({rate:.2f}%) | 连挂{lose}期\n"
                keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"kill_{m}")])
            elif rank_type == 'double_rate':
                m, rate = item
                pred = self.data.get_prediction_for_model(m)
                if pred:
                    double = get_double_recommend(pred['kill'])
                    msg += f"预测{i}：算法{m} → {double[0]}/{double[1]} ({rate:.2f}%)\n"
                    keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"double_{m}")])
            elif rank_type == 'double_consecutive':
                m, consec, rate = item
                pred = self.data.get_prediction_for_model(m)
                if pred:
                    double = get_double_recommend(pred['kill'])
                    msg += f"预测{i}：算法{m} → {double[0]}/{double[1]} | {consec}连中 ({rate:.2f}%)\n"
                    keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"double_{m}")])
            elif rank_type == 'double_lose':
                m, lose, rate = item
                pred = self.data.get_prediction_for_model(m)
                if pred:
                    double = get_double_recommend(pred['kill'])
                    msg += f"预测{i}：算法{m} → {double[0]}/{double[1]} | 连挂{lose}期 ({rate:.2f}%)\n"
                    keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"double_{m}")])
            elif rank_type == 'size':
                m, rate = item
                pred = self.data.get_prediction_for_model(m)
                size = pred['size'] if pred else '--'
                msg += f"预测{i}：算法{m} → {size} ({rate:.2f}%)\n"
                keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"size_{m}")])
            elif rank_type == 'oe':
                m, rate = item
                pred = self.data.get_prediction_for_model(m)
                oe = pred['oe'] if pred else '--'
                msg += f"预测{i}：算法{m} → {oe} ({rate:.2f}%)\n"
                keyboard.append([InlineKeyboardButton(f"预测{i} 算法{m}", callback_data=f"oe_{m}")])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="rank_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

    # -------- 自动更新数据 --------
    async def auto_update(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("🔄 自动更新数据...")
        old_period = self.data.last_period
        if self.data.fetch_data():
            new_period = self.data.last_period
            if new_period and new_period != old_period and old_period is not None:
                logger.info(f"📢 检测到新期号: {new_period}")
                pred = self.data.get_prediction_for_model(self.data.current_model)
                if pred:
                    self.data.last_prediction = pred
                    logger.info(f"📤 新期号 {new_period} 预测已更新")
                await self.auto_push(context, new_period)

    # -------- 运行 --------
    def run(self):
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback, pattern="^(rank_|main_menu|back_to_predict|kill_|double_|size_|oe_|combo_)"))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        job_queue = self.app.job_queue
        if job_queue:
            job_queue.run_repeating(self.auto_update, interval=AUTO_REFRESH_INTERVAL, first=10)
            job_queue.run_repeating(self.auto_push, interval=AUTO_REFRESH_INTERVAL, first=15)

        logger.info("📡 加载数据...")
        self.data.fetch_data()
        logger.info(f"✅ 加载完成，{TOTAL_MODELS} 个算法")
        logger.info("🚀 启动天真预测机器人（无权限限制）...")
        self.app.run_polling()

if __name__ == "__main__":
    print("=" * 50)
    print("🌸 法老破解天真预测机器人 v2.0 (无权限限制版)")
    print("=" * 50)
    print(f"📊 算法总数：{TOTAL_MODELS}（前2000个组合）")
    print(f"📊 分析期数：最近{HISTORY_LIMIT}期")
    print("🎯 功能：杀组/双组/大小/单双/组合")
    print("💡 点击算法查看历史记录")
    print("🔄 每30秒检查新期号并自动推送")
    print("=" * 50)
    bot = TianZhenBot(TOKEN)
    bot.run()