"""pytest 根配置：把项目根加入 sys.path，让测试能 `import backend.xxx`。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
