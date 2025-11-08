#!/usr/bin/env python3
"""
测试 API 路由注册
"""

import sys
sys.path.insert(0, 'src')

from flask import Flask

# 创建一个简单的 Flask 应用来测试路由
app = Flask(__name__)

# 模拟路由注册
@app.route('/api/v1/algorithms', methods=['GET'])
def get_algorithms():
    return {'success': True}

# 列出所有路由
print("=" * 60)
print("Flask 路由列表:")
print("=" * 60)

for rule in app.url_map.iter_rules():
    methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
    print(f"{rule.rule:50s} [{methods}]")

print("\n" + "=" * 60)
print(f"总共 {len(list(app.url_map.iter_rules()))} 个路由")
print("=" * 60)

