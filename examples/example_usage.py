"""
实时视频检测系统使用示例
"""

import sys
import os
import time
import requests
import json

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.config_manager import config_manager
from src.detection_engine import DetectionEngine, DetectionResult, AlarmEvent
from src.stream_manager import StreamManager, StreamConfig
from src.alarm_system import AlarmSystem, AlarmRule, NotificationType


def example_1_basic_detection():
    """示例1: 基础检测功能"""
    print("=== 示例1: 基础检测功能 ===")
    
    # 初始化检测引擎
    engine = DetectionEngine()
    
    # 定义检测结果回调
    def on_detection(result: DetectionResult):
        print(f"检测到 {result.bbox_count} 个目标")
        for detection in result.detections:
            print(f"  - {detection['class_name']}: {detection['confidence']:.2f}")
    
    # 注册回调
    engine.add_detection_callback(on_detection)
    
    # 启动检测（使用摄像头）
    success = engine.start_detection(
        stream_id="test_camera",
        video_source=0,  # 使用默认摄像头
        custom_params={'confidence_threshold': 0.3}
    )
    
    if success:
        print("检测启动成功，运行10秒...")
        time.sleep(10)
        
        # 停止检测
        engine.stop_detection("test_camera")
        print("检测已停止")
    else:
        print("检测启动失败")
    
    # 关闭引擎
    engine.shutdown()


def example_2_stream_management():
    """示例2: 流管理功能"""
    print("\n=== 示例2: 流管理功能 ===")
    
    # 初始化组件
    engine = DetectionEngine()
    manager = StreamManager(engine)
    
    # 创建流配置
    config1 = StreamConfig(
        stream_id="rtsp_camera_1",
        rtsp_url="rtsp://admin:password@192.168.1.100:554/stream",
        name="前门摄像头",
        confidence_threshold=0.4,
        fps_limit=10
    )
    
    config2 = StreamConfig(
        stream_id="rtsp_camera_2", 
        rtsp_url="rtsp://admin:password@192.168.1.101:554/stream",
        name="后门摄像头",
        confidence_threshold=0.5,
        fps_limit=15
    )
    
    # 注册流
    result1 = manager.register_stream(config1)
    result2 = manager.register_stream(config2)
    
    print(f"流1注册结果: {result1['success']}")
    print(f"流2注册结果: {result2['success']}")
    
    # 启动流
    if result1['success']:
        start_result = manager.start_stream("rtsp_camera_1")
        print(f"流1启动结果: {start_result['success']}")
    
    # 获取所有流状态
    streams = manager.get_all_streams()
    print(f"当前管理的流数量: {len(streams)}")
    
    # 等待一段时间
    time.sleep(5)
    
    # 停止并注销流
    manager.stop_stream("rtsp_camera_1")
    manager.unregister_stream("rtsp_camera_1")
    manager.unregister_stream("rtsp_camera_2")
    
    # 关闭管理器
    manager.shutdown()
    engine.shutdown()


def example_3_alarm_system():
    """示例3: 报警系统功能"""
    print("\n=== 示例3: 报警系统功能 ===")
    
    # 初始化报警系统
    alarm_system = AlarmSystem()
    
    # 创建自定义报警规则
    high_priority_rule = AlarmRule(
        rule_id="high_priority",
        name="高优先级报警",
        stream_ids=["camera_001"],
        class_names=["person"],
        min_confidence=0.8,
        consecutive_frames=2,
        cooldown_seconds=20,
        notifications=[NotificationType.LOG, NotificationType.CALLBACK]
    )
    
    # 添加规则
    alarm_system.add_rule(high_priority_rule)
    
    # 模拟报警事件
    mock_alarm = AlarmEvent(
        stream_id="camera_001",
        timestamp=time.time(),
        alarm_type="high",
        confidence=0.85,
        bbox=[100, 50, 200, 150],
        class_name="person",
        consecutive_count=3
    )
    
    # 处理报警事件
    alarm_system.process_alarm_event(mock_alarm)
    
    # 获取统计信息
    stats = alarm_system.get_stats()
    print(f"报警统计: {stats}")
    
    # 关闭系统
    alarm_system.shutdown()


