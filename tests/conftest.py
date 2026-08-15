"""pytest 公共配置：将项目根目录加入 sys.path，便于测试导入业务模块"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
