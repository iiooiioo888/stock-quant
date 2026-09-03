#!/usr/bin/env python3
"""
proxy_collector.py - 批量采集免费代理 + 验证 + 存入 TXT 文件
依赖：pip install requests beautifulsoup4 lxml
"""
import requests
from bs4 import BeautifulSoup
import threading
import queue
import time
import re

# ================= 配置 =================
TEST_URL = "http://httpbin.org/ip"       # 验证目标
TIMEOUT = 5                               # 请求超时
THREADS = 50                              # 验证线程数
OUTPUT_FILE = "valid_proxies.txt"         # 输出文件
# =========================================

# ---------- 采集源定义 ----------
def fetch_kuaidaili():
    """快代理免费高匿页"""
    proxies = []
    urls = [
        'https://www.kuaidaili.com/free/inha/1/',
        'https://www.kuaidaili.com/free/inha/2/'
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, 'lxml')
            table = soup.find('table', class_='table-bordered')
            if not table:
                continue
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 7:
                    continue
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                protocol = cols[3].text.strip().lower()
                proxies.append({'ip': ip, 'port': port, 'protocol': protocol})
        except Exception as e:
            print(f"采集快代理出错: {e}")
    return proxies

def fetch_89ip():
    """89免费代理"""
    proxies = []
    url = 'http://www.89ip.cn/'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        pattern = r'<tr>.*?<td>(\d+\.\d+\.\d+\.\d+)</td>.*?<td>(\d+)</td>'
        matches = re.findall(pattern, r.text, re.DOTALL)
        for ip, port in matches:
            proxies.append({'ip': ip, 'port': port, 'protocol': 'http'})
    except Exception as e:
        print(f"采集89ip出错: {e}")
    return proxies

def fetch_proxy_list_org():
    """proxy-list.org（需 base64 解码）"""
    proxies = []
    url = 'https://proxy-list.org/english/index.php'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        for item in soup.select('div.proxy'):
            encoded = item.get('data-ip', '')
            try:
                import base64
                decoded = base64.b64decode(encoded).decode()
                parts = decoded.split(':')
                if len(parts) == 2:
                    proxies.append({'ip': parts[0], 'port': parts[1], 'protocol': 'http'})
            except:
                pass
    except Exception as e:
        print(f"采集proxy-list.org出错: {e}")
    return proxies

def fetch_github_raw():
    """GitHub 公共代理列表"""
    proxies = []
    url = 'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/proxies.txt'
    try:
        r = requests.get(url, timeout=10)
        for line in r.text.splitlines():
            line = line.strip()
            if line and ':' in line:
                ip, port = line.split(':')[:2]
                proxies.append({'ip': ip, 'port': port, 'protocol': 'http'})
    except Exception as e:
        print(f"采集GitHub出错: {e}")
    return proxies

# 所有采集源
SOURCE_FUNCTIONS = [fetch_kuaidaili, fetch_89ip, fetch_proxy_list_org, fetch_github_raw]

# ---------- 验证器 ----------
def test_proxy(proxy_dict):
    """
    验证单个代理，成功返回 (proxy_dict_with_latency) 否则 None
    """
    ip = proxy_dict['ip']
    port = proxy_dict['port']
    protocol = proxy_dict['protocol']
    proxy_url = f"{protocol}://{ip}:{port}"
    proxies = {'http': proxy_url, 'https': proxy_url}
    try:
        start = time.time()
        r = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT)
        latency = round(time.time() - start, 3)
        if r.status_code == 200:
            data = r.json()
            if ip in data.get('origin', ''):
                proxy_dict['latency'] = latency
                return proxy_dict
    except:
        pass
    return None

# ---------- 主流程 ----------
def run():
    print("开始采集免费代理...")
    all_proxies = []
    for func in SOURCE_FUNCTIONS:
        try:
            result = func()
            print(f"  {func.__name__}: {len(result)} 个")
            all_proxies.extend(result)
        except Exception as e:
            print(f"  {func.__name__} 出错: {e}")

    # 去重（ip:port:protocol）
    seen = set()
    unique = []
    for p in all_proxies:
        key = f"{p['ip']}:{p['port']}:{p['protocol']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)
    print(f"去重后待验证: {len(unique)} 个")

    # 多线程验证
    print(f"开始验证 (并发 {THREADS})...")
    q = queue.Queue()
    for p in unique:
        q.put(p)

    valid = []
    lock = threading.Lock()

    def worker():
        while not q.empty():
            p = q.get()
            res = test_proxy(p)
            if res:
                with lock:
                    valid.append(res)
            q.task_done()

    threads = []
    for _ in range(min(THREADS, len(unique))):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    q.join()
    for t in threads:
        t.join(timeout=1)

    # 按延迟排序
    valid.sort(key=lambda x: x.get('latency', 999))

    # 输出到文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for p in valid:
            line = f"{p['protocol']}://{p['ip']}:{p['port']}\n"
            f.write(line)

    print(f"\n验证完成！有效代理: {len(valid)} 个")
    print(f"已保存到: {OUTPUT_FILE}")

    # 显示延迟最低的 5 个
    print("\n延迟最低的 5 个代理：")
    for p in valid[:5]:
        print(f"  {p['protocol']}://{p['ip']}:{p['port']}  延迟: {p.get('latency', '?')}s")

if __name__ == '__main__':
    run()