def example_4_api_client():
    """示例4: API客户端使用"""
    print("\n=== 示例4: API客户端使用 ===")
    
    base_url = "http://localhost:8080"
    
    # 检查服务器状态
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            print("服务器状态正常")
            print(f"响应: {response.json()}")
        else:
            print("服务器状态异常")
            return
    except requests.exceptions.ConnectionError:
        print("无法连接到服务器，请确保系统已启动")
        return
    
    # 注册新流
    stream_data = {
        "stream_id": "api_test_stream",
        "rtsp_url": "rtsp://demo:demo@192.168.1.100:554/stream",
        "name": "API测试流",
        "confidence_threshold": 0.3,
        "fps_limit": 20,
        "callback_url": "http://your-callback-server.com/webhook"
    }
    
    response = requests.post(
        f"{base_url}/api/v1/streams",
        json=stream_data,
        headers={'Content-Type': 'application/json'}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"流注册成功: {result}")
        
        # 启动流
        start_response = requests.post(
            f"{base_url}/api/v1/streams/api_test_stream/start"
        )
        
        if start_response.status_code == 200:
            print("流启动成功")
            
            # 等待几秒
            time.sleep(3)
            
            # 获取流状态
            status_response = requests.get(
                f"{base_url}/api/v1/streams/api_test_stream"
            )
            
            if status_response.status_code == 200:
                stream_info = status_response.json()
                print(f"流状态: {stream_info['data']['status']}")
            
            # 停止流
            stop_response = requests.post(
                f"{base_url}/api/v1/streams/api_test_stream/stop"
            )
            print(f"流停止结果: {stop_response.status_code == 200}")
        
        # 删除流
        delete_response = requests.delete(
            f"{base_url}/api/v1/streams/api_test_stream"
        )
        print(f"流删除结果: {delete_response.status_code == 200}")
    
    else:
        print(f"流注册失败: {response.status_code}")
        print(f"错误信息: {response.text}")


def example_5_callback_server():
    """示例5: 回调服务器示例"""
    print("\n=== 示例5: 回调服务器示例 ===")
    
    from flask import Flask, request, jsonify
    import threading
    
    app = Flask(__name__)
    
    @app.route('/webhook', methods=['POST'])
    def webhook():
        """处理检测结果和报警事件的回调"""
        data = request.get_json()
        
        if data['type'] == 'detection':
            print(f"收到检测结果: 流={data['stream_id']}, 目标数量={data['bbox_count']}")
            for detection in data['detections']:
                print(f"  - {detection['class_name']}: {detection['confidence']:.2f}")
        
        elif data['type'] == 'alarm':
            print(f"收到报警事件: 流={data['stream_id']}, 类型={data['alarm_type']}")
            print(f"  目标: {data['class_name']}, 置信度: {data['confidence']:.2f}")
        
        return jsonify({'status': 'ok'})
    
    # 在后台线程中运行Flask服务器
    def run_server():
        app.run(host='localhost', port=5000, debug=False)
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print("回调服务器已启动在 http://localhost:5000")
    print("现在可以将callback_url设置为: http://localhost:5000/webhook")
    
    # 等待用户按键
    input("按回车键停止示例...")


def example_6_configuration():
    """示例6: 配置管理示例"""
    print("\n=== 示例6: 配置管理示例 ===")
    
    # 读取当前配置
    current_model = config_manager.get_model_path()
    detection_params = config_manager.get_detection_params()
    alarm_config = config_manager.get_alarm_config()
    
    print(f"当前模型: {current_model}")
    print(f"检测参数: {detection_params}")
    print(f"报警配置: {alarm_config}")
    
    # 修改配置
    config_manager.set('detection.confidence_threshold', 0.4)
    config_manager.set('alarm.min_confidence', 0.6)
    
    # 批量更新配置
    updates = {
        'detection.fps_limit': 25,
        'alarm.cooldown_seconds': 45,
        'api.debug': True
    }
    config_manager.update_config(updates)
    
    # 保存配置到文件
    config_manager.save_config('config/updated_config.yaml')
    
    print("配置已更新并保存")


def main():
    """主函数"""
    print("实时视频检测系统使用示例")
    print("=" * 50)
    
    # 选择运行的示例
    examples = {
        '1': example_1_basic_detection,
        '2': example_2_stream_management,
        '3': example_3_alarm_system,
        '4': example_4_api_client,
        '5': example_5_callback_server,
        '6': example_6_configuration
    }
    
    print("可用示例:")
    print("1. 基础检测功能")
    print("2. 流管理功能")
    print("3. 报警系统功能") 
    print("4. API客户端使用")
    print("5. 回调服务器示例")
    print("6. 配置管理示例")
    print("0. 运行所有示例")
    
    choice = input("\n请选择要运行的示例 (0-6): ").strip()
    
    if choice == '0':
        # 运行所有示例（除了需要交互的）
        for key in ['1', '2', '3', '6']:
            if key in examples:
                try:
                    examples[key]()
                except Exception as e:
                    print(f"示例 {key} 运行出错: {e}")
    elif choice in examples:
        try:
            examples[choice]()
        except Exception as e:
            print(f"示例运行出错: {e}")
    else:
        print("无效的选择")


if __name__ == "__main__":
    main()
