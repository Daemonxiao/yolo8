#!/usr/bin/env python3
"""
系统功能测试脚本
"""

import sys
import os
import time
import requests
import json
import threading
from typing import Dict, Any

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.config_manager import config_manager
from src.detection_engine import DetectionEngine
from src.stream_manager import StreamManager, StreamConfig
from src.alarm_system import AlarmSystem


class SystemTester:
    """系统测试器"""
    
    def __init__(self):
        self.base_url = "http://localhost:8080"
        self.test_results = []
        
    def log_test(self, test_name: str, success: bool, message: str = ""):
        """记录测试结果"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            'test': test_name,
            'success': success,
            'message': message
        }
        self.test_results.append(result)
        print(f"{status} {test_name}: {message}")
    
    def test_config_manager(self) -> bool:
        """测试配置管理器"""
        print("\n=== 测试配置管理器 ===")
        
        try:
            # 测试配置读取
            model_path = config_manager.get_model_path()
            self.log_test("配置读取", model_path is not None, f"模型路径: {model_path}")
            
            # 测试配置设置
            original_conf = config_manager.get('detection.confidence_threshold')
            config_manager.set('detection.confidence_threshold', 0.123)
            new_conf = config_manager.get('detection.confidence_threshold')
            
            success = new_conf == 0.123
            self.log_test("配置设置", success, f"设置值: {new_conf}")
            
            # 恢复原始值
            config_manager.set('detection.confidence_threshold', original_conf)
            
            return True
            
        except Exception as e:
            self.log_test("配置管理器", False, str(e))
            return False
    
    def test_detection_engine(self) -> bool:
        """测试检测引擎"""
        print("\n=== 测试检测引擎 ===")
        
        try:
            # 初始化引擎
            engine = DetectionEngine()
            self.log_test("引擎初始化", True, "检测引擎创建成功")
            
            # 测试模型加载
            model_loaded = engine.model is not None
            self.log_test("模型加载", model_loaded, "YOLO模型加载状态")
            
            # 测试回调注册
            callback_called = False
            
            def test_callback(result):
                nonlocal callback_called
                callback_called = True
            
            engine.add_detection_callback(test_callback)
            self.log_test("回调注册", True, "检测回调注册成功")
            
            # 清理
            engine.shutdown()
            self.log_test("引擎关闭", True, "检测引擎关闭成功")
            
            return True
            
        except Exception as e:
            self.log_test("检测引擎", False, str(e))
            return False
    
    def test_stream_manager(self) -> bool:
        """测试流管理器"""
        print("\n=== 测试流管理器 ===")
        
        try:
            # 初始化组件
            engine = DetectionEngine()
            manager = StreamManager(engine)
            
            # 创建测试流配置
            test_config = StreamConfig(
                stream_id="test_stream_001",
                rtsp_url="test://fake_url",
                name="测试流",
                confidence_threshold=0.3
            )
            
            # 测试流注册
            result = manager.register_stream(test_config)
            success = result['success']
            self.log_test("流注册", success, result.get('message', ''))
            
            if success:
                # 测试流信息获取
                stream_info = manager.get_stream_info("test_stream_001")
                info_success = stream_info is not None
                self.log_test("流信息获取", info_success, "获取流详细信息")
                
                # 测试流注销
                unreg_result = manager.unregister_stream("test_stream_001")
                unreg_success = unreg_result['success']
                self.log_test("流注销", unreg_success, unreg_result.get('message', ''))
            
            # 清理
            manager.shutdown()
            engine.shutdown()
            
            return True
            
        except Exception as e:
            self.log_test("流管理器", False, str(e))
            return False
    
    def test_alarm_system(self) -> bool:
        """测试报警系统"""
        print("\n=== 测试报警系统 ===")
        
        try:
            # 初始化报警系统
            alarm_system = AlarmSystem()
            
            # 测试规则获取
            rules = alarm_system.get_all_rules()
            rules_success = isinstance(rules, list)
            self.log_test("规则获取", rules_success, f"获取到 {len(rules)} 个规则")
            
            # 测试统计信息
            stats = alarm_system.get_stats()
            stats_success = isinstance(stats, dict) and 'total_alarms' in stats
            self.log_test("统计获取", stats_success, "获取报警统计信息")
            
            # 清理
            alarm_system.shutdown()
            
            return True
            
        except Exception as e:
            self.log_test("报警系统", False, str(e))
            return False
    
    def test_api_server(self) -> bool:
        """测试API服务器"""
        print("\n=== 测试API服务器 ===")
        
        try:
            # 测试健康检查
            response = requests.get(f"{self.base_url}/health", timeout=5)
            health_success = response.status_code == 200
            self.log_test("健康检查", health_success, f"状态码: {response.status_code}")
            
            if health_success:
                # 测试系统信息
                response = requests.get(f"{self.base_url}/api/v1/info", timeout=5)
                info_success = response.status_code == 200
                self.log_test("系统信息", info_success, f"状态码: {response.status_code}")
                
                # 测试流列表
                response = requests.get(f"{self.base_url}/api/v1/streams", timeout=5)
                streams_success = response.status_code == 200
                self.log_test("流列表", streams_success, f"状态码: {response.status_code}")
                
                # 测试配置获取
                response = requests.get(f"{self.base_url}/api/v1/config", timeout=5)
                config_success = response.status_code == 200
                self.log_test("配置获取", config_success, f"状态码: {response.status_code}")
            
            return health_success
            
        except requests.exceptions.ConnectionError:
            self.log_test("API连接", False, "无法连接到API服务器")
            return False
        except Exception as e:
            self.log_test("API服务器", False, str(e))
            return False
    
    def test_full_workflow(self) -> bool:
        """测试完整工作流程"""
        print("\n=== 测试完整工作流程 ===")
        
        try:
            # 测试流注册、启动、停止、删除的完整流程
            stream_data = {
                "stream_id": "workflow_test_stream",
                "rtsp_url": "test://workflow_test",
                "name": "工作流程测试流",
                "confidence_threshold": 0.3
            }
            
            # 1. 注册流
            response = requests.post(
                f"{self.base_url}/api/v1/streams",
                json=stream_data,
                timeout=5
            )
            
            register_success = response.status_code == 200
            self.log_test("工作流-注册", register_success, f"状态码: {response.status_code}")
            
            if register_success:
                stream_id = stream_data["stream_id"]
                
                # 2. 获取流信息
                response = requests.get(
                    f"{self.base_url}/api/v1/streams/{stream_id}",
                    timeout=5
                )
                get_success = response.status_code == 200
                self.log_test("工作流-获取", get_success, f"状态码: {response.status_code}")
                
                # 3. 尝试启动流（预期会失败，因为是假的URL）
                response = requests.post(
                    f"{self.base_url}/api/v1/streams/{stream_id}/start",
                    timeout=5
                )
                # 这里预期失败是正常的
                start_attempted = response.status_code in [200, 400]
                self.log_test("工作流-启动尝试", start_attempted, "尝试启动检测")
                
                # 4. 删除流
                response = requests.delete(
                    f"{self.base_url}/api/v1/streams/{stream_id}",
                    timeout=5
                )
                delete_success = response.status_code == 200
                self.log_test("工作流-删除", delete_success, f"状态码: {response.status_code}")
                
                return register_success and get_success and delete_success
            
            return False
            
        except Exception as e:
            self.log_test("完整工作流程", False, str(e))
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        print("🧪 开始系统功能测试")
        print("=" * 50)
        
        # 运行各项测试
        tests = [
            ("配置管理器", self.test_config_manager),
            ("检测引擎", self.test_detection_engine),
            ("流管理器", self.test_stream_manager),
            ("报警系统", self.test_alarm_system),
            ("API服务器", self.test_api_server),
            ("完整工作流程", self.test_full_workflow)
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                results[test_name] = test_func()
            except Exception as e:
                results[test_name] = False
                self.log_test(f"{test_name}(异常)", False, str(e))
        
        # 生成测试报告
        self.generate_report(results)
        
        return results
    
    def generate_report(self, results: Dict[str, bool]) -> None:
        """生成测试报告"""
        print("\n" + "=" * 50)
        print("📊 测试报告")
        print("=" * 50)
        
        passed = sum(1 for success in results.values() if success)
        total = len(results)
        
        print(f"总测试数: {total}")
        print(f"通过数: {passed}")
        print(f"失败数: {total - passed}")
        print(f"通过率: {passed/total*100:.1f}%")
        
        print("\n详细结果:")
        for test_result in self.test_results:
            status = "✅" if test_result['success'] else "❌"
            print(f"{status} {test_result['test']}: {test_result['message']}")
        
        if passed == total:
            print("\n🎉 所有测试通过！系统功能正常。")
        else:
            print(f"\n⚠️  有 {total - passed} 个测试失败，请检查相关功能。")
        
        # 保存测试报告
        report_file = "test_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': time.time(),
                'summary': {
                    'total': total,
                    'passed': passed,
                    'failed': total - passed,
                    'pass_rate': passed/total*100
                },
                'results': results,
                'details': self.test_results
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存至: {report_file}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='系统功能测试')
    parser.add_argument(
        '--api-url',
        default='http://localhost:8080',
        help='API服务器地址 (默认: http://localhost:8080)'
    )
    parser.add_argument(
        '--test',
        choices=['config', 'engine', 'stream', 'alarm', 'api', 'workflow', 'all'],
        default='all',
        help='指定要运行的测试'
    )
    
    args = parser.parse_args()
    
    # 创建测试器
    tester = SystemTester()
    tester.base_url = args.api_url
    
    # 运行指定测试
    if args.test == 'all':
        results = tester.run_all_tests()
    else:
        test_map = {
            'config': tester.test_config_manager,
            'engine': tester.test_detection_engine,
            'stream': tester.test_stream_manager,
            'alarm': tester.test_alarm_system,
            'api': tester.test_api_server,
            'workflow': tester.test_full_workflow
        }
        
        test_func = test_map[args.test]
        success = test_func()
        
        results = {args.test: success}
        tester.generate_report(results)
    
    # 根据测试结果设置退出码
    all_passed = all(results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
