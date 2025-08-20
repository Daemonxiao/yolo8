#!/usr/bin/env python3
"""
简单的视频检测测试脚本
无需RTSP服务器，直接使用文件和摄像头测试
"""

import sys
import os
import time
import requests
import json

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_with_video_file():
    """使用视频文件测试"""
    print("🎬 使用视频文件测试检测功能")
    print("=" * 40)
    
    # 检查测试视频是否存在
    test_video = "test_video.mp4"
    if not os.path.exists(test_video):
        print("❌ 测试视频不存在，正在创建...")
        create_test_video()
    
    api_url = "http://localhost:8080"
    
    # 检查API服务器
    try:
        response = requests.get(f"{api_url}/health", timeout=5)
        if response.status_code != 200:
            print("❌ API服务器未启动，请先运行: python main.py")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到API服务器，请先运行: python main.py")
        return False
    
    print("✅ API服务器连接正常")
    
    # 注册视频文件作为流
    stream_data = {
        "stream_id": "test_video_file",
        "rtsp_url": os.path.abspath(test_video),  # 使用文件绝对路径
        "name": "测试视频文件",
        "confidence_threshold": 0.3,
        "fps_limit": 5  # 降低FPS以便观察
    }
    
    print(f"📝 注册视频流: {stream_data['rtsp_url']}")
    
    # 注册流
    response = requests.post(
        f"{api_url}/api/v1/streams",
        json=stream_data,
        headers={'Content-Type': 'application/json'}
    )
    
    if response.status_code == 200:
        print("✅ 视频流注册成功")
        
        # 启动检测
        print("🚀 启动检测...")
        start_response = requests.post(
            f"{api_url}/api/v1/streams/test_video_file/start"
        )
        
        if start_response.status_code == 200:
            print("✅ 检测启动成功")
            
            # 等待一段时间查看结果
            print("⏰ 等待检测结果...")
            for i in range(10):
                time.sleep(2)
                
                # 获取流状态
                status_response = requests.get(
                    f"{api_url}/api/v1/streams/test_video_file"
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    stream_info = status_data.get('data', {})
                    
                    print(f"第{i+1}次检查 - 状态: {stream_info.get('status', 'unknown')}, "
                          f"处理帧数: {stream_info.get('frame_count', 0)}, "
                          f"检测数: {stream_info.get('detection_count', 0)}")
                
                if i == 9:
                    print("✅ 检测测试完成")
            
            # 停止检测
            print("⏹️ 停止检测...")
            stop_response = requests.post(
                f"{api_url}/api/v1/streams/test_video_file/stop"
            )
            print("✅ 检测已停止" if stop_response.status_code == 200 else "❌ 停止失败")
            
        else:
            print(f"❌ 检测启动失败: {start_response.status_code}")
        
        # 删除流
        print("🗑️ 清理测试流...")
        delete_response = requests.delete(
            f"{api_url}/api/v1/streams/test_video_file"
        )
        print("✅ 测试流已删除" if delete_response.status_code == 200 else "❌ 删除失败")
        
        return True
        
    else:
        print(f"❌ 视频流注册失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return False


def test_with_camera():
    """使用摄像头测试"""
    print("\n📹 使用摄像头测试检测功能")
    print("=" * 40)
    
    api_url = "http://localhost:8080"
    
    # 注册摄像头流
    stream_data = {
        "stream_id": "test_camera",
        "rtsp_url": "0",  # 默认摄像头
        "name": "测试摄像头",
        "confidence_threshold": 0.5,
        "fps_limit": 1  # 改为1帧/秒便于观察
    }
    
    print("📝 注册摄像头流...")
    
    # 注册流
    response = requests.post(
        f"{api_url}/api/v1/streams",
        json=stream_data,
        headers={'Content-Type': 'application/json'}
    )
    
    if response.status_code == 200:
        print("✅ 摄像头流注册成功")
        
        # 启动检测
        print("🚀 启动摄像头检测...")
        start_response = requests.post(
            f"{api_url}/api/v1/streams/test_camera/start"
        )
        
        if start_response.status_code == 200:
            print("✅ 摄像头检测启动成功")
            print("📸 请在摄像头前移动物体进行测试...")
            
            # 等待一段时间查看结果
            for i in range(15):
                time.sleep(2)
                
                # 获取流状态
                status_response = requests.get(
                    f"{api_url}/api/v1/streams/test_camera"
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    stream_info = status_data.get('data', {})
                    
                    print(f"第{i+1}次检查 - 状态: {stream_info.get('status', 'unknown')}, "
                          f"处理帧数: {stream_info.get('frame_count', 0)}, "
                          f"检测数: {stream_info.get('detection_count', 0)}")
            
            print("✅ 摄像头检测测试完成")
            
            # 停止检测
            print("⏹️ 停止摄像头检测...")
            stop_response = requests.post(
                f"{api_url}/api/v1/streams/test_camera/stop"
            )
            print("✅ 摄像头检测已停止" if stop_response.status_code == 200 else "❌ 停止失败")
            
        else:
            print(f"❌ 摄像头检测启动失败: {start_response.status_code}")
            result = start_response.json()
            print(f"错误信息: {result.get('error', '未知错误')}")
        
        # 删除流
        print("🗑️ 清理摄像头流...")
        delete_response = requests.delete(
            f"{api_url}/api/v1/streams/test_camera"
        )
        print("✅ 摄像头流已删除" if delete_response.status_code == 200 else "❌ 删除失败")
        
        return True
        
    else:
        print(f"❌ 摄像头流注册失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return False


def create_test_video():
    """创建测试视频"""
    import subprocess
    
    print("🎬 创建测试视频...")
    
    # 检查ffmpeg是否可用
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ FFmpeg未安装，无法创建测试视频")
        print("请手动放置一个MP4视频文件命名为 test_video.mp4")
        return False
    
    # 创建测试视频
    cmd = [
        'ffmpeg', '-f', 'lavfi', '-i', 'testsrc2=duration=30:size=640x480:rate=10',
        '-c:v', 'libx264', '-preset', 'fast', '-y', 'test_video.mp4'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("✅ 测试视频创建成功: test_video.mp4")
            return True
        else:
            print(f"❌ 测试视频创建失败: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ 测试视频创建超时")
        return False
    except Exception as e:
        print(f"❌ 创建测试视频时发生错误: {e}")
        return False


def show_system_stats():
    """显示系统统计信息"""
    print("\n📊 系统统计信息")
    print("=" * 40)
    
    api_url = "http://localhost:8080"
    
    try:
        # 获取系统统计
        response = requests.get(f"{api_url}/api/v1/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()['data']
            print(f"活跃流数量: {stats.get('active_streams', 0)}")
            print(f"总处理帧数: {stats.get('total_frames_processed', 0)}")
            print(f"总检测数量: {stats.get('total_detections', 0)}")
            
            engine_stats = stats.get('engine_stats', {})
            print(f"引擎处理帧数: {engine_stats.get('total_frames', 0)}")
            print(f"平均FPS: {engine_stats.get('average_fps', 0):.2f}")
            print(f"平均处理时间: {engine_stats.get('average_processing_time', 0):.3f}s")
        else:
            print("❌ 无法获取系统统计信息")
            
    except Exception as e:
        print(f"❌ 获取统计信息失败: {e}")


def main():
    """主函数"""
    print("🧪 简单视频检测测试")
    print("==================")
    
    # 检查API服务器是否运行
    try:
        response = requests.get("http://localhost:8080/health", timeout=5)
        if response.status_code == 200:
            print("✅ 检测系统API服务器运行正常")
        else:
            print("❌ API服务器状态异常")
            return
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到API服务器")
        print("请先在另一个终端中启动检测系统:")
        print("  python main.py")
        return
    
    # 选择测试方式
    print("\n请选择测试方式:")
    print("1. 使用视频文件测试")
    print("2. 使用摄像头测试")
    print("3. 显示系统统计")
    print("0. 退出")
    
    while True:
        try:
            choice = input("\n请输入选择 (0-3): ").strip()
            
            if choice == '1':
                success = test_with_video_file()
                if success:
                    show_system_stats()
                break
                
            elif choice == '2':
                success = test_with_camera()
                if success:
                    show_system_stats()
                break
                
            elif choice == '3':
                show_system_stats()
                break
                
            elif choice == '0':
                print("👋 测试结束")
                break
                
            else:
                print("❌ 无效选择，请重新输入")
                
        except KeyboardInterrupt:
            print("\n👋 测试被中断")
            break
        except Exception as e:
            print(f"❌ 发生错误: {e}")
            break


if __name__ == "__main__":
    main()
