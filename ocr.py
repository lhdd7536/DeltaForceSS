"""OCR 识别与文本匹配。

识别函数（空闲/物品名/剩余时间/价格）、模糊匹配与时间解析。
OCR 配置（config['OCR_configs']）与 debug_mode 通过 config_store 实时访问。
"""

import re

import pytesseract
from rapidfuzz import fuzz

import config_store as cs


def time_to_seconds(time_str):
    """解析 'HH:MM:SS' / 'MM:SS' 为秒；解析失败返回 None"""
    if time_str is None:
        return None
    try:
        hh, mm, ss = map(int, time_str.split(':'))
        return hh * 3600 + mm * 60 + ss
    except Exception:
        return None  # 解析失败返回 None 而非固定 1800，避免"完成"状态被误判为"占用中"


def OCR_remain_time(image):
    t_config = r'--psm 7 -c tessedit_char_whitelist=0123456789:'
    text = pytesseract.image_to_string(image, config=t_config)
    if text != '':
        return text.strip()
    return None


def OCR_is_free(image):
    t_config = r'-l chi_sim'
    text = pytesseract.image_to_string(image, config=t_config)
    match_score = fuzz.ratio(text, '空闲中')
    return match_score > 60


def OCR_item_name(image, dep):
    OCR_config = cs.config['OCR_configs'][dep]
    text = pytesseract.image_to_string(image, config=OCR_config)

    # manual improvement
    text = text.replace("番", "盔")
    if cs.debug_mode:
        print(f"List Item OCR: {text}")
    return text.strip()


def OCR_price(image):
    t_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist="0123456789,"'
    text = pytesseract.image_to_string(image, config=t_config)
    price = re.sub(r'[^\d]', '', text)
    if price == '':
        return None
    print(f'✅ OCR 价格: {price}')
    return int(price)


def best_match_item(str1, reference):
    str1 = str1.strip()
    max_score = 0
    best_match = None
    for item in reference:
        score = fuzz.ratio(str1, item)
        if score > max_score:
            max_score = score
            best_match = item
    return best_match, max_score
