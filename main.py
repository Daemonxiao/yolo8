"""
实时视频检测系统主程序
"""

import os
import sys
import signal
import logging
import argparse
import time
import json
from typing import Optional

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config_manager import config_manager
from src.detection_engine import DetectionEngine
from src.stream_manager import StreamManager
from src.alarm_system import AlarmSystem
from src.api_server import APIServer


class VideoDetectionSystem:
    """实时视频检测系统主类"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化系统
        
        Args:
            config_path: 配置文件路径
        """
        # 配置日志
        self._setup_logging()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("初始化实时视频检测系统...")
        
        # 加载配置
        if config_path:
            config_manager.config_path = config_path
            config_manager.reload_config()
        
        # 初始化组件
        self.detection_engine: Optional[DetectionEngine] = None
        self.stream_manager: Optional[StreamManager] = None
        self.alarm_system: Optional[AlarmSystem] = None
        self.api_server: Optional[APIServer] = None
        
        # 系统状态
        self.is_running = False
        
        # 注册信号处理
        self._setup_signal_handlers()
    
    def _setup_logging(self) -> None:
        """配置日志系统"""
        log_config = config_manager.get('logging', {})
        
        # 创建logs目录
        log_file_path = log_config.get('file_path', 'logs/detection.log')
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        
        # 配置日志格式
        log_format = log_config.get(
            'format',
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 配置日志级别
        log_level = getattr(logging, log_config.get('level', 'INFO').upper())
        
        # 配置日志处理器
        handlers = [
            logging.StreamHandler(sys.stdout),  # 控制台输出
            logging.FileHandler(log_file_path, encoding='utf-8')  # 文件输出
        ]
        
        # 应用配置
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=handlers,
            force=True
        )
        
        # 设置第三方库日志级别
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
        if not config_manager.get('api.debug', False):
            logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info(f"接收到信号 {signum}，正在关闭系统...")
            self.shutdown()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Windows系统支持
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, signal_handler)
    
    def initialize(self) -> bool:
        """
        初始化所有组件
        
        Returns:
            是否初始化成功
        """
        try:
            self.logger.info("正在初始化系统组件...")
            
            # 1. 初始化检测引擎
            self.logger.info("初始化检测引擎...")
            self.detection_engine = DetectionEngine()
            
            # 2. 初始化报警系统
            self.logger.info("初始化报警系统...")
            self.alarm_system = AlarmSystem()
            
            # 3. 初始化流管理器
            self.logger.info("初始化流管理器...")
            self.stream_manager = StreamManager(self.detection_engine)
            
            # 4. 注册报警处理器
            self.detection_engine.add_alarm_callback(
                self.alarm_system.process_alarm_event
            )
            
            # 5. 初始化API服务器
            self.logger.info("初始化API服务器...")
            self.api_server = APIServer(self.stream_manager)
            
            self.logger.info("系统组件初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"系统初始化失败: {e}")
            return False
    
    def start(self) -> bool:
        """
        启动系统
        
        Returns:
            是否启动成功
        """
        if self.is_running:
            self.logger.warning("系统已在运行")
            return False
        
        try:
            self.logger.info("启动实时视频检测系统...")
            
            # 检查组件是否已初始化
            if not all([self.detection_engine, self.stream_manager, 
                       self.alarm_system, self.api_server]):
                self.logger.error("系统组件未正确初始化")
                return False
            
            # 启动API服务器
            if not self.api_server.start():
                self.logger.error("API服务器启动失败")
                return False
            
            self.is_running = True
            
            # 显示系统信息
            self._show_system_info()
            
            self.logger.info("实时视频检测系统启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"系统启动失败: {e}")
            return False
    
    def _show_system_info(self) -> None:
        """显示系统信息"""
        api_config = config_manager.get_api_config()
        
        info_lines = [
            "=" * 60,
            "实时视频检测系统",
            "=" * 60,
            f"API服务地址: http://{api_config['host']}:{api_config['port']}",
            f"模型文件: {config_manager.get_model_path()}",
            f"最大流数量: {config_manager.get('detection.max_streams', 10)}",
            f"使用GPU: {config_manager.get('performance.use_gpu', True)}",
            "",
            "主要API接口:",
            f"  健康检查: GET /health",
            f"  注册流: POST /api/v1/streams",
            f"  获取流列表: GET /api/v1/streams",
            f"  启动流: POST /api/v1/streams/{{stream_id}}/start",
            f"  停止流: POST /api/v1/streams/{{stream_id}}/stop",
            f"  删除流: DELETE /api/v1/streams/{{stream_id}}",
            "",
            "按 Ctrl+C 停止系统",
            "=" * 60
        ]
        
        for line in info_lines:
            print(line)
    
    def wait_for_shutdown(self) -> None:
        """等待系统关闭"""
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("接收到中断信号")
            self.shutdown()
    
    def shutdown(self) -> None:
        """关闭系统"""
        if not self.is_running:
            return
        
        self.logger.info("正在关闭实时视频检测系统...")
        self.is_running = False
        
        try:
            # 关闭API服务器
            if self.api_server:
                self.api_server.stop()
            
            # 关闭流管理器
            if self.stream_manager:
                self.stream_manager.shutdown()
            
            # 关闭报警系统
            if self.alarm_system:
                self.alarm_system.shutdown()
            
            # 关闭检测引擎
            if self.detection_engine:
                self.detection_engine.shutdown()
            
            self.logger.info("系统关闭完成")
            
        except Exception as e:
            self.logger.error(f"系统关闭时发生错误: {e}")
    
    def get_system_status(self) -> dict:
        """获取系统状态"""
        status = {
            'is_running': self.is_running,
            'components': {
                'detection_engine': self.detection_engine is not None,
                'stream_manager': self.stream_manager is not None,
                'alarm_system': self.alarm_system is not None,
                'api_server': self.api_server is not None and self.api_server.is_server_running()
            }
        }
        
        if self.stream_manager:
            status['stream_stats'] = self.stream_manager.get_stream_stats()
        
        if self.alarm_system:
            status['alarm_stats'] = self.alarm_system.get_stats()
        
        return status


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='实时视频检测系统')
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config/default_config.yaml',
        help='配置文件路径'
    )
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='以守护进程模式运行'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='显示系统状态'
    )
    
    args = parser.parse_args()
    
    try:
        # 创建系统实例
        system = VideoDetectionSystem(config_path=args.config)
        
        # 如果只是查看状态
        if args.status:
            if system.initialize():
                status = system.get_system_status()
                print("系统状态:")
                print(json.dumps(status, indent=2, ensure_ascii=False))
            return
        
        # 初始化系统
        if not system.initialize():
            print("系统初始化失败")
            sys.exit(1)
        
        # 启动系统
        if not system.start():
            print("系统启动失败")
            sys.exit(1)
        
        # 如果是守护进程模式
        if args.daemon:
            print("系统以守护进程模式运行")
            # 在实际部署中，这里可以使用专门的守护进程库
            # 如 python-daemon
        
        # 等待关闭
        system.wait_for_shutdown()
        
    except Exception as e:
        print(f"系统运行异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
