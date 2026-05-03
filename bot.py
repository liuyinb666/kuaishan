import requests
import time
import math
import random
from datetime import datetime

# ==================== 配置区 ====================
BOT_TOKEN = "8618290364:AAGuIBWTfkGcgiw0mY4kpgW9Ij0hmc49hfw"

CHANNEL_IDS = [
    "@ziwn19",
    ""
]

API_URL = "https://pc28.help/api/kj.json?nbr=30"
PREDICT_INTERVAL = 30
MAX_CONSECUTIVE_LOSS = 1
# =================================================

# 尾数 → 形态映射
TAIL_TO_CATEGORY = {
    0: "小双", 1: "小单", 2: "小双", 3: "小单", 4: "小双",
    5: "大单", 6: "大双", 7: "大单", 8: "大双", 9: "大单"
}

# 对立面(当两个尾数映射相同时使用)
OPPOSITE = {
    "大单": "小双",
    "大双": "小单",
    "小单": "大双",
    "小双": "大单"
}

# 候选参数范围
PARAM_RANGES = {
    "大单": (10, 17),
    "小单": (10, 17),
    "大双": (11, 17),
    "小双": (11, 17)
}

# 全局连错计数
consecutive_loss = 0

def get_category(total):
    size = "大" if total >= 14 else "小"
    oe = "单" if total % 2 == 1 else "双"
    return size + oe

def get_two_digits(decimal):
    s = str(decimal)[2:]
    if len(s) >= 2:
        result = s[:2]
    else:
        result = s + "0"
    return int(result[0]), int(result[1])

def get_omission(category, history):
    for i, h in enumerate(history):
        if h["category"] == category:
            return i
    return len(history)

def get_market_state(history):
    if len(history) < 6:
        return "震荡", 3
    
    categories = [h["category"] for h in history[:6]]
    streak = 1
    for i in range(1, len(categories)):
        if categories[i] == categories[0]:
            streak += 1
        else:
            break
    
    if streak >= 3:
        return "趋势", 5
    else:
        return "震荡", 3

def predict_kill_with_params(history, params):
    """杀组预测"""
    if len(history) < 5:
        return None
    
    latest = history[0]
    
    market_state, window_size = get_market_state(history)
    window_size = min(window_size, len(history) - 1)
    last_n = history[1:1+window_size]
    
    fixed_sum = 0
    weight_sum = 0
    
    for i, h in enumerate(last_n):
        w = len(last_n) - i
        omission = get_omission(h["category"], history[1:])
        adjust = 1 + min(omission, 10) * 0.03
        
        fixed_sum += params[h["category"]] * w * adjust
        weight_sum += w * adjust
    
    fixed_sum = fixed_sum / weight_sum if weight_sum > 0 else 0
    
    raw = fixed_sum / (latest["total"] * math.pi)
    decimal = raw - int(raw)
    
    tail1, tail2 = get_two_digits(decimal)
    cat1 = TAIL_TO_CATEGORY[tail1]
    cat2 = TAIL_TO_CATEGORY[tail2]
    
    # 🔥 杀组逻辑
    if cat1 == cat2:
        kill = OPPOSITE[cat1]
    else:
        # 统计近期频率,杀出现多的(追冷)
        freq1 = sum(1 for h in history[1:10] if h["category"] == cat1)
        freq2 = sum(1 for h in history[1:10] if h["category"] == cat2)
        kill = cat1 if freq1 >= freq2 else cat2
    
    return kill, market_state, window_size

def evaluate_params(history, params):
    hits = 0
    total = 0
    for i in range(len(history) - 6):
        train = history[i+1:i+7]
        actual = history[i]
        result = predict_kill_with_params(train, params)
        if result:
            kill, _, _ = result
            if actual["category"] != kill:
                hits += 1
        total += 1
    return hits / total if total > 0 else 0

