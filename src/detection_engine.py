"""
实时检测引擎
负责处理视频流的实时目标检测
"""

import cv2
import torch
import threading
import time
import queue
import logging
import os
import json
from datetime import datetime, time as dt_time
from typing import Dict, List, Callable, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from ultralytics import YOLO
import numpy as np
from .config_manager import config_manager
from .gaode_weather import GaodeWeather
from .model_manager import model_manager


@dataclass
class DetectionResult:
    """检测结果数据类"""
    stream_id: str
    timestamp: float
    frame_id: int
    detections: List[Dict[str, Any]]
    confidence_scores: List[float]
    bbox_count: int
    processing_time: float
    # 告警图片URL（用于Kafka推送和外部访问）
    image_url: str = ""
    # 告警录像URL（预留字段）
    record_url: str = ""


@dataclass
class AlarmEvent:
    """报警事件数据类"""
    stream_id: str
    timestamp: float
    alarm_type: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    class_name: str
    consecutive_count: int
    image_url: str = ""  # 告警图片URL
    record_url: str = ""  # 告警录像URL（预留）


@dataclass
class StreamEvent:
    """流状态事件数据类"""
    stream_id: str
    timestamp: float
    event_type: str  # "connected", "disconnected", "error", "reconnecting"
    message: str = ""


