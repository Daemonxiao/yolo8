#!/usr/bin/env python3
"""
基础功能测试脚本
"""

import sys
import os

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """测试基本导入"""
    print("测试基本导入...")
    
    try:
        print("导入配置管理器...")
        from src.config_manager import config_manager
        print("✅ 配置管理器导入成功")
        
        print("导入检测引擎...")
        from src.detection_engine import DetectionEngine
        print("✅ 检测引擎导入成功")
        
        print("导入流管理器...")
        from src.stream_manager import StreamManager
        print("✅ 流管理器导入成功")
        
        print("导入报警系统...")
        from src.alarm_system import AlarmSystem
        print("✅ 报警系统导入成功")
        
        print("导入API服务器...")
        from src.api_server import APIServer
        print("✅ API服务器导入成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_basic_initialization():
    """测试基本初始化"""
    print("\n测试基本初始化...")
    
    try:
        from src.config_manager import config_manager
        from src.detection_engine import DetectionEngine
        from src.alarm_system import AlarmSystem
        
        print("初始化检测引擎...")
        engine = DetectionEngine()
        print("✅ 检测引擎初始化成功")
        
        print("初始化报警系统...")
        alarm_system = AlarmSystem()
        print("✅ 报警系统初始化成功")
        
        print("关闭组件...")
        alarm_system.shutdown()
        engine.shutdown()
        print("✅ 组件关闭成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return False

def main():
    """主函数"""
    print("🧪 基础功能测试")
    print("=" * 30)
    
    # 测试导入
    import_success = test_imports()
    
    if import_success:
        # 测试初始化
        init_success = test_basic_initialization()
        
        if init_success:
            print("\n🎉 所有基础测试通过！")
            print("系统基本功能正常，可以尝试启动完整服务。")
        else:
            print("\n⚠️ 初始化测试失败")
    else:
        print("\n⚠️ 导入测试失败")
        print("请检查依赖安装和Python环境")

if __name__ == "__main__":
    main()
