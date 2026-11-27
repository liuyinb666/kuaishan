import os
import re
import json
import asyncio
import logging
import threading
from typing import List, Dict
import aiohttp
import uvicorn
from fastapi import FastAPI
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError, PhoneCodeInvalidError

# ==================== 环境变量 ====================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_URL = "https://yu28.top/api/kj.json?nbr=100"
API_KEY = "yu28_0889c78ad74725b7"
SESSIONS_DIR = "telegram_sessions"
USER_DATA_DIR = "user_data"

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(USER_DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

# ==================== 杀组预测算法 ====================
ALL_TYPES = ['小双', '小单', '大双', '大单']
SEQUENCES = [
    [0, 3, 9, 12, 15, 18, 21, 24, 27],
    [1, 4, 7, 10, 13, 16, 19, 22, 25],
    [2, 5, 8, 11, 14, 17, 20, 23, 26]
]
COMBINATION_RULES = {
    'sameSequence': {
        '小双': ['小双', '大双', '大单'],
        '小单': ['小单', '大单', '大双'],
        '大双': ['大双', '小双', '小单'],
        '大单': ['大单', '小单', '小双']
    },
    'diffSequence': {
        '小双': ['小双', '小单', '大单'],
        '小单': ['小单', '小双', '大双'],
        '大双': ['大双', '大单', '小单'],
        '大单': ['大单', '大双', '小双']
    }
}

def get_type_from_sum(sum_val: int) -> str:
    size = '小' if sum_val < 14 else '大'
    parity = '双' if sum_val % 2 == 0 else '单'
    return size + parity

def mulberry32(seed: int):
    s = seed & 0xFFFFFFFF
    def next_():
        nonlocal s
        s = (s + 0x6D2B79F5) & 0xFFFFFFFF
        t = (s ^ (s >> 15)) & 0xFFFFFFFF
        t = (t * (s | 1)) & 0xFFFFFFFF
        t = (t ^ (t + ((t ^ (t >> 7)) * (61 | t)))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return next_

def get_sequence_indexes(num: int) -> List[int]:
    idxs = []
    for i, seq in enumerate(SEQUENCES):
        if num in seq:
            idxs.append(i)
    return idxs

def is_same_sequence(num1: int, num2: int) -> bool:
    seq1 = get_sequence_indexes(num1)
    seq2 = get_sequence_indexes(num2)
    return any(i in seq2 for i in seq1)

def split_and_sum_str(s: str) -> int:
    s = s.replace('.', '')
    return sum(int(c) for c in s)

def predict_next_period(current_expect: str, current_sum: int, range_min: float = 0.25, range_max: float = 0.55) -> str:
    match = re.search(r'\d+', current_expect)
    seed = int(match.group()) if match else hash(current_expect) & 0xFFFFFFFF
    rnd = mulberry32(seed)

    random_num = rnd() * (range_max - range_min) + range_min
    product = random_num * current_sum
    rounded = round(product, 3)
    final_sum = split_and_sum_str(str(rounded))
    final_type = get_type_from_sum(final_sum)

    rand_str = f"{random_num:.8f}".split('.')[1]
    rand_first_three = rand_str[:3]
    rand_sum = split_and_sum_str(rand_first_three)
    same_seq = is_same_sequence(rand_sum, current_sum)

    rule_key = 'sameSequence' if same_seq else 'diffSequence'
    predict_groups = COMBINATION_RULES[rule_key][final_type]
    return next(t for t in ALL_TYPES if t not in predict_groups)

def generate_range_pool():
    pool = []
    step = 0.01
    min_width = 0.2
    max_width = 0.5
    vals = [round(i * step, 2) for i in range(0, 101)]
    for min_ in vals:
        for max_ in vals:
            if max_ - min_ >= min_width and max_ - min_ <= max_width:
                pool.append((min_, max_))
    return pool

RANGE_POOL = generate_range_pool()

class KillGroupPredictor:
    @staticmethod
    def predict_kill(history: List[dict]) -> str:
        if len(history) < 2:
            return "小单"
        max_test = min(27, len(history) - 1)
        best_range = (0.25, 0.55)
        best_hits = -1

        for rmin, rmax in RANGE_POOL:
            hits = 0
            for i in range(max_test):
                target = history[i]
                prev = history[i + 1]
                kill = predict_next_period(prev['issue'], prev['sum'], rmin, rmax)
                if target['type'] != kill:
                    hits += 1
            if hits > best_hits:
                best_hits = hits
                best_range = (rmin, rmax)

        latest = history[0]
        return predict_next_period(latest['issue'], latest['sum'], best_range[0], best_range[1])

# ==================== 数据抓取 ====================
class DataFetcher:
    @staticmethod
    async def fetch_history_list():
        try:
            headers = {"Authorization": f"Bearer {API_KEY}", "X-API-Key": API_KEY}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(API_URL, timeout=15) as resp:
                    if resp.status == 200:
                        return (await resp.json()).get("data", [])
        except Exception as e:
            logger.error(f"抓取异常: {e}")
        return []

    @staticmethod
    async def fetch_latest():
        raw_list = await DataFetcher.fetch_history_list()
        if raw_list:
            raw = raw_list[0]
            num_str = str(raw.get("number", ""))
            nums = [int(d) for d in num_str if d.isdigit()]
            total = int(raw.get("num", sum(nums[:3]) if nums else 0))
            return {
                "issue": str(raw.get("nbr")),
                "number": num_str,
                "total": total,
                "combination": str(raw.get("combination", ""))
            }
        return None

    @staticmethod
    def parse_history(raw_data: list) -> List[dict]:
        parsed = []
        for item in raw_data:
            try:
                num_str = str(item.get("number", ""))
                nums = [int(d) for d in num_str if d.isdigit()]
                if len(nums) >= 3:
                    nums = nums[:3]
                    total = int(item.get("num", sum(nums)))
                    combo = item.get("combination", "")
                    if not combo:
                        combo = "大" if total >= 14 else "小" + ("单" if total % 2 else "双")
                    parsed.append({
                        "nums": nums,
                        "sum": total,
                        "type": combo,
                        "issue": str(item.get("nbr", ""))
                    })
            except:
                pass
        return parsed

# ==================== 辅助函数 ====================
def get_next_qihao(qihao: str) -> str:
    s = str(qihao)
    try:
        if s.isdigit():
            return str(int(s) + 1).zfill(len(s))
        match = re.search(r'(\d+)$', s)
        if match:
            num_part = match.group(1)
            prefix = s[:match.start()]
            next_num = str(int(num_part) + 1).zfill(len(num_part))
            return prefix + next_num
        return s
    except:
        return s

def build_broadcast_message(title: str, history_records: list, max_records: int = 10) -> str:
    header = title.strip() if title else "预测播报"
    lines = [header]
    for rec in history_records[-max_records:]:
        q = str(rec.get('qihao', '--'))[-4:]
        kill = rec.get('kill_target', '--')
        actual = rec.get('actual')
        s = str(rec.get('sum', ''))
        if actual is None:
            lines.append(f"{q}.杀{kill}")
        elif actual != kill:
            lines.append(f"{q}.杀{kill} 🀄{s}")
        else:
            lines.append(f"{q}.杀{kill} ❌{s}")
    return "\n".join(lines)

# ==================== 用户状态 ====================
class UserState:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.file_path = os.path.join(USER_DATA_DIR, f"{self.user_id}.json")
        self.lock = threading.Lock()
        self.is_logged_in = False
        self.phone = ""
        self.client = None
        self.temp_phone_code_hash = None
        self.custom_delay = 12.0

        self.broadcast_enabled = False
        self.broadcast_channel = ""
        self.broadcast_title = "预测播报"
        self.broadcast_max_periods = 0
        self.broadcast_count = 0
        self.broadcast_history = []
        self.broadcast_sent_issues = []
        self.broadcast_last_issue = ""      # 上次播报的期号（即已发送预测的期号）
        self.last_processed_issue = ""      # 上次处理的开奖期号（用于去重）
        self.history = []

        self.load()

    def load(self):
        with self.lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.is_logged_in = data.get("is_logged_in", False)
                        self.phone = data.get("phone", "")
                        self.custom_delay = data.get("custom_delay", 12.0)
                        self.broadcast_enabled = data.get("broadcast_enabled", False)
                        self.broadcast_channel = data.get("broadcast_channel", "")
                        self.broadcast_title = data.get("broadcast_title", "预测播报")
                        self.broadcast_max_periods = data.get("broadcast_max_periods", 0)
                        self.broadcast_count = data.get("broadcast_count", 0)
                        self.broadcast_history = data.get("broadcast_history", [])
                        self.broadcast_sent_issues = data.get("broadcast_sent_issues", [])
                        self.broadcast_last_issue = data.get("broadcast_last_issue", "")
                        self.last_processed_issue = data.get("last_processed_issue", "")
                        self.history = data.get("history", [])
                except Exception as e:
                    logger.error(f"加载用户 {self.user_id} 档案出错: {e}")

    def save(self):
        with self.lock:
            try:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "user_id": self.user_id,
                        "is_logged_in": self.is_logged_in,
                        "phone": self.phone,
                        "custom_delay": self.custom_delay,
                        "broadcast_enabled": self.broadcast_enabled,
                        "broadcast_channel": self.broadcast_channel,
                        "broadcast_title": self.broadcast_title,
                        "broadcast_max_periods": self.broadcast_max_periods,
                        "broadcast_count": self.broadcast_count,
                        "broadcast_history": self.broadcast_history,
                        "broadcast_sent_issues": self.broadcast_sent_issues,
                        "broadcast_last_issue": self.broadcast_last_issue,
                        "last_processed_issue": self.last_processed_issue,
                        "history": self.history
                    }, f, ensure_ascii=False)
            except Exception as e:
                logger.error(f"保存用户 {self.user_id} 档案出错: {e}")

    def reset_broadcast_history(self):
        self.broadcast_history = []
        self.broadcast_count = 0
        self.broadcast_sent_issues = []
        self.broadcast_last_issue = ""
        self.last_processed_issue = ""

    async def try_reconnect(self):
        session_path = os.path.join(SESSIONS_DIR, f"user_{self.user_id}")
        if self.is_logged_in and os.path.exists(f"{session_path}.session"):
            try:
                self.client = TelegramClient(session_path, API_ID, API_HASH)
                await self.client.connect()
                if await self.client.is_user_authorized():
                    return True
                self.is_logged_in = False
                self.save()
            except Exception as e:
                logger.error(f"用户 {self.user_id} 重连失败: {e}")
        return False

