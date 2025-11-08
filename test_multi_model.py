#!/usr/bin/env python3
"""
测试多模型功能
"""

import sys
sys.path.append('src')

from src.model_manager import model_manager
from src.config_manager import config_manager

def test_model_manager():
    """测试模型管理器"""
    print("=" * 60)
    print("多模型管理器测试")
    print("=" * 60)
    
    # 获取配置的模型
    scene_models = config_manager.get('model.scene_models', {})
    print(f"\n配置的场景模型: {len(scene_models)} 个")
    for scene, model_path in scene_models.items():
        print(f"  - {scene}: {model_path}")
    
    # 预加载所有模型
    print("\n正在预加载模型...")
    model_paths = list(scene_models.values())
    results = model_manager.preload_models(model_paths)
    
    # 显示结果
    print(f"\n预加载结果:")
    for model_path, success in results.items():
        status = "✓" if success else "✗"
        print(f"  {status} {model_path}")
    
    # 显示已加载的模型
    print("\n已加载的模型详情:")
    loaded_models = model_manager.get_loaded_models()
    for model_path, info in loaded_models.items():
        print(f"\n  模型: {model_path}")
        print(f"    - 类别数: {info['num_classes']}")
        print(f"    - 设备: {info['device']}")
        print(f"    - 类别: {list(info['classes'].values())[:5]}...")  # 只显示前5个
    
    print("\n" + "=" * 60)
    print(f"测试完成！成功加载 {len(loaded_models)}/{len(scene_models)} 个模型")
    print("=" * 60)

if __name__ == "__main__":
    test_model_manager()
