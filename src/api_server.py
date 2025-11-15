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
        
        # ========== 算法查询接口 ==========
        
        # 获取支持的算法列表
        @self.app.route('/api/algorithms', methods=['GET'])
        def get_algorithms():
            """获取所有支持的算法"""
            try:
                from .model_manager import model_manager
                
                # 获取算法配置
                algorithm_info = self.stream_manager.scene_manager.scene_mapper.get_algorithm_info()
                
                # 获取已加载的模型
                loaded_models = model_manager.get_loaded_models()
                
                # 组合信息
                algorithms = {}
                for algorithm, info in algorithm_info.items():
                    model_path = info['model_path']
                    algorithms[algorithm] = {
                        'model_path': model_path,
                        'file_exists': info['exists'],
                        # 'model_loaded': model_path in loaded_models,
                        # 'target_classes': info.get('target_classes', [])
                    }
                
                return jsonify({
                    'success': True,
                    'data': {
                        'algorithms': algorithms,
                        'total': len(algorithms)
                    }
                }), 200
                
            except Exception as e:
                self.logger.error(f"获取算法列表异常: {e}", exc_info=True)
                return jsonify({
                    'success': False,
                    'message': f'服务器内部错误: {str(e)}'
                }), 500
        
        # ========== 场景管理接口 ==========
        
        # 场景下发接口（新版，符合外部平台要求）
        @self.app.route('/api/sceneIssue', methods=['POST'])
        def scene_issue():
            """
            算法场景下发接口（符合外部平台规范）
            
            支持三种日期类型：
            - type=1: 指定开始和结束的日期时间
            - type=2: 指定月份和每天的时间段
            - type=3: 指定每天的时间段
            """
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'status': 1,
                        'message': '请求数据不能为空'
                    }), 400
                
                # 记录接收到的请求
                self.logger.info(f"收到场景下发请求: {json.dumps(data, ensure_ascii=False)}")
                
                # 验证必需字段
                required_fields = ['devices', 'sceneId', 'algorithmCode', 'type', 'start', 'end']
                missing_fields = [f for f in required_fields if f not in data]
                if missing_fields:
                    return jsonify({
                        'status': 1,
                        'message': f'缺少必需字段: {", ".join(missing_fields)}'
                    }), 400
                
                # 解析参数
                scene_id = str(data.get('sceneId'))  # 统一转换为字符串
                algorithm_code = data.get('algorithmCode')
                devices = data.get('devices', [])
                date_type = str(data.get('type'))  # 统一转换为字符串
                start_time = data.get('start')
                end_time = data.get('end')
                month = data.get('month', [])
                
                # 验证设备列表不为空
                if not devices:
                    return jsonify({
                        'status': 1,
                        'message': '设备列表不能为空'
                    }), 400
                
                # Type 2 时验证 month
                if date_type == "2" and not month:
                    return jsonify({
                        'status': 1,
                        'message': 'type=2时，month字段不能为空'
                    }), 400
                
                # 验证 date_type 有效性
                if date_type not in ["1", "2", "3"]:
                    return jsonify({
                        'status': 1,
                        'message': 'type参数错误，必须为1、2或3'
                    }), 400
                
                # 调用场景管理器处理
                result = self.stream_manager.scene_manager.deploy_scene_v2(
                    scene_id=scene_id,
                    algorithm_code=algorithm_code,
                    devices=devices,
                    date_type=date_type,
                    start_time=start_time,
                    end_time=end_time,
                    month=month,
                )
                
                # 返回结果
                if result.get('status') == 0:
                    self.logger.info(f"场景下发成功: sceneId={scene_id}, algorithmCode={algorithm_code}")
                    return jsonify(result), 200
                else:
                    self.logger.warning(f"场景下发失败: {result.get('message')}")
                    return jsonify(result), 400
                    
            except Exception as e:
                self.logger.error(f"场景下发异常: {e}", exc_info=True)
                return jsonify({
                    'status': 1,
                    'message': f'服务器内部错误: {str(e)}'
                }), 500
        
        # 场景启停接口
        @self.app.route('/api/sceneStartStop', methods=['POST'])
        def scene_start_stop():
            """
            场景启停接口
            
            参数：
            - sceneId: 场景ID
            - status: 启动(1)或停止(0)
            """
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'status': 1,
                        'message': '请求数据不能为空'
                    }), 400
                
                scene_id = data.get('sceneId')
                status = data.get('status')
                
                # 验证必需字段
                if scene_id is None or status is None:
                    return jsonify({
                        'status': 1,
                        'message': '缺少必需字段: sceneId 或 status'
                    }), 400
                
                # 统一转换类型
                scene_id = str(scene_id)
                
                # 转换和验证 status
                try:
                    status = int(status)
                except (ValueError, TypeError):
                    return jsonify({
                        'status': 1,
                        'message': 'status必须为整数0或1'
                    }), 400
                
                if status not in [0, 1]:
                    return jsonify({
                        'status': 1,
                        'message': 'status参数错误，必须为0或1'
                    }), 400
                
                self.logger.info(f"收到场景启停请求: sceneId={scene_id}, status={status}")
                
                if status == 1:
                    # 启动场景
                    result = self.stream_manager.scene_manager.start_scene(scene_id)
                else:  # status == 0
                    # 停止场景
                    result = self.stream_manager.scene_manager.stop_scene(scene_id)
                
                if result.get('status') == 0:
                    action = "启动" if status == 1 else "停止"
                    self.logger.info(f"场景{action}成功: sceneId={scene_id}")
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400
                    
            except Exception as e:
                self.logger.error(f"场景启停异常: {e}", exc_info=True)
                return jsonify({
                    'status': 1,
                    'message': f'服务器内部错误: {str(e)}'
                }), 500
        
        # 图片上传接口
        @self.app.route('/api/file/uploadAlarmImage', methods=['POST'])
        def upload_alarm_image():
            """
            上传告警图片接口
            
            这是一个代理接口，将图片转发到外部平台
            """
            try:
                # 检查是否有文件
                if 'file' not in request.files:
                    return jsonify({
                        'status': 1,
                        'message': '未找到文件'
                    }), 400
                
                file = request.files['file']
                
                if file.filename == '':
                    return jsonify({
                        'status': 1,
                        'message': '文件名为空'
                    }), 400
                
                # 调用设备平台客户端上传图片
                result = self.stream_manager.scene_manager.device_client.upload_alarm_image(file)
                
                if result.get('status') == 0:
                    self.logger.info(f"图片上传成功: {result.get('data', {}).get('path')}")
                    return jsonify(result), 200
                else:
                    self.logger.warning(f"图片上传失败: {result.get('message')}")
                    return jsonify(result), 400
                    
            except Exception as e:
                self.logger.error(f"图片上传异常: {e}", exc_info=True)
                return jsonify({
                    'status': 1,
                    'message': f'服务器内部错误: {str(e)}'
                }), 500
        
        # 获取场景列表
        @self.app.route('/api/scenes', methods=['GET'])
        def get_scenes():
            """
            获取所有场景列表
            用于查询当前系统中的所有场景状态
            """
            try:
                scenes = self.stream_manager.scene_manager.get_all_scenes()
                
                return jsonify({
                    'status': 0,
                    'message': '获取成功',
                    'data': {
                        'scenes': scenes,
                        'total': len(scenes)
                    }
                }), 200
                    
            except Exception as e:
                self.logger.error(f"获取场景列表异常: {e}", exc_info=True)
                return jsonify({
                    'status': 1,
                    'message': f'服务器内部错误: {str(e)}'
                }), 500
        
        # ========== 内部管理接口（已删除）==========
        # 根据接入文档要求，以下内部管理接口已删除：
        # - /api/v1/streams/* (流管理)
        # - /api/v1/stats (统计信息)
        # - /api/v1/info (系统信息)
        # - /api/v1/config (配置管理)
        # 
        # 如需内部调试，请查看日志或使用场景查询接口
        
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
    
    # 回调函数相关方法已删除
    # 告警通过 AlarmSystem 和 Kafka 直接推送，不再使用 HTTP 回调
    
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