class DetectionEngine:
    """实时检测引擎"""

    def __init__(self):
        """初始化检测引擎"""
        self.logger = logging.getLogger(__name__)

        # 配置参数
        self.model_path = config_manager.get_model_path()
        self.detection_params = config_manager.get_detection_params()
        self.alarm_config = config_manager.get_alarm_config()

        # 模型加载
        self.model: Optional[YOLO] = None
        self.device = self._get_device()
        self._load_model()

        # 状态管理
        self.is_running = False
        self.active_streams: Dict[str, Dict] = {}
        self.detection_threads: Dict[str, threading.Thread] = {}
        self.result_queues: Dict[str, queue.Queue] = {}

        # 报警状态跟踪
        self.alarm_states: Dict[str, Dict] = {}  # stream_id -> {class_name: consecutive_count}
        self.last_alarm_time: Dict[str, float] = {}  # stream_id -> timestamp

        # 回调函数
        self.detection_callbacks: List[Callable[[DetectionResult], None]] = []
        self.alarm_callbacks: List[Callable[[AlarmEvent], None]] = []
        self.stream_callbacks: List[Callable[[StreamEvent], None]] = []

        # 性能统计
        self.stats = {
            'total_frames': 0,
            'total_detections': 0,
            'average_fps': 0.0,
            'average_processing_time': 0.0
        }

        # 结果保存配置
        self.save_results = config_manager.get('storage.save_results', True)
        self.save_images = config_manager.get('storage.save_images', True)
        self.results_path = config_manager.get('storage.results_path', 'results/')
        self.images_path = config_manager.get('storage.images_path', 'results/images/')

        # 图像质量配置
        self.image_format = config_manager.get('storage.image_format', 'png')
        self.jpeg_quality = config_manager.get('storage.jpeg_quality', 100)
        self.png_compression = config_manager.get('storage.png_compression', 1)
        self.capture_width = config_manager.get('storage.capture_width', 640)
        self.capture_height = config_manager.get('storage.capture_height', 480)
        
        # 服务器公网URL配置（用于生成告警图片访问地址）
        self.server_public_url = config_manager.get('server.public_url', 'http://localhost:8080')
        self.logger.info(f"服务器公网URL: {self.server_public_url}")

        # 类别名称映射（可选的中文化）
        self.custom_class_names = config_manager.get('detection.custom_class_names', {}) or {}

        # 自定义类别
        self.custom_type = config_manager.get('detection.custom_type', '')
        self.custom_params = config_manager.get('detection.custom_params', {})

        # 自动缩放配置
        self.auto_resize = config_manager.get('detection.auto_resize', True)
        self.max_resolution = config_manager.get('detection.max_resolution', 640)

        # 类别过滤配置
        self.target_classes = config_manager.get('detection.target_classes', [])
        if self.target_classes:
            self.logger.info(f"启用类别过滤，只检测: {self.target_classes}")
        else:
            self.logger.info("未设置类别过滤，将检测所有类别")

        # 自定义处理类型配置（全局配置，所有流共享）
        # 注意：custom_type 现在是每个流独立配置的，不再从全局配置读取
        self.custom_type_config = config_manager.get('detection.custom_type_config', {})
        
        # 预加载所有可能的处理器配置（延迟初始化，在第一次使用时初始化）
        # 这样每个流可以使用不同的 custom_type，但共享配置
        self._initialized_handlers = set()  # 记录已初始化的处理器类型
        
        self.logger.info("自定义处理器配置已加载，将在流启动时按需初始化")

        # 确保保存目录存在
        if self.save_results or self.save_images:
            os.makedirs(self.results_path, exist_ok=True)
            os.makedirs(self.images_path, exist_ok=True)

        self.logger.info("检测引擎初始化完成")

    def _initialize_handler_for_type(self, custom_type: str) -> None:
        """
        延迟初始化指定类型的处理器（按需初始化）
        
        Args:
            custom_type: 自定义处理类型
        """
        try:
            if custom_type == "high_temperature_alert":
                # 初始化高温检测处理器
                self._init_high_temperature_handler()
            elif custom_type == "morning_meeting_alert":
                # 初始化安全晨会预警处理器
                self._init_morning_meeting_handler()
            elif custom_type == "weather_safety_alert":
                # 初始化防台防汛施工预警处理器
                self._init_weather_safety_handler()
            elif custom_type == "helmet_detection_alert":
                # 初始化安全帽检测预警处理器
                self._init_helmet_detection_handler()

            # 在这里可以添加更多自定义类型
            # elif custom_type == "other_type":
            #     self._init_other_handler()

            self.logger.info(f"自定义处理器 [{custom_type}] 初始化完成")

        except Exception as e:
            self.logger.error(f"自定义处理器初始化失败: {e}")
            raise

    def _init_high_temperature_handler(self) -> None:
        """初始化高温检测处理器"""
        # 高温阈值配置
        self.temperature_threshold = self.custom_type_config.get('temperature_threshold', 35.0)
        self.temperature_check_enabled = self.custom_type_config.get('enabled', True)

        # 温度获取方式配置
        temp_source = self.custom_type_config.get('temperature_source', 'api')

        if temp_source == 'api':
            # 从API获取温度
            self._init_temperature_api()
        elif temp_source == 'sensor':
            # 从传感器获取温度（预留）
            self._init_temperature_sensor()
        else:
            # 使用固定温度值
            self.fixed_temperature = self.custom_type_config.get('fixed_temperature', 25.0)
            self.logger.info(f"使用固定温度值: {self.fixed_temperature}°C")

        self.logger.info(f"高温检测阈值: {self.temperature_threshold}°C")

    def _init_temperature_api(self) -> None:
        """初始化温度API"""
        try:
            # 导入天气API模块
            from .gaode_weather import GaodeWeather

            api_key = self.custom_type_config.get('api_key', '')
            city = self.custom_type_config.get('city', '北京')

            if not api_key:
                self.logger.warning("未配置天气API密钥，使用固定温度值")
                self.fixed_temperature = 25.0
                return

            self.weather_api = GaodeWeather(api_key=api_key, city=city)
            self.logger.info(f"天气API初始化完成: 城市={city}")

        except ImportError:
            self.logger.warning("天气API模块不可用，使用固定温度值")
            self.fixed_temperature = 25.0
        except Exception as e:
            self.logger.error(f"天气API初始化失败: {e}")
            self.fixed_temperature = 25.0

    def _init_temperature_sensor(self) -> None:
        """初始化温度传感器（预留接口）"""
        self.logger.info("温度传感器接口预留，当前使用固定温度值")
        self.fixed_temperature = 25.0

    def _init_morning_meeting_handler(self) -> None:
        """初始化安全晨会预警处理器"""
        # 晨会时间配置
        self.meeting_start_time = self.custom_type_config.get('meeting_start_time', '08:00')
        self.meeting_end_time = self.custom_type_config.get('meeting_end_time', '08:30')
        # 晨会持续有人判定时长（分钟），默认5分钟
        self.meeting_required_minutes = self.custom_type_config.get('meeting_required_minutes', 5)
        self.meeting_check_enabled = self.custom_type_config.get('enabled', True)
        
        # 工作日配置（0=周一, 6=周日）
        self.meeting_weekdays = self.custom_type_config.get('weekdays', [0, 1, 2, 3, 4])  # 默认周一到周五
        
        # 人员类别配置
        self.person_class_names = self.custom_type_config.get('person_class_names', ['person', '人', '人员'])
        
        # 告警状态跟踪 - 简化为每日重置
        self.meeting_alert_states = {}  # stream_id -> {'alert_sent_today': bool, 'last_check_date': date}
        
        self.logger.info(f"安全晨会预警配置:")
        self.logger.info(f"  - 晨会时间: {self.meeting_start_time} - {self.meeting_end_time}")
        self.logger.info(f"  - 判定时长: {self.meeting_required_minutes} 分钟（连续有人视为已召开）")
        self.logger.info(f"  - 工作日: {self.meeting_weekdays}")
        self.logger.info(f"  - 人员类别: {self.person_class_names}")

    def _init_weather_safety_handler(self) -> None:
        """初始化防台防汛施工预警处理器"""
        # 风力阈值配置
        self.wind_power_threshold = self.custom_type_config.get('wind_power_threshold', 6)  # 默认6级风以上
        self.weather_safety_enabled = self.custom_type_config.get('enabled', True)
        
        # 危险天气关键词配置
        self.dangerous_weather_keywords = self.custom_type_config.get('dangerous_weather_keywords', 
                                                                     ['特大暴雨', '大暴雨', '暴雨', '台风', '飓风', '强风'])
        
        # 天气数据源配置
        weather_source = self.custom_type_config.get('weather_source', 'api')
        
        if weather_source == 'api':
            # 从API获取天气数据
            self._init_weather_safety_api()
        else:
            # 使用固定值进行测试
            self.fixed_wind_power = self.custom_type_config.get('fixed_wind_power', 3)
            self.fixed_weather_type = self.custom_type_config.get('fixed_weather_type', '晴')
            self.logger.info(f"使用固定天气值: 风力{self.fixed_wind_power}级, 天气{self.fixed_weather_type}")
        
        self.logger.info(f"防台防汛施工预警配置:")
        self.logger.info(f"  - 风力阈值: {self.wind_power_threshold}级")
        self.logger.info(f"  - 危险天气关键词: {self.dangerous_weather_keywords}")

    def _init_weather_safety_api(self) -> None:
        """初始化防台防汛天气API"""
        try:
            # 导入天气API模块
            from .gaode_weather import GaodeWeather

            api_key = self.custom_type_config.get('api_key', '')
            city = self.custom_type_config.get('city', '北京')

            if not api_key:
                self.logger.warning("未配置天气API密钥，使用固定天气值")
                self.fixed_wind_power = 3
                self.fixed_weather_type = '晴'
                return

            self.weather_safety_api = GaodeWeather(api_key=api_key, city=city)
            self.logger.info(f"防台防汛天气API初始化完成: 城市={city}")

        except ImportError:
            self.logger.warning("天气API模块不可用，使用固定天气值")
            self.fixed_wind_power = 3
            self.fixed_weather_type = '晴'
        except Exception as e:
            self.logger.error(f"防台防汛天气API初始化失败: {e}")
            self.fixed_wind_power = 3
            self.fixed_weather_type = '晴'

    def _init_helmet_detection_handler(self) -> None:
        """初始化安全帽检测预警处理器"""
        # 是否启用安全帽检测
        self.helmet_detection_enabled = self.custom_type_config.get('helmet_detection_enabled', True)
        
        # 人员类别配置
        self.helmet_person_class_names = self.custom_type_config.get('person_class_names', ['person', '人', '人员'])
        
        # 安全帽类别配置
        self.helmet_class_names = self.custom_type_config.get('helmet_class_names', ['helmet', 'hardhat', '安全帽', '头盔'])
        
        self.logger.info(f"安全帽检测预警配置:")
        self.logger.info(f"  - 启用状态: {self.helmet_detection_enabled}")
        self.logger.info(f"  - 人员类别: {self.helmet_person_class_names}")
        self.logger.info(f"  - 安全帽类别: {self.helmet_class_names}")

    def _get_device(self) -> str:
        """获取计算设备"""
        if config_manager.get('performance.use_gpu', True) and torch.cuda.is_available():
            device_id = config_manager.get('performance.gpu_device', 0)
            return f'cuda:{device_id}'
        return 'cpu'

    def _load_model(self) -> None:
        """加载YOLO模型"""
        try:
            self.logger.info(f"加载模型: {self.model_path}")

            # 设置torch安全加载（兼容性处理）
            if hasattr(torch.serialization, 'add_safe_globals'):
                from ultralytics.nn.tasks import DetectionModel
                from ultralytics.nn.modules.conv import Conv
                torch.serialization.add_safe_globals([DetectionModel, Conv])

            # 临时替换torch.load以支持旧模型
            original_torch_load = torch.load

            def safe_torch_load(*args, **kwargs):
                kwargs['weights_only'] = False
                return original_torch_load(*args, **kwargs)

            torch.load = safe_torch_load

            # 加载模型
            self.model = YOLO(self.model_path)

            # 恢复原始torch.load
            torch.load = original_torch_load

            # 设置设备
            if self.device != 'cpu':
                self.model.to(self.device)

            self.logger.info(f"模型加载成功，使用设备: {self.device}")

        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            raise

    def add_detection_callback(self, callback: Callable[[DetectionResult], None]) -> None:
        """添加检测结果回调函数"""
        self.detection_callbacks.append(callback)
        self.logger.info("添加检测结果回调函数")

    def add_alarm_callback(self, callback: Callable[[AlarmEvent], None]) -> None:
        """添加报警回调函数"""
        self.alarm_callbacks.append(callback)
        self.logger.info("添加报警回调函数")

    def add_stream_callback(self, callback: Callable[[StreamEvent], None]) -> None:
        """添加流状态回调函数"""
        self.stream_callbacks.append(callback)
        self.logger.info("添加流状态回调函数")

    def _send_stream_event(self, stream_id: str, event_type: str, message: str = "") -> None:
        """发送流状态事件"""
        event = StreamEvent(
            stream_id=stream_id,
            timestamp=time.time(),
            event_type=event_type,
            message=message
        )

        for callback in self.stream_callbacks:
            try:
                callback(event)
            except Exception as e:
                self.logger.error(f"流状态回调函数执行失败: {e}")

    def start_detection(self, stream_id: str, video_source: str,
                        custom_params: Optional[Dict] = None,
                        model_path: Optional[str] = None,
                        target_classes: Optional[List[str]] = None,
                        custom_type: Optional[str] = None) -> bool:
        """
        开始检测指定视频流
        
        Args:
            stream_id: 视频流唯一标识
            video_source: 视频源（RTSP URL、文件路径等）
            custom_params: 自定义检测参数
            model_path: 指定使用的模型路径（可选，默认使用配置中的模型）
            target_classes: 目标检测类别列表（可选，为空则检测所有类别）
            custom_type: 自定义处理类型（可选，如 "helmet_detection_alert"）
            
        Returns:
            是否成功启动
        """
        if stream_id in self.active_streams:
            self.logger.warning(f"视频流已存在: {stream_id}")
            return False

        try:
            # 确定使用的模型路径
            if model_path is None:
                model_path = self.model_path
            
            # 确保模型已加载
            model = model_manager.get_model(model_path)
            if model is None:
                self.logger.error(f"无法加载模型: {model_path}")
                return False
            
            # 测试视频源连接
            cap = cv2.VideoCapture(video_source)
            if not cap.isOpened():
                self.logger.error(f"无法打开视频源: {video_source}")
                return False
            cap.release()

            # 合并检测参数
            params = self.detection_params.copy()
            if custom_params:
                params.update(custom_params)

            # 创建视频流信息
            stream_info = {
                'video_source': video_source,
                'params': params,
                'model_path': model_path,  # 保存使用的模型路径
                'target_classes': target_classes if target_classes else [],  # 目标检测类别
                'custom_type': custom_type if custom_type else "",  # 自定义处理类型（每个流独立）
                'start_time': time.time(),
                'frame_count': 0,
                'detection_count': 0,
                'last_detection_time': 0
            }

            # 创建结果队列
            self.result_queues[stream_id] = queue.Queue(maxsize=1000)

            # 初始化报警状态
            self.alarm_states[stream_id] = {}
            self.last_alarm_time[stream_id] = 0

            # 创建并启动检测线程
            detection_thread = threading.Thread(
                target=self._detection_worker,
                args=(stream_id, stream_info),
                daemon=True
            )

            self.active_streams[stream_id] = stream_info
            self.detection_threads[stream_id] = detection_thread

            detection_thread.start()
            self.logger.info(f"视频流检测启动成功: {stream_id}")

            return True

        except Exception as e:
            self.logger.error(f"启动视频流检测失败: {e}")
            self._cleanup_stream(stream_id)
            return False

    def stop_detection(self, stream_id: str) -> bool:
        """
        停止检测指定视频流
        
        Args:
            stream_id: 视频流标识
            
        Returns:
            是否成功停止
        """
        if stream_id not in self.active_streams:
            self.logger.warning(f"视频流不存在: {stream_id}")
            return False

        try:
            # 标记停止
            self.active_streams[stream_id]['stop_flag'] = True

            # 等待线程结束
            thread = self.detection_threads.get(stream_id)
            if thread and thread.is_alive():
                thread.join(timeout=5.0)

            # 清理资源
            self._cleanup_stream(stream_id)

            self.logger.info(f"视频流检测停止成功: {stream_id}")
            return True

        except Exception as e:
            self.logger.error(f"停止视频流检测失败: {e}")
            return False

    def _cleanup_stream(self, stream_id: str) -> None:
        """清理视频流相关资源"""
        self.active_streams.pop(stream_id, None)
        self.detection_threads.pop(stream_id, None)
        self.result_queues.pop(stream_id, None)
        self.alarm_states.pop(stream_id, None)
        self.last_alarm_time.pop(stream_id, None)

    def _detection_worker(self, stream_id: str, stream_info: Dict) -> None:
        """检测工作线程"""
        video_source = stream_info['video_source']
        params = stream_info['params']

        cap = None
        frame_id = 0
        fps_limit = params.get('fps_limit', 30)
        frame_interval = 1.0 / fps_limit if fps_limit > 0 else 0
        last_frame_time = 0
        last_log_time = 0  # 用于记录日志时间间隔

        self.logger.info(f"流 {stream_id} 帧率设置: fps_limit={fps_limit}, frame_interval={frame_interval}")

        try:
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = (
                'rtsp_transport;tcp;'
                'fflags;nobuffer;'
                'flags;low_delay;'
                'reorder_queue_size;0;'
            )
            # 打开视频源
            cap = cv2.VideoCapture(video_source)
            if not cap.isOpened():
                raise Exception(f"无法打开视频源: {video_source}")

            # 设置缓冲区大小为1，避免帧堆积
            buffer_size = 1  # 强制设置为1，避免旧帧堆积
            cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)

            # 获取实际设置的分辨率
            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            self.logger.info(f"流 {stream_id} 视频设置:")
            self.logger.info(f"  - 缓冲区大小: {buffer_size}")
            self.logger.info(f"  - 分辨率: {actual_width}x{actual_height}")
            self.logger.info(f"  - 编码格式: {cap.get(cv2.CAP_PROP_FOURCC)}")

            self.logger.info(f"开始处理视频流: {stream_id}")

            while not stream_info.get('stop_flag', False):
                current_time = time.time()

                # 检查时间策略（Type 2 和 Type 3）
                if not self._check_time_strategy(stream_info):
                    # 当前时间不在允许的检测时段，跳过检测但不停止流
                    continue

                # 读取最新帧
                ret, frame = cap.read()
                if not ret:
                    self.logger.warning(f"读取帧失败: {stream_id}")
                    if self._should_reconnect(stream_id):
                        cap.release()
                        cap = self._reconnect_stream(video_source)
                        if cap is None:
                            break
                    continue

                # 控制帧率 - 在读取帧后进行时间控制
                if frame_interval > 0 and (current_time - last_frame_time) < frame_interval:
                    # 跳过这一帧的处理，但已经清空了缓冲区
                    if frame_id < 5:  # 前5帧记录详细信息
                        elapsed = current_time - last_frame_time
                        # self.logger.info(
                        #     f"流 {stream_id} 帧率控制: 跳过帧 (间隔:{elapsed:.3f}s < {frame_interval:.3f}s)")
                    continue

                # 检查帧是否损坏（全黑或异常小）
                if frame is None or frame.size == 0:
                    self.logger.warning(f"接收到损坏的帧: {stream_id}")
                    continue

                # 检查帧尺寸是否合理
                if frame.shape[0] < 50 or frame.shape[1] < 50:
                    self.logger.warning(f"帧尺寸异常: {stream_id}, 尺寸: {frame.shape}")
                    continue

                # 执行检测
                detection_start = time.time()
                result = self._process_frame(stream_id, frame, frame_id, params)
                processing_time = time.time() - detection_start

                if result:
                    result.processing_time = processing_time

                    # 自定义处理逻辑 - 根据custom_type决定是否继续处理
                    # 在这里会对result进行修改（删除、添加检测目标等）
                    if self._should_continue_processing(result, stream_id):
                        # 保存检测结果（会设置 result.image_url）
                        if self.save_results or self.save_images:
                            self._save_detection_result(result, frame, stream_info)
                        
                        # 确保告警时总是有图片URL（即使保存失败或没有检测结果）
                        if not hasattr(result, 'image_url') or not result.image_url:
                            # 生成图片URL（基于时间戳和流ID）
                            timestamp = datetime.fromtimestamp(result.timestamp)
                            date_str = timestamp.strftime('%Y-%m-%d')
                            time_str = timestamp.strftime('%H-%M-%S-%f')[:-3]
                            image_filename = 'annotated.png' if self.image_format.lower() == 'png' else 'annotated.jpg'
                            expected_relative_path = f"{date_str}/{result.stream_id}/{time_str}_frame_{result.frame_id}/{image_filename}"
                            result.image_url = f"{self.server_public_url}/results/{expected_relative_path}"
                            self.logger.debug(f"告警前生成图片URL: {result.image_url}")

                        # 检查报警条件
                        self._check_alarm_conditions(result)

                        # 调用回调函数
                        for callback in self.detection_callbacks:
                            try:
                                callback(result)
                            except Exception as e:
                                self.logger.error(f"检测回调函数执行失败: {e}")

                    # 更新统计信息
                    self._update_stats(result)

                frame_id += 1
                stream_info['frame_count'] = frame_id
                last_frame_time = current_time

                # 每10帧记录一次处理间隔
                if frame_id % 10 == 0:
                    if last_log_time > 0:
                        actual_interval = current_time - last_log_time
                        self.logger.info(
                            f"流 {stream_id} 已处理 {frame_id} 帧, 检测耗时: {processing_time:.3f}s, 实际帧间隔: {actual_interval / 10:.3f}s")
                    else:
                        self.logger.info(f"流 {stream_id} 已处理 {frame_id} 帧, 检测耗时: {processing_time:.3f}s")
                    last_log_time = current_time

        except Exception as e:
            self.logger.error(f"检测线程异常: {stream_id}, {e}")

        finally:
            if cap:
                cap.release()
            self.logger.info(f"检测线程结束: {stream_id}")

            # 清理流资源（重要！确保流可以重新启动）
            self._cleanup_stream(stream_id)

            # 发送流断开事件
            self._send_stream_event(stream_id, "disconnected", "检测线程结束")

    def _process_frame(self, stream_id: str, frame: np.ndarray,
                       frame_id: int, params: Dict) -> Optional[DetectionResult]:
        """处理单帧图像"""
        try:
            # 确保参数不为None
            if params is None:
                params = {}

            # 优化高分辨率图像处理
            original_shape = frame.shape
            scale_factor = 1.0

            # 检查是否需要自动缩放
            detection_frame = frame
            if self.auto_resize:
                max_dimension = max(original_shape[0], original_shape[1])
                if max_dimension > self.max_resolution:
                    scale_factor = self.max_resolution / max_dimension
                    new_width = int(original_shape[1] * scale_factor)
                    new_height = int(original_shape[0] * scale_factor)

                    # 缩放图像用于检测
                    detection_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
                    self.logger.debug(f"流 {stream_id} 图像自动缩放: {original_shape[1]}x{original_shape[0]} -> {new_width}x{new_height}")
                else:
                    detection_frame = frame
            else:
                detection_frame = frame

            # 获取模型（从active_streams中获取模型路径）
            stream_info = self.active_streams.get(stream_id, {})
            model_path = stream_info.get('model_path', self.model_path)
            model = model_manager.get_model(model_path)
            
            if model is None:
                self.logger.error(f"模型未加载: {model_path}")
                return None
            
            # 运行推理
            results = model(
                detection_frame,
                conf=params.get('confidence_threshold', 0.5),
                iou=params.get('iou_threshold', 0.45),
                imgsz=params.get('image_size', 640),
                verbose=False
            )

            # 解析检测结果
            detections = []
            confidence_scores = []

            if results and len(results) > 0:
                result = results[0]

                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes.xyxy.cpu().numpy()
                    confidences = result.boxes.conf.cpu().numpy()
                    classes = result.boxes.cls.cpu().numpy()

                    for i, (box, conf, cls) in enumerate(zip(boxes, confidences, classes)):
                        # 获取原始类别名称（使用当前模型的类别名称）
                        original_class_name = model.names[int(cls)]

                        # 类别过滤：从stream_info中获取target_classes（每个流可能有不同的目标类别）
                        stream_target_classes = stream_info.get('target_classes', None)
                        if stream_target_classes and len(stream_target_classes) > 0:
                            if original_class_name not in stream_target_classes:
                                continue  # 跳过不在目标类别列表中的检测结果

                        # 检查是否有自定义映射
                        if self.custom_class_names and isinstance(self.custom_class_names, dict):
                            class_name = self.custom_class_names.get(original_class_name, original_class_name)
                        else:
                            class_name = original_class_name

                        # 如果进行了缩放，需要将坐标映射回原始图像
                        if scale_factor != 1.0:
                            scaled_box = box / scale_factor
                        else:
                            scaled_box = box

                        detection = {
                            'id': i,
                            'class_name': class_name,
                            'class_id': int(cls),
                            'confidence': float(conf),
                            'bbox': scaled_box.tolist(),  # [x1, y1, x2, y2] - 原始图像坐标
                            'center': [(scaled_box[0] + scaled_box[2]) / 2, (scaled_box[1] + scaled_box[3]) / 2],
                            'area': (scaled_box[2] - scaled_box[0]) * (scaled_box[3] - scaled_box[1])
                        }

                        detections.append(detection)
                        confidence_scores.append(float(conf))

            # 创建检测结果
            detection_result = DetectionResult(
                stream_id=stream_id,
                timestamp=time.time(),
                frame_id=frame_id,
                detections=detections,
                confidence_scores=confidence_scores,
                bbox_count=len(detections),
                processing_time=0.0  # 将在调用处设置
            )

            return detection_result

        except Exception as e:
            self.logger.error(f"处理帧时发生错误: {e}")
            return None

    def _check_alarm_conditions(self, result: DetectionResult) -> None:
        """检查报警条件"""
        stream_id = result.stream_id
        current_time = result.timestamp

        # 获取报警配置
        min_confidence = self.alarm_config['min_confidence']
        consecutive_frames = self.alarm_config['consecutive_frames']
        cooldown_seconds = self.alarm_config['cooldown_seconds']

        # 检查每个检测目标
        detected_classes = set()

        for detection in result.detections:
            if detection['confidence'] >= min_confidence:
                class_name = detection['class_name']
                detected_classes.add(class_name)

                # 更新连续检测计数
                if class_name not in self.alarm_states[stream_id]:
                    self.alarm_states[stream_id][class_name] = 0

                self.alarm_states[stream_id][class_name] += 1

                # 检查是否达到报警条件
                if (self.alarm_states[stream_id][class_name] >= consecutive_frames and
                        current_time - self.last_alarm_time.get(stream_id, 0) > cooldown_seconds):

                    # 确保告警时有图片URL（如果还没有设置）
                    if not hasattr(result, 'image_url') or not result.image_url:
                        # 生成图片URL（基于时间戳和流ID）
                        timestamp = datetime.fromtimestamp(result.timestamp)
                        date_str = timestamp.strftime('%Y-%m-%d')
                        time_str = timestamp.strftime('%H-%M-%S-%f')[:-3]
                        image_filename = 'annotated.png' if self.image_format.lower() == 'png' else 'annotated.jpg'
                        expected_relative_path = f"{date_str}/{result.stream_id}/{time_str}_frame_{result.frame_id}/{image_filename}"
                        result.image_url = f"{self.server_public_url}/results/{expected_relative_path}"
                        self.logger.warning(f"告警时图片URL为空，已生成URL: {result.image_url}")
                    
                    # 触发报警
                    alarm_event = AlarmEvent(
                        stream_id=stream_id,
                        timestamp=current_time,
                        alarm_type=self._get_alarm_level(detection['confidence']),
                        confidence=detection['confidence'],
                        bbox=detection['bbox'],
                        class_name=class_name,
                        consecutive_count=self.alarm_states[stream_id][class_name],
                        image_url=result.image_url if hasattr(result, 'image_url') and result.image_url else "",  # 从检测结果中获取图片URL
                        record_url=result.record_url if hasattr(result, 'record_url') and result.record_url else ""  # 从检测结果中获取录像URL
                    )
                    
                    # 调试日志
                    self.logger.info(f"创建告警事件: stream_id={stream_id}, image_url={alarm_event.image_url}")

                    # 调用报警回调
                    for callback in self.alarm_callbacks:
                        try:
                            callback(alarm_event)
                        except Exception as e:
                            self.logger.error(f"报警回调函数执行失败: {e}")

                    # 更新最后报警时间
                    self.last_alarm_time[stream_id] = current_time

                    # 重置计数器
                    self.alarm_states[stream_id][class_name] = 0

        # 重置未检测到的类别计数
        for class_name in list(self.alarm_states[stream_id].keys()):
            if class_name not in detected_classes:
                self.alarm_states[stream_id][class_name] = 0

    def _get_alarm_level(self, confidence: float) -> str:
        """根据置信度获取报警级别"""
        levels = self.alarm_config.get('levels', {})

        if confidence >= levels.get('high', 0.7):
            return 'high'
        elif confidence >= levels.get('medium', 0.5):
            return 'medium'
        else:
            return 'low'

    def _check_time_strategy(self, stream_info: Dict) -> bool:
        """
        检查当前时间是否符合检测时间策略（用于Type 2和Type 3）
        
        Args:
            stream_info: 流信息字典，包含时间策略配置
            
        Returns:
            True=当前时间允许检测, False=跳过检测
        """
        date_type = stream_info.get('date_type', '1')
        
        # Type 1: 完整日期时间范围，无需额外检查（已由start_date/end_date控制）
        if date_type == '1':
            return True
        
        # Type 2 和 Type 3: 需要检查每日时间段（和月份）
        daily_time_start = stream_info.get('daily_time_start', '')
        daily_time_end = stream_info.get('daily_time_end', '')
        
        if not daily_time_start or not daily_time_end:
            # 如果没有配置每日时间段，默认允许检测
            return True
        
        try:
            from datetime import datetime
            now = datetime.now()
            current_month = now.month
            current_time = now.time()
            
            # Type 2: 检查月份
            if date_type == '2':
                allowed_months = stream_info.get('allowed_months', [])
                if allowed_months and current_month not in allowed_months:
                    # 当前月份不在允许的月份列表中
                    return False
            
            # 检查每日时间段
            # daily_time_start 格式: "06:00:00"
            start_time = datetime.strptime(daily_time_start, '%H:%M:%S').time()
            end_time = datetime.strptime(daily_time_end, '%H:%M:%S').time()
            
            # 判断当前时间是否在时间段内
            if start_time <= end_time:
                # 正常情况：06:00:00 - 21:00:00
                return start_time <= current_time <= end_time
            else:
                # 跨午夜情况：21:00:00 - 06:00:00
                return current_time >= start_time or current_time <= end_time
                
        except Exception as e:
            self.logger.error(f"时间策略检查失败: {e}")
            # 发生错误时，默认允许检测
            return True
    
    def _should_reconnect(self, stream_id: str) -> bool:
        """判断是否应该重连"""
        return True

    def _reconnect_stream(self, video_source: str) -> Optional[cv2.VideoCapture]:
        """重连视频流"""
        max_attempts = config_manager.get('video_streams.max_reconnect_attempts', 10)
        reconnect_interval = config_manager.get('video_streams.reconnect_interval', 5)

        for attempt in range(max_attempts):
            self.logger.info(f"尝试重连视频流，第 {attempt + 1} 次")

            time.sleep(reconnect_interval)

            cap = cv2.VideoCapture(video_source)
            if cap.isOpened():
                self.logger.info("视频流重连成功")
                return cap
            cap.release()

        self.logger.error("视频流重连失败，达到最大重试次数")
        return None

    def _update_stats(self, result: DetectionResult) -> None:
        """更新性能统计信息"""
        self.stats['total_frames'] += 1
        self.stats['total_detections'] += result.bbox_count

        # 更新平均处理时间
        if result.processing_time > 0:
            current_avg = self.stats['average_processing_time']
            frame_count = self.stats['total_frames']
            self.stats['average_processing_time'] = (
                    (current_avg * (frame_count - 1) + result.processing_time) / frame_count
            )

        # 计算平均FPS
        if result.processing_time > 0:
            self.stats['average_fps'] = 1.0 / result.processing_time

    def _save_detection_result(self, result: DetectionResult, frame: np.ndarray, stream_info: Dict) -> None:
        """保存检测结果到本地"""
        try:
            # 只保存有检测结果的帧
            if result.bbox_count == 0:
                return

            # 创建时间戳和目录结构
            timestamp = datetime.fromtimestamp(result.timestamp)
            date_str = timestamp.strftime('%Y-%m-%d')
            time_str = timestamp.strftime('%H-%M-%S-%f')[:-3]  # 精确到毫秒

            # 为每个检测结果创建独立文件夹
            result_dir = os.path.join(
                self.results_path,
                date_str,
                result.stream_id,
                f"{time_str}_frame_{result.frame_id}"
            )
            os.makedirs(result_dir, exist_ok=True)

            # 1. 保存检测信息文件
            if self.save_results:
                self._save_detection_info(result, result_dir, stream_info, timestamp)

            # 2. 保存带检测框的图片，并生成访问URL
            if self.save_images:
                relative_path = self._save_detection_image(result, frame, result_dir, timestamp)
                if relative_path:
                    # 生成完整的URL（用于Kafka推送和外部访问）
                    # 格式：http://server-ip/results/2025-11-08/camera_001/14-30-45-123_frame_100/annotated.jpg
                    result.image_url = f"{self.server_public_url}/results/{relative_path.replace(os.sep, '/')}"
                    self.logger.debug(f"生成图片URL: {result.image_url}")
                else:
                    # 即使保存失败，也尝试生成URL（基于预期的路径）
                    # 这样告警时至少有一个URL（即使图片可能不存在）
                    date_str = timestamp.strftime('%Y-%m-%d')
                    time_str = timestamp.strftime('%H-%M-%S-%f')[:-3]
                    image_filename = 'annotated.png' if self.image_format.lower() == 'png' else 'annotated.jpg'
                    expected_relative_path = f"{date_str}/{result.stream_id}/{time_str}_frame_{result.frame_id}/{image_filename}"
                    result.image_url = f"{self.server_public_url}/results/{expected_relative_path}"
                    self.logger.warning(f"图片保存失败，但已生成预期URL: {result.image_url}")
            else:
                # 即使不保存图片，也生成URL（基于预期的路径）
                # 这样告警时至少有一个URL（即使图片可能不存在）
                date_str = timestamp.strftime('%Y-%m-%d')
                time_str = timestamp.strftime('%H-%M-%S-%f')[:-3]
                image_filename = 'annotated.png' if self.image_format.lower() == 'png' else 'annotated.jpg'
                expected_relative_path = f"{date_str}/{result.stream_id}/{time_str}_frame_{result.frame_id}/{image_filename}"
                result.image_url = f"{self.server_public_url}/results/{expected_relative_path}"
                self.logger.debug(f"未保存图片，但已生成预期URL: {result.image_url}")

            self.logger.debug(f"检测结果已保存: {result_dir}")

        except Exception as e:
            self.logger.error(f"保存检测结果失败: {e}")

    def _save_detection_info(self, result: DetectionResult, result_dir: str,
                             stream_info: Dict, timestamp: datetime) -> None:
        """保存检测信息到JSON文件"""
        try:
            # 获取流的基本信息
            video_source = stream_info.get('video_source', 'unknown')
            stream_params = stream_info.get('params', {})

            # 构建检测信息
            detection_info = {
                'basic_info': {
                    'timestamp': timestamp.isoformat(),
                    'stream_id': str(result.stream_id),
                    'frame_id': int(result.frame_id),
                    'processing_time': float(result.processing_time),
                    'video_source': str(video_source)
                },
                'stream_info': {
                    'confidence_threshold': float(stream_params.get('confidence_threshold', 0.25)),
                    'iou_threshold': float(stream_params.get('iou_threshold', 0.45)),
                    'fps_limit': int(stream_params.get('fps_limit', 30)),
                    'total_frames_processed': int(stream_info.get('frame_count', 0)),
                    'total_detections': int(stream_info.get('detection_count', 0))
                },
                'detection_results': {
                    'total_objects': int(result.bbox_count),
                    'objects': []
                },
                'alarm_info': {
                    'has_alarm': False,
                    'alarm_level': None,
                    'alarm_objects': []
                }
            }

            # 添加每个检测目标的详细信息
            for i, detection in enumerate(result.detections):
                obj_info = {
                    'id': i + 1,
                    'class_name': str(detection['class_name']),
                    'class_id': int(detection['class_id']),
                    'confidence': float(detection['confidence']),
                    'bbox': {
                        'x1': float(detection['bbox'][0]),
                        'y1': float(detection['bbox'][1]),
                        'x2': float(detection['bbox'][2]),
                        'y2': float(detection['bbox'][3]),
                        'width': float(detection['bbox'][2] - detection['bbox'][0]),
                        'height': float(detection['bbox'][3] - detection['bbox'][1])
                    },
                    'center': {
                        'x': float(detection['center'][0]),
                        'y': float(detection['center'][1])
                    },
                    'area': float(detection['area'])
                }

                detection_info['detection_results']['objects'].append(obj_info)

                # 检查是否触发报警
                alarm_config = config_manager.get_alarm_config()
                min_confidence = alarm_config.get('min_confidence', 0.5)

                if detection['confidence'] >= min_confidence:
                    detection_info['alarm_info']['has_alarm'] = True
                    detection_info['alarm_info']['alarm_objects'].append({
                        'object_id': i + 1,
                        'class_name': str(detection['class_name']),
                        'confidence': float(detection['confidence']),
                        'alarm_level': self._get_alarm_level_by_confidence(detection['confidence'])
                    })

            # 设置整体报警级别
            if detection_info['alarm_info']['has_alarm']:
                alarm_levels = [obj['alarm_level'] for obj in detection_info['alarm_info']['alarm_objects']]
                if 'high' in alarm_levels:
                    detection_info['alarm_info']['alarm_level'] = 'high'
                elif 'medium' in alarm_levels:
                    detection_info['alarm_info']['alarm_level'] = 'medium'
                else:
                    detection_info['alarm_info']['alarm_level'] = 'low'

            # 保存到JSON文件
            info_file = os.path.join(result_dir, 'detection_info.json')
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(detection_info, f, indent=2, ensure_ascii=False, default=self._json_serializer)

        except Exception as e:
            self.logger.error(f"保存检测信息失败: {e}")

    def _save_detection_image(self, result: DetectionResult, frame: np.ndarray,
                              result_dir: str, timestamp: datetime) -> str:
        """
        保存带检测框的图片
        
        Returns:
            str: 图片相对路径（用于生成URL）
        """
        try:
            # 复制原始帧
            annotated_frame = frame.copy()

            # 绘制检测框和标签
            for i, detection in enumerate(result.detections):
                bbox = detection['bbox']
                class_name = detection['class_name']
                confidence = detection['confidence']

                # 转换坐标为整数
                x1, y1, x2, y2 = map(int, bbox)

                # 根据置信度选择颜色
                color = (0, 0, 255)  # 红色 - 低置信度

                # 绘制边界框
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

                # 准备标签文本
                label = f"{class_name}: {confidence:.2f}"

                # 计算文本尺寸
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.6
                thickness = 2
                (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)

                # 绘制标签背景
                cv2.rectangle(annotated_frame,
                              (x1, y1 - text_height - baseline - 10),
                              (x1 + text_width + 10, y1),
                              color, -1)

                # 绘制标签文本
                cv2.putText(annotated_frame, label,
                            (x1 + 5, y1 - baseline - 5),
                            font, font_scale, (255, 255, 255), thickness)

                # 添加对象ID
                id_text = f"#{i + 1}"
                cv2.putText(annotated_frame, id_text,
                            (x1 + 5, y2 - 10),
                            font, 0.5, (255, 255, 255), 1)

            # # 在图片上添加时间戳和流信息
            # info_text = f"Stream: {result.stream_id} | Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
            # cv2.putText(annotated_frame, info_text,
            #             (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # stats_text = f"Frame: {result.frame_id} | Objects: {result.bbox_count} | Processing: {result.processing_time:.3f}s"
            # cv2.putText(annotated_frame, stats_text,
            #             (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # 根据配置选择图像格式和质量
            if self.image_format.lower() == 'png':
                # PNG无损格式
                original_file = os.path.join(result_dir, 'original.png')
                annotated_file = os.path.join(result_dir, 'annotated.png')
                save_params = [cv2.IMWRITE_PNG_COMPRESSION, self.png_compression]
            else:
                # JPEG格式
                original_file = os.path.join(result_dir, 'original.jpg')
                annotated_file = os.path.join(result_dir, 'annotated.jpg')
                save_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]

            # 保存原始图片
            cv2.imwrite(original_file, frame, save_params)

            # 保存带标注的图片
            cv2.imwrite(annotated_file, annotated_frame, save_params)

            # 如果有检测结果，还保存每个目标的裁剪图片
            if result.bbox_count > 0:
                crops_dir = os.path.join(result_dir, 'crops')
                os.makedirs(crops_dir, exist_ok=True)

                for i, detection in enumerate(result.detections):
                    bbox = detection['bbox']
                    class_name = detection['class_name']
                    confidence = detection['confidence']

                    # 裁剪目标区域
                    x1, y1, x2, y2 = map(int, bbox)
                    x1, y1 = max(0, x1), max(0, y1)
                    x2 = min(frame.shape[1], x2)
                    y2 = min(frame.shape[0], y2)

                    if x2 > x1 and y2 > y1:
                        crop = frame[y1:y2, x1:x2]

                        # 使用与主图像相同的格式保存裁剪图片
                        if self.image_format.lower() == 'png':
                            crop_file = os.path.join(crops_dir, f"{i + 1}_{class_name}_{confidence:.2f}.png")
                            crop_params = [cv2.IMWRITE_PNG_COMPRESSION, self.png_compression]
                        else:
                            crop_file = os.path.join(crops_dir, f"{i + 1}_{class_name}_{confidence:.2f}.jpg")
                            crop_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]

                        cv2.imwrite(crop_file, crop, crop_params)
            
            # 返回annotated图片的相对路径
            # 从完整路径中提取相对于results_path的路径
            relative_path = os.path.relpath(annotated_file, self.results_path)
            return relative_path
            
        except Exception as e:
            self.logger.error(f"保存检测图片失败: {e}")
            return ""

    def _get_alarm_level_by_confidence(self, confidence: float) -> str:
        """根据置信度获取报警级别"""
        alarm_config = config_manager.get_alarm_config()
        levels = alarm_config.get('levels', {})

        if confidence >= levels.get('high', 0.7):
            return 'high'
        elif confidence >= levels.get('medium', 0.5):
            return 'medium'
        else:
            return 'low'

    def _json_serializer(self, obj):
        """JSON序列化辅助函数，处理NumPy数据类型"""
        if isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif hasattr(obj, 'item'):  # NumPy标量
            return obj.item()
        else:
            return str(obj)

    def get_stream_info(self, stream_id: str) -> Optional[Dict]:
        """获取视频流信息"""
        return self.active_streams.get(stream_id)

    def get_all_streams(self) -> List[str]:
        """获取所有活跃的视频流ID"""
        return list(self.active_streams.keys())

    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        stats = self.stats.copy()
        stats['active_streams'] = len(self.active_streams)
        return stats

    def shutdown(self) -> None:
        """关闭检测引擎"""
        self.logger.info("正在关闭检测引擎...")

        # 停止所有视频流
        stream_ids = list(self.active_streams.keys())
        for stream_id in stream_ids:
            self.stop_detection(stream_id)

        self.logger.info("检测引擎已关闭")

    def _should_continue_processing(self, result: DetectionResult, stream_id: str) -> bool:
        """
        根据自定义类型决定是否继续处理检测结果
        
        Args:
            result: 检测结果
            stream_id: 流ID
            
        Returns:
            是否继续处理
        """
        # 从流的配置中获取 custom_type（每个流独立配置）
        stream_info = self.active_streams.get(stream_id, {})
        custom_type = stream_info.get('custom_type', '')
        
        # 如果没有设置自定义类型，始终继续处理
        if not custom_type:
            return True

        try:
            # 延迟初始化处理器（第一次使用时初始化）
            if custom_type not in self._initialized_handlers:
                self._initialize_handler_for_type(custom_type)
                self._initialized_handlers.add(custom_type)
            
            # 根据自定义类型分发到具体处理方法
            if custom_type == "high_temperature_alert":
                return self._check_high_temperature_condition(result, stream_id)
            elif custom_type == "morning_meeting_alert":
                # 晨会预警：检查并修改result，然后决定是否继续处理
                return self._check_morning_meeting_condition(result, stream_id)
            elif custom_type == "weather_safety_alert":
                # 防台防汛预警：检查天气条件决定是否继续处理
                return self._check_weather_safety_condition(result, stream_id)
            elif custom_type == "helmet_detection_alert":
                # 安全帽检测预警：检查人数和安全帽数量，如果人数>安全帽数则触发告警
                return self._check_helmet_detection_condition(result, stream_id)

            # 这里可以添加更多自定义类型
            # elif custom_type == "low_light_alert":
            #     return self._check_low_light_condition(result, stream_id)
            # elif custom_type == "motion_detection":
            #     return self._check_motion_condition(result, stream_id)

            else:
                self.logger.warning(f"未知的自定义类型: {custom_type} (流: {stream_id})")
                return True  # 默认继续处理

        except Exception as e:
            self.logger.error(f"自定义处理逻辑执行失败: {e}")
            return True  # 出错时默认继续处理

    def _check_high_temperature_condition(self, result: DetectionResult, stream_id: str) -> bool:
        """
        检查高温条件
        
        Args:
            result: 检测结果
            stream_id: 流ID
            
        Returns:
            是否满足高温条件（温度高于阈值时返回True）
        """
        if not self.temperature_check_enabled:
            return True

        try:
            # 获取当前温度
            current_temp = self._get_current_temperature()

            # 检查是否超过阈值
            is_high_temp = current_temp >= self.temperature_threshold

            if is_high_temp:
                self.logger.info(
                    f"🌡️ 高温条件满足: 当前温度 {current_temp}°C >= 阈值 {self.temperature_threshold}°C，继续处理检测结果")
            else:
                self.logger.debug(
                    f"🌡️ 温度正常: 当前温度 {current_temp}°C < 阈值 {self.temperature_threshold}°C，跳过处理")

            return is_high_temp

        except Exception as e:
            self.logger.error(f"温度检查失败: {e}")
            return True  # 出错时默认继续处理

    def _get_current_temperature(self) -> float:
        """
        获取当前温度
        
        Returns:
            当前温度值
        """
        try:
            if hasattr(self, 'weather_api'):
                # 从天气API获取温度
                temp_str = self.weather_api.get_temperature()
                return float(temp_str)
            elif hasattr(self, 'fixed_temperature'):
                # 使用固定温度值
                return self.fixed_temperature
            else:
                # 默认温度
                return 25.0

        except Exception as e:
            self.logger.error(f"获取温度失败: {e}")
            return 25.0  # 默认温度

    def _check_morning_meeting_condition(self, result: DetectionResult, stream_id: str) -> bool:
        """
        检查安全晨会条件，并直接修改检测结果
        
        规则：在规定时间段内，如果连续累计检测到人员达5分钟，则认为晨会已召开；
        否则在时间段结束时触发告警。
        
        Returns:
            是否应该继续处理（保存结果、触发回调等）
        """
        if not self.meeting_check_enabled:
            return False  # 晨会预警模式下，如果未启用则不处理任何结果
        
        try:
            now = datetime.now()
            current_date = now.date()
            current_weekday = now.weekday()
            
            # 检查是否为工作日
            if current_weekday not in self.meeting_weekdays:
                return False  # 非工作日不处理
            
            # 解析时间段
            start_hour, start_minute = map(int, self.meeting_start_time.split(':'))
            end_hour, end_minute = map(int, self.meeting_end_time.split(':'))
            start_time = dt_time(start_hour, start_minute)
            end_time = dt_time(end_hour, end_minute)
            now_time = now.time()
            
            def _within_window(t: dt_time) -> bool:
                # 早晨时间段通常不跨日，这里假设 start_time <= end_time
                return start_time <= t <= end_time
            
            def _after_window(t: dt_time) -> bool:
                return t > end_time
            
            # 初始化/重置状态
            state = self.meeting_alert_states.setdefault(stream_id, {
                'alert_sent_today': 0,
                'meeting_done': False,
                'last_check_date': current_date,
                'presence_accumulated': 0.0,  # 累计有人时长（秒）
                'last_person_ts': None
            })
            
            # 跨天重置
            if state['last_check_date'] != current_date:
                state.update({
                    'alert_sent_today': 0,
                    'meeting_done': False,
                    'last_check_date': current_date,
                    'presence_accumulated': 0.0,
                    'last_person_ts': None
                })
            
            # 如果今天已完成或已告警，跳过特殊处理，让正常流程继续
            if state['meeting_done'] or state['alert_sent_today'] > 4:
                return False
            
            in_window = _within_window(now_time)
            after_window = _after_window(now_time)
            
            has_person = self._has_person_detected(result)
            
            # 1) 窗口内逻辑：累计有人时长
            if in_window:
                if has_person:
                    if state['last_person_ts'] is None:
                        state['last_person_ts'] = now
                    else:
                        delta = (now - state['last_person_ts']).total_seconds()
                        if delta > 0:
                            state['presence_accumulated'] += delta
                        state['last_person_ts'] = now
                    
                    # 达到配置的判定时长（分钟）视为晨会已召开
                    required_seconds = max(1, int(self.meeting_required_minutes * 60))
                    if state['presence_accumulated'] >= required_seconds:
                        state['meeting_done'] = True
                        self.logger.info(
                            f"流 {stream_id} 晨会检测：已累计有人≥{self.meeting_required_minutes}分钟，视为晨会已召开")
                        return False  # 继续正常处理，不触发晨会未召开告警
                    
                    # 窗口内有人但未满5分钟，不触发告警，正常继续
                    return False
                else:
                    # 窗口内无人，重置last_person_ts，但不清零累计时长
                    state['last_person_ts'] = None
                    return False  # 继续正常处理，不立即告警
            
            # 2) 窗口结束后：如果未达到5分钟且未告警，则触发告警
            if after_window and (not state['meeting_done']) and (state['alert_sent_today'] > 4):
                # 清空原有检测结果，添加虚拟告警目标
                result.detections.clear()
                result.confidence_scores.clear()
                
                meeting_alert_detection = {
                    'id': 0,
                    'class_name': '晨会未召开',
                    'class_id': 9999,  # 特殊class_id
                    'confidence': 1.0,
                    'bbox': [0, 0, 100, 50],  # 虚拟框，左上角
                    'center': [50, 25],
                    'area': 5000
                }
                
                result.detections.append(meeting_alert_detection)
                result.confidence_scores.append(1.0)
                result.bbox_count = 1
                
                state['alert_sent_today'] += 1
                self.logger.warning(f"流 {stream_id} 晨会检测：时间结束且累计有人<{self.meeting_required_minutes}分钟，触发未召开告警")
                return True  # 继续处理，保存并告警
            
            # 窗口外（未到开始或已结束但已处理完），不做特殊处理
            return False
        
        except Exception as e:
            self.logger.error(f"晨会预警检查失败: {e}")
            return False  # 出错时不处理
    
    def _is_meeting_time(self, current_time: datetime) -> bool:
        """检查当前时间是否在晨会时间段内"""
        try:
            current_time_only = current_time.time()
            
            # 解析开始和结束时间
            start_hour, start_minute = map(int, self.meeting_start_time.split(':'))
            end_hour, end_minute = map(int, self.meeting_end_time.split(':'))
            
            start_time = dt_time(start_hour, start_minute)
            end_time = dt_time(end_hour, end_minute)
            
            return start_time <= current_time_only <= end_time
            
        except Exception as e:
            self.logger.error(f"时间检查失败: {e}")
            return False
    
    def _has_person_detected(self, result: DetectionResult) -> bool:
        """检查检测结果中是否包含人员"""
        for detection in result.detections:
            class_name = detection.get('class_name', '').lower()
            # 检查是否为人员类别
            for person_class in self.person_class_names:
                if person_class.lower() in class_name or class_name in person_class.lower():
                    return True
        return False
    
    def _check_weather_safety_condition(self, result: DetectionResult, stream_id: str) -> bool:
        """
        检查防台防汛施工安全条件
        
        Args:
            result: 检测结果
            stream_id: 流ID
            
        Returns:
            是否满足危险天气条件（天气危险时返回True）
        """
        if not self.weather_safety_enabled:
            return True
        
        try:
            # 获取当前天气信息
            wind_power, weather_type = self._get_current_weather_info()
            
            # 检查风力是否超过阈值
            is_high_wind = wind_power >= self.wind_power_threshold
            
            # 检查天气类型是否包含危险关键词
            is_dangerous_weather = any(keyword in weather_type for keyword in self.dangerous_weather_keywords)
            
            # 判断是否为危险天气
            is_dangerous = is_high_wind or is_dangerous_weather
            
            if is_dangerous:
                self.logger.info(
                    f"🌪️ 危险天气条件满足: 风力{wind_power}级 >= 阈值{self.wind_power_threshold}级 或天气包含危险关键词({weather_type})，继续处理检测结果")
            else:
                self.logger.debug(
                    f"☀️ 天气安全: 风力{wind_power}级 < 阈值{self.wind_power_threshold}级 且天气安全({weather_type})，跳过处理")
            
            return is_dangerous
            
        except Exception as e:
            self.logger.error(f"天气安全检查失败: {e}")
            return True  # 出错时默认继续处理
    
    def _get_current_weather_info(self) -> Tuple[int, str]:
        """
        获取当前天气信息
        
        Returns:
            (风力等级, 天气类型)
        """
        try:
            if hasattr(self, 'weather_safety_api'):
                # 从天气API获取信息
                wind_power_str = self.weather_safety_api.get_wind_power()
                weather_type = self.weather_safety_api.get_weather_type()
                
                # 解析风力等级（提取数字）
                import re
                wind_match = re.search(r'(\d+)', wind_power_str)
                wind_power = int(wind_match.group(1)) if wind_match else 0
                
                return wind_power, weather_type
            elif hasattr(self, 'fixed_wind_power') and hasattr(self, 'fixed_weather_type'):
                # 使用固定值
                return self.fixed_wind_power, self.fixed_weather_type
            else:
                # 默认安全天气
                return 3, '晴'
                
        except Exception as e:
            self.logger.error(f"获取天气信息失败: {e}")
            return 3, '晴'  # 默认安全天气
    
    def _check_helmet_detection_condition(self, result: DetectionResult, stream_id: str) -> bool:
        """
        检查安全帽检测条件
        当检测到人数 > 安全帽数时，说明有人没戴安全帽，触发告警
        
        Args:
            result: 检测结果（会被修改）
            stream_id: 流ID
            
        Returns:
            是否应该继续处理（保存结果、触发回调等）
        """
        if not self.helmet_detection_enabled:
            return True  # 未启用时，正常处理所有检测结果
        
        try:
            # 统计人员数量
            person_count = 0
            helmet_count = 0
            
            for detection in result.detections:
                class_name = detection.get('class_name', '').lower()
                
                # 检查是否为人员类别
                for person_class in self.helmet_person_class_names:
                    if person_class.lower() in class_name or class_name in person_class.lower():
                        person_count += 1
                        break
                
                # 检查是否为安全帽类别
                for helmet_class in self.helmet_class_names:
                    if helmet_class.lower() in class_name or class_name in helmet_class.lower():
                        helmet_count += 1
                        break
            
            # 判断是否有人没戴安全帽
            if person_count > helmet_count:
                # 有人没戴安全帽，触发告警
                # 修改检测结果，添加告警信息
                missing_helmet_count = person_count - helmet_count
                
                # 添加虚拟的告警目标到检测结果中
                alert_detection = {
                    'id': len(result.detections),
                    'class_name': f'未戴安全帽({missing_helmet_count}人)',
                    'class_id': 9998,  # 使用特殊的class_id
                    'confidence': 1.0,
                    'bbox': [0, 0, 200, 50],  # 虚拟的边界框，显示在左上角
                    'center': [100, 25],
                    'area': 10000
                }
                
                result.detections.append(alert_detection)
                result.confidence_scores.append(1.0)
                result.bbox_count = len(result.detections)
                
                self.logger.warning(
                    f"⚠️ 安全帽检测告警: 流 {stream_id} 检测到 {person_count} 人, "
                    f"但只有 {helmet_count} 个安全帽, {missing_helmet_count} 人未戴安全帽"
                )
                return True  # 继续处理，保存告警结果
            else:
                # 所有人员都戴了安全帽，正常情况
                self.logger.debug(
                    f"✅ 安全帽检测正常: 流 {stream_id} 检测到 {person_count} 人, "
                    f"{helmet_count} 个安全帽, 符合安全要求"
                )
                return True  # 正常情况也继续处理，可以记录日志
            
        except Exception as e:
            self.logger.error(f"安全帽检测检查失败: {e}")
            return True  # 出错时默认继续处理
    
