"""共享工具函数"""
import random
import time


def calc_jitter(seconds):
    """计算 ±20% 随机波动后的时长（最大抖动 30s），不执行休眠"""
    jitter = min(seconds * 0.2, 30)
    return max(0.1, seconds + random.uniform(-jitter, jitter))


def jitter_sleep(seconds):
    """休眠（加入 ±20% 随机波动，最大 30s）"""
    time.sleep(calc_jitter(seconds))
