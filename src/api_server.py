"""
REST API服务器
提供视频流管理的HTTP接口
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import json
import time
from typing import Dict, Any, Optional
from dataclasses import asdict
import threading
import requests

from .stream_manager import StreamManager, StreamConfig
from .detection_engine import DetectionEngine, DetectionResult, AlarmEvent
from .config_manager import config_manager


class APIServer:
    """REST API服务器"""
    
    def __init__(self, stream_manager: StreamManager):
        """
        初始化API服务器
        
        Args:
            stream_manager: 流管理器实例
        """
        self.logger = logging.getLogger(__name__)
        self.stream_manager = stream_manager
        
        # 获取API配置
        self.api_config = config_manager.get_api_config()
        
        # 创建Flask应用
        self.app = Flask(__name__)
        
        # 配置CORS
        CORS(self.app, origins=self.api_config.get('cors_origins', ['*']))
        
        # 配置日志
        if not self.api_config.get('debug', False):
            logging.getLogger('werkzeug').setLevel(logging.WARNING)
        
        # 注册路由
        self._register_routes()
        
        # 服务器状态
        self.server_thread: Optional[threading.Thread] = None
        self.is_running = False
        
        # 回调错误计数（用于熔断机制）
        self.callback_error_counts: Dict[str, int] = {}  # stream_id -> error_count
        self.callback_disabled: Dict[str, bool] = {}     # stream_id -> is_disabled
        
        self.logger.info("API服务器初始化完成")
    
    def _register_routes(self) -> None:
        """注册API路由"""
        
        # 健康检查
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """健康检查接口"""
            return jsonify({
                'status': 'healthy',
                'timestamp': time.time(),
                'version': self.api_config.get('version', 'v1'),
                'streams': len(self.stream_manager.get_all_streams())
            })
        
        # 获取系统信息
        @self.app.route('/api/v1/info', methods=['GET'])
        def get_system_info():
            """获取系统信息"""
            try:
                stats = self.stream_manager.get_stream_stats()
                return jsonify({
                    'success': True,
                    'data': {
                        'system_info': stats,
                        'config': {
                            'max_streams': config_manager.get('detection.max_streams', 10),
                            'model_path': config_manager.get_model_path(),
                            'detection_params': config_manager.get_detection_params()
                        }
                    }
                })
            except Exception as e:
                self.logger.error(f"获取系统信息失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 注册视频流
        @self.app.route('/api/v1/streams', methods=['POST'])
        def register_stream():
            """注册新的视频流"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': '请求数据不能为空'
                    }), 400
                
                # 验证必需字段
                required_fields = ['stream_id', 'rtsp_url']
                for field in required_fields:
                    if field not in data:
                        return jsonify({
                            'success': False,
                            'error': f'缺少必需字段: {field}'
                        }), 400
                
                # 创建流配置
                config = StreamConfig(
                    stream_id=data['stream_id'],
                    rtsp_url=data['rtsp_url'],
                    name=data.get('name', ''),
                    description=data.get('description', ''),
                    confidence_threshold=data.get('confidence_threshold', 0.5),
                    iou_threshold=data.get('iou_threshold', 0.45),
                    fps_limit=data.get('fps_limit', 1),
                    callback_url=data.get('callback_url', ''),
                    alarm_enabled=data.get('alarm_enabled', True),
                    save_results=data.get('save_results', False),
                    tags=data.get('tags', [])
                )
                
                # 注册流
                result = self.stream_manager.register_stream(config)
                
                # 注册回调函数（如果提供了callback_url）
                if result['success'] and config.callback_url:
                    self._register_stream_callbacks(config.stream_id, config.callback_url)
                
                return jsonify(result), 200 if result['success'] else 400
                
            except Exception as e:
                self.logger.error(f"注册视频流失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 删除视频流
        @self.app.route('/api/v1/streams/<stream_id>', methods=['DELETE'])
        def unregister_stream(stream_id: str):
            """删除视频流"""
            try:
                result = self.stream_manager.unregister_stream(stream_id)
                return jsonify(result), 200 if result['success'] else 400
                
            except Exception as e:
                self.logger.error(f"删除视频流失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 启动视频流
        @self.app.route('/api/v1/streams/<stream_id>/start', methods=['POST'])
        def start_stream(stream_id: str):
            """启动视频流检测"""
            try:
                result = self.stream_manager.start_stream(stream_id)
                return jsonify(result), 200 if result['success'] else 400
                
            except Exception as e:
                self.logger.error(f"启动视频流失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 停止视频流
        @self.app.route('/api/v1/streams/<stream_id>/stop', methods=['POST'])
        def stop_stream(stream_id: str):
            """停止视频流检测"""
            try:
                result = self.stream_manager.stop_stream(stream_id)
                return jsonify(result), 200 if result['success'] else 400
                
            except Exception as e:
                self.logger.error(f"停止视频流失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 获取视频流信息
        @self.app.route('/api/v1/streams/<stream_id>', methods=['GET'])
        def get_stream_info(stream_id: str):
            """获取视频流详细信息"""
            try:
                stream_info = self.stream_manager.get_stream_info(stream_id)
                if stream_info is None:
                    return jsonify({
                        'success': False,
                        'error': f'流ID不存在: {stream_id}'
                    }), 404
                
                return jsonify({
                    'success': True,
                    'data': stream_info
                })
                
            except Exception as e:
                self.logger.error(f"获取视频流信息失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 获取所有视频流
        @self.app.route('/api/v1/streams', methods=['GET'])
        def get_all_streams():
            """获取所有视频流信息"""
            try:
                streams = self.stream_manager.get_all_streams()
                return jsonify({
                    'success': True,
                    'data': {
                        'streams': streams,
                        'total': len(streams)
                    }
                })
                
            except Exception as e:
                self.logger.error(f"获取视频流列表失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 更新视频流配置
        @self.app.route('/api/v1/streams/<stream_id>/config', methods=['PUT'])
        def update_stream_config(stream_id: str):
            """更新视频流配置"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': '请求数据不能为空'
                    }), 400
                
                result = self.stream_manager.update_stream_config(stream_id, data)
                return jsonify(result), 200 if result['success'] else 400
                
            except Exception as e:
                self.logger.error(f"更新视频流配置失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 获取统计信息
        @self.app.route('/api/v1/stats', methods=['GET'])
        def get_stats():
            """获取系统统计信息"""
            try:
                stats = self.stream_manager.get_stream_stats()
                return jsonify({
                    'success': True,
                    'data': stats
                })
                
            except Exception as e:
                self.logger.error(f"获取统计信息失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 配置管理
        @self.app.route('/api/v1/config', methods=['GET'])
        def get_config():
            """获取系统配置"""
            try:
                return jsonify({
                    'success': True,
                    'data': {
                        'detection_params': config_manager.get_detection_params(),
                        'alarm_config': config_manager.get_alarm_config(),
                        'api_config': config_manager.get_api_config(),
                        'model_path': config_manager.get_model_path()
                    }
                })
                
            except Exception as e:
                self.logger.error(f"获取配置失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/v1/config', methods=['PUT'])
        def update_config():
            """更新系统配置"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': '请求数据不能为空'
                    }), 400
                
                # 更新配置
                config_manager.update_config(data)
                
                return jsonify({
                    'success': True,
                    'message': '配置更新成功'
                })
                
            except Exception as e:
                self.logger.error(f"更新配置失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # 错误处理
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                'success': False,
                'error': '接口不存在'
            }), 404
        
        @self.app.errorhandler(405)
        def method_not_allowed(error):
            return jsonify({
                'success': False,
                'error': '方法不被允许'
            }), 405
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({
                'success': False,
                'error': '服务器内部错误'
            }), 500
    
    def _register_stream_callbacks(self, stream_id: str, callback_url: str) -> None:
        """注册流的回调函数"""
        def detection_callback(result: DetectionResult):
            """检测结果回调"""
            # 检查回调是否被禁用（熔断）
            if self.callback_disabled.get(stream_id, False):
                return
            
            try:
                payload = {
                    'type': 'detection',
                    'stream_id': result.stream_id,
                    'timestamp': result.timestamp,
                    'frame_id': result.frame_id,
                    'detections': result.detections,
                    'bbox_count': result.bbox_count,
                    'processing_time': result.processing_time
                }
                
                response = requests.post(
                    callback_url,
                    json=payload,
                    timeout=5,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code != 200:
                    self._handle_callback_error(stream_id, f"状态码: {response.status_code}")
                else:
                    # 成功回调，重置错误计数
                    self.callback_error_counts[stream_id] = 0
                
            except Exception as e:
                self._handle_callback_error(stream_id, str(e))
        
        def alarm_callback(alarm: AlarmEvent):
            """报警事件回调"""
            try:
                payload = {
                    'type': 'alarm',
                    'stream_id': alarm.stream_id,
                    'timestamp': alarm.timestamp,
                    'alarm_type': alarm.alarm_type,
                    'confidence': alarm.confidence,
                    'bbox': alarm.bbox,
                    'class_name': alarm.class_name,
                    'consecutive_count': alarm.consecutive_count
                }
                
                response = requests.post(
                    callback_url,
                    json=payload,
                    timeout=5,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code != 200:
                    self.logger.warning(
                        f"报警回调响应异常: {stream_id}, "
                        f"状态码: {response.status_code}"
                    )
                
            except Exception as e:
                self.logger.error(f"报警回调发送失败: {stream_id}, {e}")
        
        # 注册回调
        self.stream_manager.register_callback(stream_id, 'detection', detection_callback)
        self.stream_manager.register_callback(stream_id, 'alarm', alarm_callback)
        
        self.logger.info(f"已注册回调函数: {stream_id} -> {callback_url}")
    
    def _handle_callback_error(self, stream_id: str, error_msg: str) -> None:
        """处理回调错误（熔断机制）"""
        # 增加错误计数
        current_count = self.callback_error_counts.get(stream_id, 0)
        self.callback_error_counts[stream_id] = current_count + 1
        
        # 检查是否需要熔断
        if self.callback_error_counts[stream_id] >= 10:  # 连续10次错误后熔断
            self.callback_disabled[stream_id] = True
            self.logger.error(
                f"流 {stream_id} 回调连续失败{self.callback_error_counts[stream_id]}次，已禁用回调: {error_msg}"
            )
        elif self.callback_error_counts[stream_id] % 3 == 0:  # 每3次错误记录一次
            self.logger.warning(
                f"流 {stream_id} 回调错误 ({self.callback_error_counts[stream_id]}/10): {error_msg}"
            )
    
    def enable_stream_callback(self, stream_id: str) -> None:
        """重新启用流的回调（手动恢复）"""
        self.callback_disabled[stream_id] = False
        self.callback_error_counts[stream_id] = 0
        self.logger.info(f"流 {stream_id} 回调已重新启用")
    
    def start(self) -> bool:
        """启动API服务器"""
        if self.is_running:
            self.logger.warning("API服务器已在运行")
            return False
        
        try:
            host = self.api_config.get('host', '0.0.0.0')
            port = self.api_config.get('port', 8080)
            debug = self.api_config.get('debug', False)
            
            self.logger.info(f"启动API服务器: {host}:{port}")
            
            # 在单独线程中运行Flask应用
            self.server_thread = threading.Thread(
                target=self._run_server,
                args=(host, port, debug),
                daemon=True
            )
            
            self.is_running = True
            self.server_thread.start()
            
            return True
            
        except Exception as e:
            self.logger.error(f"启动API服务器失败: {e}")
            self.is_running = False
            return False
    
    def _run_server(self, host: str, port: int, debug: bool) -> None:
        """运行Flask服务器"""
        try:
            self.app.run(
                host=host,
                port=port,
                debug=debug,
                threaded=True,
                use_reloader=False  # 避免在线程中重载
            )
        except Exception as e:
            self.logger.error(f"Flask服务器运行异常: {e}")
        finally:
            self.is_running = False
    
    def stop(self) -> None:
        """停止API服务器"""
        if not self.is_running:
            self.logger.warning("API服务器未在运行")
            return
        
        self.logger.info("正在停止API服务器...")
        self.is_running = False
        
        # 等待服务器线程结束
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5.0)
        
        self.logger.info("API服务器已停止")
    
    def is_server_running(self) -> bool:
        """检查服务器是否在运行"""
        return self.is_running
