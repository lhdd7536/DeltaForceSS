"""共享工具函数"""
import random
import time
import locale


def calc_jitter(seconds):
    """计算 ±20% 随机波动后的时长（最大抖动 30s），不执行休眠"""
    jitter = min(seconds * 0.2, 30)
    return max(0.1, seconds + random.uniform(-jitter, jitter))


def jitter_sleep(seconds):
    """休眠（加入 ±20% 随机波动，最大 30s）"""
    time.sleep(calc_jitter(seconds))


def read_with_encoding_fallback(path, primary='utf-8', fallback='gbk'):
    """读取文件，主编码失败时回退到备用编码。

    用于兼容中文 Windows 下可能以 GBK 保存的旧配置文件。
    写操作一律使用 UTF-8，确保新文件编码统一。
    """
    try:
        with open(path, 'r', encoding=primary) as f:
            return f.read()
    except UnicodeDecodeError:
        print(f"[utils] 文件编码不是 {primary}，尝试 {fallback} 编码读取: {path}")
        with open(path, 'r', encoding=fallback) as f:
            return f.read()