# ==================== 系统调度器 ====================
class SystemOrchestrator:
    def __init__(self):
        if not API_ID or not API_HASH:
            logger.warning("未配置 API_ID/API_HASH，Bot 不可用")
            self.bot = None
        else:
            self.bot = TelegramClient("telegram_sessions/bot_master", API_ID, API_HASH)
        self.users = {}
        self.user_login_states = {}
        self.last_issue_id = None

    def get_user_state(self, uid):
        if uid not in self.users:
            self.users[uid] = UserState(uid)
        return self.users[uid]

    def main_keyboard(self, u: UserState):
        login = "🚪 登出账号" if u.is_logged_in else "🔑 登录协议号"
        status = "✅ 报数开启" if u.broadcast_enabled else "⏹ 报数关闭"
        return [
            [Button.inline(f"状态: {status}", data=b"noop"), Button.inline(login, data=b"login")],
            [Button.inline("📢 报数设置", data=b"broadcast_settings")],
            [Button.inline(f"⏱ 投递延迟: {u.custom_delay}s", data=b"set_delay")],
            [Button.inline("📖 使用说明", data=b"mode_intro")]
        ]

    def broadcast_settings_keyboard(self, u: UserState):
        enabled = "✅ " if u.broadcast_enabled else "⬜ "
        return [
            [Button.inline(f"{enabled}启用报数播报", data=b"toggle_broadcast")],
            [Button.inline(f"播报频道: {u.broadcast_channel or '未设置'}", data=b"set_broadcast_channel")],
            [Button.inline(f"播报标题: {u.broadcast_title}", data=b"set_broadcast_title")],
            [Button.inline(f"最大期数: {'∞' if u.broadcast_max_periods <= 0 else u.broadcast_max_periods}", data=b"set_broadcast_max")],
            [Button.inline("⬅️ 返回主菜单", data=b"back_main")]
        ]

    async def load_existing_users(self):
        if os.path.exists(USER_DATA_DIR):
            for file in os.listdir(USER_DATA_DIR):
                if file.endswith(".json"):
                    try:
                        uid = int(file.replace(".json", ""))
                        await self.get_user_state(uid).try_reconnect()
                    except:
                        pass

    async def do_broadcast(self, u: UserState, data: dict):
        """
        根据当前开奖数据 data，更新上一期结果，并生成下一期预测发送。
        必须保证同一期只处理一次，使用 last_processed_issue 去重。
        """
        if not u.broadcast_enabled or not u.broadcast_channel or not u.client:
            return

        current_issue = data['issue']
        # 如果已处理过这一期，直接跳过
        if u.last_processed_issue == current_issue:
            logger.debug(f"[用户 {u.user_id}] 期号 {current_issue} 已处理过，跳过")
            return

        # 达到最大期数则自动关闭
        if u.broadcast_max_periods > 0 and u.broadcast_count >= u.broadcast_max_periods:
            u.broadcast_enabled = False
            u.save()
            try:
                await self.bot.send_message(u.user_id, "【播报通知】已达到最大播报期数，已自动关闭报数。")
            except:
                pass
            return

        # 更新上一期结果（如果历史中有上一条记录，且它还没有 actual）
        if u.broadcast_history:
            last_rec = u.broadcast_history[-1]
            if last_rec.get('actual') is None:
                last_rec['actual'] = data['combination']
                last_rec['sum'] = data['total']

        # 生成下一期预测
        next_qihao = get_next_qihao(current_issue)
        rec = {'qihao': next_qihao, 'sum': data['total']}
        try:
            kill_target = KillGroupPredictor.predict_kill(u.history)
            rec['kill_target'] = kill_target
        except Exception as e:
            logger.error(f"预测失败: {e}")
            rec['kill_target'] = '--'

        u.broadcast_history.append(rec)
        if len(u.broadcast_history) > 20:
            u.broadcast_history = u.broadcast_history[-20:]

        msg = build_broadcast_message(u.broadcast_title, u.broadcast_history, max_records=20)

        # 延迟发送
        if u.custom_delay > 0:
            await asyncio.sleep(u.custom_delay)

        try:
            await u.client.send_message(u.broadcast_channel, msg)
            u.broadcast_count += 1
            u.broadcast_sent_issues.append(current_issue)
            u.broadcast_sent_issues = u.broadcast_sent_issues[-200:]
            u.broadcast_last_issue = current_issue   # 记录本次处理的开奖期号（即刚处理的期）
            u.last_processed_issue = current_issue   # 标记已处理
            u.save()
            logger.info(f"[用户 {u.user_id}] 播报下一期 {next_qihao}，基于期号 {current_issue}，累计 {u.broadcast_count} 期")
        except Exception as e:
            logger.error(f"播报发送失败: {e}")

    async def register_handlers(self):
        @self.bot.on(events.NewMessage(pattern="/start"))
        async def handler_start(event):
            u = self.get_user_state(event.sender_id)
            status = "开启" if u.broadcast_enabled else "关闭"
            await event.respond(
                f"📢 PC28 报数机器人\n"
                f"--------------------\n"
                f"报数状态: `{status}`\n"
                f"绑定频道: `{u.broadcast_channel or '无'}`\n"
                f"已播报: `{u.broadcast_count}` 期\n"
                f"--------------------",
                buttons=self.main_keyboard(u)
            )

        @self.bot.on(events.CallbackQuery)
        async def handler_callback(event):
            sid = event.sender_id
            u = self.get_user_state(sid)
            data = event.data.decode() if isinstance(event.data, bytes) else event.data

            if data == "noop":
                await event.answer()
                return

            if data == "back_main":
                status = "开启" if u.broadcast_enabled else "关闭"
                await event.edit(
                    f"📢 主控制面板\n"
                    f"--------------------\n"
                    f"报数状态: `{status}`\n"
                    f"绑定频道: `{u.broadcast_channel or '无'}`\n"
                    f"已播报: `{u.broadcast_count}` 期\n"
                    f"--------------------",
                    buttons=self.main_keyboard(u)
                )
                return

            if data == "broadcast_settings":
                await event.edit("报数设置", buttons=self.broadcast_settings_keyboard(u))
                return

            if data == "toggle_broadcast":
                u.broadcast_enabled = not u.broadcast_enabled
                if u.broadcast_enabled:
                    # 清空历史，重新开始
                    u.reset_broadcast_history()
                    # 获取最新开奖数据
                    latest = await DataFetcher.fetch_latest()
                    if latest:
                        # 填充历史数据
                        full = await DataFetcher.fetch_history_list()
                        if full:
                            u.history = DataFetcher.parse_history(full)
                        # 立即处理最新一期（生成下一期预测并发送）
                        await self.do_broadcast(u, latest)
                    else:
                        await event.answer("暂时无法获取开奖数据，请稍后重试", alert=True)
                u.save()
                await event.edit("报数设置", buttons=self.broadcast_settings_keyboard(u))
                return

            if data == "set_broadcast_channel":
                self.user_login_states[sid] = "WAIT_BROADCAST_CHANNEL"
                await event.respond(f"当前播报频道: `{u.broadcast_channel or '未设置'}`\n请输入目标频道 Username 或 ID:")
                return

            if data == "set_broadcast_title":
                self.user_login_states[sid] = "WAIT_BROADCAST_TITLE"
                await event.respond(f"当前播报标题: `{u.broadcast_title}`\n请输入新标题:")
                return

            if data == "set_broadcast_max":
                self.user_login_states[sid] = "WAIT_BROADCAST_MAX"
                await event.respond(f"当前最大播报期数: `{'∞' if u.broadcast_max_periods <= 0 else u.broadcast_max_periods}`\n请输入新值（0 为不限制）:")
                return

            if data == "set_delay":
                self.user_login_states[sid] = "WAIT_DELAY"
                await event.respond(f"当前延迟: `{u.custom_delay}s`\n请输入新投递延迟秒数:")
                return

            if data == "mode_intro":
                await event.answer(
                    "本机器人提供基于区间优化的杀组预测。\n"
                    "算法原理：根据期号生成伪随机数，结合区间缩放，计算下一期和值，再根据序列规则推导杀组。\n"
                    "每期自动从历史最近27期中回测所有区间，选用命中率最高的区间进行预测。\n"
                    "开启报数时清空历史，从当前最新期开始播报，历史记录最多保留20期。",
                    alert=True
                )
                return

            if data == "login":
                if u.is_logged_in:
                    u.is_logged_in = False
                    if u.client:
                        await u.client.disconnect()
                    u.save()
                    await event.edit("已安全登出。", buttons=self.main_keyboard(u))
                else:
                    self.user_login_states[sid] = "WAIT_PHONE"
                    await event.respond("请发送您的 Telegram 手机号:")
                return

        @self.bot.on(events.NewMessage)
        async def handler_text(event):
            if event.text.startswith("/"):
                return
            sid = event.sender_id
            state = self.user_login_states.get(sid)
            u = self.get_user_state(sid)

            if state == "WAIT_PHONE":
                u.phone = event.text.strip()
                try:
                    client = TelegramClient(os.path.join(SESSIONS_DIR, f"user_{sid}"), API_ID, API_HASH)
                    await client.connect()
                    req = await client.send_code_request(u.phone)
                    u.client, u.temp_phone_code_hash = client, req.phone_code_hash
                    self.user_login_states[sid] = "WAIT_CODE"
                    await event.respond("验证码已发送，请输入:")
                except Exception as e:
                    await event.respond(f"发送验证码失败: {e}")
                    self.user_login_states.pop(sid, None)
            elif state == "WAIT_CODE":
                code = event.text.strip()
                try:
                    await u.client.sign_in(u.phone, code, phone_code_hash=u.temp_phone_code_hash)
                    u.is_logged_in = True
                    u.save()
                    self.user_login_states.pop(sid, None)
                    await event.respond("登录成功!", buttons=self.main_keyboard(u))
                except SessionPasswordNeededError:
                    self.user_login_states[sid] = "WAIT_2FA"
                    await event.respond("请输入两步验证密码:")
                except (PhoneCodeExpiredError, PhoneCodeInvalidError) as e:
                    await event.respond(f"验证码错误: {e}")
                    self.user_login_states.pop(sid, None)
                except Exception as e:
                    await event.respond(f"登录失败: {e}")
                    self.user_login_states.pop(sid, None)
            elif state == "WAIT_2FA":
                try:
                    await u.client.sign_in(password=event.text.strip())
                    u.is_logged_in = True
                    u.save()
                    self.user_login_states.pop(sid, None)
                    await event.respond("2FA 验证通过，登录成功!", buttons=self.main_keyboard(u))
                except Exception as e:
                    await event.respond(f"密码错误: {e}")
            elif state == "WAIT_BROADCAST_CHANNEL":
                u.broadcast_channel = event.text.strip()
                u.save()
                self.user_login_states.pop(sid, None)
                await event.respond(f"播报频道更新为: `{u.broadcast_channel}`", buttons=self.broadcast_settings_keyboard(u))
            elif state == "WAIT_BROADCAST_TITLE":
                u.broadcast_title = event.text.strip() or "预测播报"
                u.save()
                self.user_login_states.pop(sid, None)
                await event.respond(f"播报标题更新为: `{u.broadcast_title}`", buttons=self.broadcast_settings_keyboard(u))
            elif state == "WAIT_BROADCAST_MAX":
                try:
                    val = max(0, int(event.text.strip()))
                    u.broadcast_max_periods = val
                    u.save()
                    self.user_login_states.pop(sid, None)
                    await event.respond(f"最大期数更新为: `{'∞' if val <= 0 else val}`", buttons=self.broadcast_settings_keyboard(u))
                except:
                    await event.respond("请输入非负整数")
                    self.user_login_states.pop(sid, None)
            elif state == "WAIT_DELAY":
                try:
                    u.custom_delay = max(0.0, float(event.text.strip()))
                    u.save()
                    await event.respond(f"延迟更新为: `{u.custom_delay}s`", buttons=self.main_keyboard(u))
                except:
                    await event.respond("请输入有效数字")
                self.user_login_states.pop(sid, None)

    async def poll_api(self):
        logger.info("报数轮询已启动...")
        while True:
            try:
                data = await DataFetcher.fetch_latest()
                if data:
                    issue = data['issue']
                    if issue != self.last_issue_id:
                        self.last_issue_id = issue
                        # 更新所有用户的历史数据并处理新期
                        full = await DataFetcher.fetch_history_list()
                        for uid, u in self.users.items():
                            if u.is_logged_in and u.broadcast_enabled:
                                if full:
                                    u.history = DataFetcher.parse_history(full)
                                await self.do_broadcast(u, data)
            except Exception as e:
                logger.error(f"轮询异常: {e}")
            await asyncio.sleep(4)

    async def start(self):
        if self.bot is None:
            logger.warning("Bot 未初始化，跳过启动")
            return
        await self.bot.start(bot_token=BOT_TOKEN)
        await self.register_handlers()
        await self.load_existing_users()
        # 预填充历史
        initial = await DataFetcher.fetch_history_list()
        if initial:
            parsed = DataFetcher.parse_history(initial)
            for u in self.users.values():
                if u.is_logged_in:
                    u.history = parsed
                    u.save()
        logger.info("报数机器人已启动（采用区间优化算法）")
        asyncio.create_task(self.poll_api())
        await self.bot.run_until_disconnected()

# ==================== FastAPI + 轻量控制台 ====================
def start_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    orchestrator = SystemOrchestrator()
    try:
        loop.run_until_complete(orchestrator.start())
    except Exception as e:
        logger.error(f"Bot 运行异常: {e}")

app = FastAPI(title="PC28 报数机器人")

@app.get("/")
@app.get("/health")
@app.get("/ping")
def health_check():
    return {"status": "ok", "service": "broadcast_only"}

if __name__ == "__main__":
    threading.Thread(target=start_bot_thread, daemon=True).start()
    port = int(os.getenv("PORT", "7860"))
    logger.info(f"服务启动，监听 0.0.0.0:{port} | 健康检查: /health")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")