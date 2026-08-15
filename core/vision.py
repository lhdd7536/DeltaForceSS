"""截图与图像处理。

截屏（PIL ImageGrab → OpenCV 灰度/Otsu 二值化）、裁剪、单元格切分、
调试图像保存与列表分割线检测。可变状态（OUTPUT_DIR / debug_mode /
departments_coords）通过 config_store 实时访问。
"""

import hashlib
import os
from datetime import datetime

import cv2
import numpy as np
from PIL import ImageGrab

from core import config_store as cs


# Image
def cut_by_lines(list_img, horizontal_lines, min_area, prefix='cell'):
    '''
    return list of (image, y position) array
    '''
    cells = []
    height, width = list_img.shape
    horizontal_lines.append(height)
    horizontal_lines = sorted(horizontal_lines)

    prev_y = 0
    for y in horizontal_lines:
        if y > prev_y:
            cell = list_img[prev_y:y, 0:width]
            # area = # black pixel
            area = cell.size
            if area > min_area:
                # center y coord
                center_y = prev_y + (y - prev_y) // 2
                cells.append((cell, center_y))
            prev_y = y
    return cells


# Screenshot
def screenshot(type='binary', hint='placeholder', region=None):
    """
    region (x, y, w, h)
    """
    if region:
        x, y, w, h = region
        pil_img = ImageGrab.grab(bbox=(x, y, x+w, y+h))
    else:
        pil_img = ImageGrab.grab()

    frame = np.array(pil_img)

    if frame is None:
        raise Exception(f'! Failed: screenshot !')

    original_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)
    otsu_thresh, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    min_thresh = 50
    final_thresh = max(otsu_thresh, min_thresh)
    if not region:
        final_thresh -= 10

    _, binary = cv2.threshold(gray, final_thresh, 255, cv2.THRESH_BINARY)

    if cs.debug_mode:
        red_channel = original_img[:, :, 2]
        _, red_binary = cv2.threshold(red_channel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        combined_binary = cv2.bitwise_xor(binary, red_binary)
        save_image([
            (original_img, f'{hint}_original', None),
            (gray, f'{hint}_gray', None),
            (binary, f'{hint}_binary', None),
            (combined_binary, f'{hint}_combinedBinary', None)
        ])

    if type == 'binary':
        return binary
    elif type == 'original':
        return original_img
    elif type == 'gray':
        return gray
    elif type == 'combined_binary':
        red_channel = original_img[:, :, 2]
        _, red_binary = cv2.threshold(red_channel, 128, 255, cv2.THRESH_BINARY)
        combined_binary = cv2.bitwise_xor(binary, red_binary)
        return combined_binary
    else:
        raise ValueError('! Error: unsupported image type !')


def cropImage(image, region):
    x, y, w, h = region
    cropped = image[y:y+h, x:x+w]

    if cs.debug_mode:
        save_image([(cropped, 'cropped', region)])
    return cropped


# Debug
def show_image(image):
    cv2.imshow('image', image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def save_image(image_hint_region_tuples):
    '''
    (image, hint, region)
    '''
    timestamp = datetime.now().strftime("%H_%M_%S_%f")[:-3]  # hh:mm:ss:sss
    for image, hint, region in image_hint_region_tuples:
        if region:
            x, y, w, h = region
            cv2.imwrite(os.path.join(cs.OUTPUT_DIR, f'{timestamp}_{hint}_{x},{y},{w},{h}.png'), image)
        else:
            cv2.imwrite(os.path.join(cs.OUTPUT_DIR, f'{timestamp}_{hint}.png'), image)


def debug_visualize_lines(image, lines):
    # Create a copy of the image in RGB format
    image_with_lines = cv2.cvtColor(image.copy(), cv2.COLOR_BGR2RGB)

    # Draw all lines on the image
    for line in lines:
        x1, y1, x2, y2 = line[0]
        cv2.line(image_with_lines, (x1, y1), (x2, y2), (0, 255, 0), 1)  # green line thickness = 1 px

    # show_image(image_with_lines)

    # Generate unique hash from image data
    image_hash = hashlib.md5(image_with_lines.tobytes()).hexdigest()[:8]

    save_image([(image_with_lines, 'list_lines', None)])


def match_list_items():
    x, y = cs.departments_coords['list_point']
    w, h = cs.departments_coords['list_size']
    list_OCR_img = screenshot('gray', 'list', (x, y, w, h))
    list_edge_img = cv2.Canny(list_OCR_img, 10, 40)

    if list_edge_img is None or list_OCR_img is None:
        raise Exception('! Error: fail to capture list image !')

    list_size = cs.departments_coords['list_size']
    item_size = cs.departments_coords['item_size']
    minLength = list_size[0] * 0.8
    minArea = int(item_size[0] * item_size[1] * 0.8)

    # find split lines
    lines = cv2.HoughLinesP(list_edge_img, 1, np.pi / 180, threshold=100, minLineLength=minLength, maxLineGap=50)

    if cs.debug_mode:
        debug_visualize_lines(list_edge_img, lines)

    if lines is None:
        raise Exception('! Error: no line was found !')
    horizontal_lines = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if abs(y2 - y1) < 5:  # k approx 0
            horizontal_lines.append(y1)
    if horizontal_lines is None:
        raise Exception('! Error: no horizontal line was found, check debug image !')

    # cut image
    cells = cut_by_lines(list_OCR_img, horizontal_lines, minArea)

    if cells:
        return cells
    raise Exception('! Error: cells is empty. Please check images !')
