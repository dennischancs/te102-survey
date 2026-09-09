#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TE102 助听器用户内测问卷 - 本地预览服务器
双击运行或在命令行执行: python start_server.py
功能: 启动本地HTTP服务器 -> 自动打开浏览器 -> 保持运行直到 Ctrl+C
"""

import http.server
import socketserver
import webbrowser
import os
import sys
import time
import threading

# ============ 配置 ============
PORT = 8765              # 服务器端口
HOST = "127.0.0.1"       # 绑定地址（仅本地访问）
OPEN_BROWSER = True       # 是否自动打开浏览器
BROWSER_DELAY = 1.5       # 打开浏览器前等待秒数（确保服务器已就绪）

# 项目目录 = 脚本所在目录
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def check_port(host, port):
    """检测端口是否被占用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            return True  # 端口被占用
        except (ConnectionRefusedError, OSError):
            return False  # 端口可用


def find_available_port(host, start_port, max_tries=20):
    """从 start_port 开始找一个可用端口"""
    for i in range(max_tries):
        port = start_port + i
        if not check_port(host, port):
            return port
    return None


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """静默请求处理器，只输出关键信息"""

    def log_message(self, format, *args):
        # 静默处理 favicon.ico 的 404
        try:
            msg = format % args
        except Exception:
            return
        if "favicon.ico" in msg:
            return
        # 只记录非 200 的请求和 HTML/JSON/JS/CSS 请求
        if " 200 " not in msg or any(ext in msg for ext in (".html", ".json", ".js", ".css")):
            timestamp = time.strftime("%H:%M:%S")
            print(f"  [{timestamp}] {msg}")


def open_browser_later(url, delay):
    """延迟打开浏览器"""
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url, new=2)
            print(f"\n  ✅ 浏览器已打开: {url}")
        except Exception as e:
            print(f"\n  ⚠️  自动打开浏览器失败，请手动访问: {url}")
            print(f"     原因: {e}")
    threading.Thread(target=_open, daemon=True).start()


def main():
    # 切换到项目目录
    os.chdir(PROJECT_DIR)

    # 检查必要文件
    index_file = os.path.join(PROJECT_DIR, "index.html")
    json_file = os.path.join(PROJECT_DIR, "questions.json")
    if not os.path.exists(index_file):
        print(f"❌ 错误: 找不到 index.html")
        print(f"   请确保本脚本与 index.html 在同一目录下")
        input("\n按回车键退出...")
        sys.exit(1)
    if not os.path.exists(json_file):
        print(f"⚠️  警告: 找不到 questions.json，问卷数据将无法加载")

    # 打印启动信息
    print("=" * 56)
    print("  TE102 助听器用户内测问卷 - 本地预览服务器")
    print("=" * 56)
    print(f"  项目目录: {PROJECT_DIR}")
    print()

    # 查找可用端口
    port = find_available_port(HOST, PORT)
    if port is None:
        print(f"❌ 错误: 从端口 {PORT} 开始的 {20} 个端口均被占用")
        input("\n按回车键退出...")
        sys.exit(1)
    if port != PORT:
        print(f"  ℹ️  端口 {PORT} 被占用，已自动切换到端口 {port}")

    url = f"http://{HOST}:{port}/index.html"

    # 启动服务器
    try:
        with socketserver.TCPServer((HOST, port), QuietHandler) as httpd:
            print(f"  🚀 服务器已启动")
            print(f"  📡 访问地址: {url}")
            print(f"  🌐 局域网访问: http://<你的IP>:{port}/index.html")
            print()
            print("  按 Ctrl+C 停止服务器")
            print("-" * 56)

            # 自动打开浏览器
            if OPEN_BROWSER:
                open_browser_later(url, BROWSER_DELAY)

            # 保持运行
            httpd.serve_forever()

    except KeyboardInterrupt:
        print("\n")
        print("-" * 56)
        print("  👋 服务器已停止")
        print("=" * 56)
    except OSError as e:
        if "10048" in str(e) or "Address already in use" in str(e):
            print(f"❌ 错误: 端口 {port} 被占用")
            print(f"   请关闭占用该端口的程序，或修改脚本中的 PORT 值")
        else:
            print(f"❌ 错误: {e}")
        input("\n按回车键退出...")
        sys.exit(1)


if __name__ == "__main__":
    main()