def adaptive_grid_search(history, iterations=40):
    best_params = {"大单": 12, "小单": 13, "大双": 14, "小双": 15}
    best_score = -1
    
    print("🔍 自适应网格搜索中...")
    
    for _ in range(iterations // 2):
        params = {
            "大单": random.randint(10, 17),
            "小单": random.randint(10, 17),
            "大双": random.randint(11, 17),
            "小双": random.randint(11, 17)
        }
        score = evaluate_params(history, params)
        if score > best_score:
            best_score = score
            best_params = params.copy()
    
    for _ in range(iterations // 2):
        params = {
            "大单": best_params["大单"] + random.randint(-2, 2),
            "小单": best_params["小单"] + random.randint(-2, 2),
            "大双": best_params["大双"] + random.randint(-2, 2),
            "小双": best_params["小双"] + random.randint(-2, 2)
        }
        for k in params:
            params[k] = max(PARAM_RANGES[k][0], min(PARAM_RANGES[k][1], params[k]))
        
        score = evaluate_params(history, params)
        if score > best_score:
            best_score = score
            best_params = params.copy()
    
    print(f"✅ 最优参数: 大单={best_params['大单']}, 小单={best_params['小单']}, 大双={best_params['大双']}, 小双={best_params['小双']}, 胜率={best_score*100:.1f}%")
    return best_params, best_score

def get_latest_data():
    resp = requests.get(API_URL, timeout=10)
    data = resp.json()["data"]
    history = []
    for item in data[:25]:
        nums = item["number"].split("+")
        total = sum(int(x) for x in nums)
        dt = datetime.strptime(f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M:%S")
        history.append({
            "issue": item["nbr"],
            "total": total,
            "category": get_category(total)
        })
    return history

def format_issue_line_kill(issue, kill, mark=""):
    short_issue = issue[-2:] if len(issue) >= 2 else issue.zfill(2)
    return f"{short_issue}期.杀{kill}{mark}"

def check_result_kill(actual, kill):
    if actual["category"] != kill:
        return "🀄️", True
    return "❌", False

def format_total(actual):
    return str(actual['total']).zfill(2)

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for channel in CHANNEL_IDS:
        try:
            requests.post(url, data={"chat_id": channel, "text": text}, timeout=10)
            print(f"已发送到: {channel}")
        except Exception as e:
            print(f"发送到 {channel} 失败: {e}")

def main():
    global consecutive_loss
    
    print("🚀 V7杀组版 机器人启动(自适应网格搜索+遗漏值+连错惩罚)...")
    
    stats = {"hit": 0, "total": 0}
    history_lines = []
    pending_kill = None
    last_issue = None
    best_params = {"大单": 12, "小单": 13, "大双": 14, "小双": 15}
    
    while True:
        try:
            history = get_latest_data()
            if not history:
                time.sleep(PREDICT_INTERVAL)
                continue
            
            current = history[0]
            current_issue = current["issue"]
            
            if current_issue != last_issue:
                if consecutive_loss >= MAX_CONSECUTIVE_LOSS:
                    print(f"⚠️ 连错{consecutive_loss}期,触发惩罚(参数范围减半)")
                    for k in PARAM_RANGES:
                        mid = (PARAM_RANGES[k][0] + PARAM_RANGES[k][1]) / 2
                        PARAM_RANGES[k] = (max(10, mid - 2), min(17, mid + 2))
                else:
                    PARAM_RANGES["大单"] = (10, 17)
                    PARAM_RANGES["小单"] = (10, 17)
                    PARAM_RANGES["大双"] = (11, 17)
                    PARAM_RANGES["小双"] = (11, 17)
                
                best_params, best_score = adaptive_grid_search(history)
                
                if pending_kill is not None:
                    mark, is_hit = check_result_kill(current, pending_kill)
                    stats["total"] += 1
                    if is_hit:
                        stats["hit"] += 1
                        consecutive_loss = 0
                    else:
                        consecutive_loss += 1
                    history_lines[-1] += f"{mark}{format_total(current)}"
                
                result = predict_kill_with_params(history, best_params)
                if result:
                    kill, market_state, window_size = result
                    pending_kill = kill
                    
                    next_issue = str(int(current_issue) + 1)
                    new_line = format_issue_line_kill(next_issue, kill)
                    history_lines.append(new_line)
                    
                    rate = stats["hit"] / stats["total"] if stats["total"] > 0 else 0
                    param_str = f"{best_params['大单']}/{best_params['小单']}/{best_params['大双']}/{best_params['小双']}"
                    punish_tag = "⚡" if consecutive_loss >= MAX_CONSECUTIVE_LOSS else ""
                    full_msg = f"願得一人心(杀组{punish_tag} {market_state}{window_size}期 {param_str})\n" + "\n".join(history_lines[-15:]) + f"\n📊 {stats['hit']}中{stats['total']} 命中率{rate*100:.1f}%"
                    
                    send_message(full_msg)
                    print(f"已发送: {next_issue}期 (杀组, {market_state}, 窗口{window_size}期, 连错{consecutive_loss})")
                
                last_issue = current_issue
            
            time.sleep(PREDICT_INTERVAL)
            
        except Exception as e:
            print(f"错误: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
