"""
视频流管理器
负责管理RTSP流的注册、删除和状态监控
"""

import logging
import time
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
from enum import Enum
from .detection_engine import DetectionEngine, DetectionResult, AlarmEvent, StreamEvent
from .config_manager import config_manager


class StreamStatus(Enum):
    """视频流状态枚举"""
    INACTIVE = "inactive"      # 未激活
    CONNECTING = "connecting"  # 连接中
    ACTIVE = "active"         # 活跃
    ERROR = "error"           # 错误
    RECONNECTING = "reconnecting"  # 重连中


@dataclass
class StreamConfig:
    """视频流配置"""
    stream_id: str
    rtsp_url: str
    name: str = ""
    description: str = ""
    confidence_threshold: float = 0.25
    iou_threshold: float = 0.45
    fps_limit: int = 30
    callback_url: str = ""
    alarm_enabled: bool = True
    save_results: bool = False
    tags: List[str] = None
    model_path: str = ""  # 使用的模型路径（可选）
    target_classes: List[str] = None  # 目标检测类别（可选）
    custom_type: str = ""  # 自定义处理类型（可选，如 "helmet_detection_alert"）
    scene_id: str = ""  # 场景ID（外部平台的场景ID）
    # 时间策略配置（用于Type 2和Type 3）
    date_type: str = ""  # 日期类型: "1", "2", "3"
    allowed_months: List[int] = None  # 允许的月份列表（Type 2）
    daily_time_start: str = ""  # 每日开始时间 HH:mm:ss（Type 2和3）
    daily_time_end: str = ""  # 每日结束时间 HH:mm:ss（Type 2和3）
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.target_classes is None:
            self.target_classes = []
        if self.allowed_months is None:
            self.allowed_months = []


@dataclass
class StreamInfo:
    """视频流信息"""
    config: StreamConfig
    status: StreamStatus
    created_time: float
    last_active_time: float
    frame_count: int = 0
    detection_count: int = 0
    error_count: int = 0
    last_error: str = ""
    performance_stats: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.performance_stats is None:
            self.performance_stats = {
                'average_fps': 0.0,
                'average_processing_time': 0.0,
                'total_detections': 0
            }


class StreamManager:
    """视频流管理器"""
    
    def __init__(self, detection_engine: DetectionEngine):
        """
        初始化流管理器
        
        Args:
            detection_engine: 检测引擎实例
        """
        self.logger = logging.getLogger(__name__)
        self.detection_engine = detection_engine
        
        # 流管理
        self.streams: Dict[str, StreamInfo] = {}
        self.stream_lock = threading.RLock()
        
        # 配置参数
        self.max_streams = config_manager.get('detection.max_streams', 10)
        
        # 监控线程
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_running = False
        
        # 回调函数注册
        self.detection_callbacks: Dict[str, Callable] = {}
        self.alarm_callbacks: Dict[str, Callable] = {}
        
        # 注册检测引擎回调
        self.detection_engine.add_detection_callback(self._on_detection_result)
        self.detection_engine.add_alarm_callback(self._on_alarm_event)
        self.detection_engine.add_stream_callback(self._on_stream_event)
        
        # 场景管理器（延迟初始化，避免循环依赖）
        self.scene_manager = None
        
        # 启动监控
        self.start_monitor()
        
        self.logger.info("视频流管理器初始化完成")
    
    def register_stream(self, config: StreamConfig) -> Dict[str, Any]:
        """
        注册新的视频流
        
        Args:
            config: 视频流配置
            
        Returns:
            注册结果
        """
        with self.stream_lock:
            # 检查流ID是否已存在
            if config.stream_id in self.streams:
                return {
                    'success': False,
                    'error': f'流ID已存在: {config.stream_id}',
                    'stream_id': config.stream_id
                }
            
            # 检查流数量限制
            if len(self.streams) >= self.max_streams:
                return {
                    'success': False,
                    'error': f'已达到最大流数量限制: {self.max_streams}',
                    'stream_id': config.stream_id
                }
            
            try:
                # 创建流信息
                current_time = time.time()
                stream_info = StreamInfo(
                    config=config,
                    status=StreamStatus.INACTIVE,
                    created_time=current_time,
                    last_active_time=current_time
                )
                
                # 添加到管理器
                self.streams[config.stream_id] = stream_info
                
                self.logger.info(f"视频流注册成功: {config.stream_id}")
                
                return {
                    'success': True,
                    'message': '视频流注册成功',
                    'stream_id': config.stream_id,
                    'stream_info': self._get_stream_summary(stream_info)
                }
                
            except Exception as e:
                self.logger.error(f"注册视频流失败: {e}")
                return {
                    'success': False,
                    'error': f'注册失败: {str(e)}',
                    'stream_id': config.stream_id
                }
    
    def unregister_stream(self, stream_id: str) -> Dict[str, Any]:
        """
        注销视频流
        
        Args:
            stream_id: 视频流ID
            
        Returns:
            注销结果
        """
        with self.stream_lock:
            if stream_id not in self.streams:
                return {
                    'success': False,
                    'error': f'流ID不存在: {stream_id}',
                    'stream_id': stream_id
                }
            
            try:
                # 停止检测
                self.stop_stream(stream_id)
                
                # 移除流信息
                stream_info = self.streams.pop(stream_id)
                
                # 清理回调
                self.detection_callbacks.pop(stream_id, None)
                self.alarm_callbacks.pop(stream_id, None)
                
                self.logger.info(f"视频流注销成功: {stream_id}")
                
                return {
                    'success': True,
                    'message': '视频流注销成功',
                    'stream_id': stream_id,
                    'final_stats': stream_info.performance_stats
                }
                
            except Exception as e:
                self.logger.error(f"注销视频流失败: {e}")
                return {
                    'success': False,
                    'error': f'注销失败: {str(e)}',
                    'stream_id': stream_id
                }
    
    def start_stream(self, stream_id: str) -> Dict[str, Any]:
        """
        启动视频流检测
        
        Args:
            stream_id: 视频流ID
            
        Returns:
            启动结果
        """
        with self.stream_lock:
            if stream_id not in self.streams:
                return {
                    'success': False,
                    'error': f'流ID不存在: {stream_id}',
                    'stream_id': stream_id
                }
            
            stream_info = self.streams[stream_id]
            
            if stream_info.status == StreamStatus.ACTIVE:
                return {
                    'success': False,
                    'error': f'视频流已在运行: {stream_id}',
                    'stream_id': stream_id
                }
            
            try:
                # 更新状态
                stream_info.status = StreamStatus.CONNECTING
                stream_info.last_active_time = time.time()
                
                # 准备检测参数
                config = stream_info.config
                detection_params = {
                    'confidence_threshold': config.confidence_threshold,
                    'iou_threshold': config.iou_threshold,
                    'fps_limit': config.fps_limit
                }
                
                # 启动检测
                success = self.detection_engine.start_detection(
                    stream_id=stream_id,
                    video_source=config.rtsp_url,
                    custom_params=detection_params,
                    model_path=config.model_path if config.model_path else None,
                    target_classes=config.target_classes if config.target_classes else None,
                    custom_type=config.custom_type if config.custom_type else None  # 传递custom_type
                )
                
                if success:
                    stream_info.status = StreamStatus.ACTIVE
                    stream_info.error_count = 0
                    stream_info.last_error = ""
                    
                    self.logger.info(f"视频流启动成功: {stream_id}")
                    
                    return {
                        'success': True,
                        'message': '视频流启动成功',
                        'stream_id': stream_id,
                        'stream_info': self._get_stream_summary(stream_info)
                    }
                else:
                    stream_info.status = StreamStatus.ERROR
                    stream_info.error_count += 1
                    stream_info.last_error = "启动检测失败"
                    
                    return {
                        'success': False,
                        'error': '启动检测失败',
                        'stream_id': stream_id
                    }
                    
            except Exception as e:
                stream_info.status = StreamStatus.ERROR
                stream_info.error_count += 1
                stream_info.last_error = str(e)
                
                self.logger.error(f"启动视频流失败: {e}")
                return {
                    'success': False,
                    'error': f'启动失败: {str(e)}',
                    'stream_id': stream_id
                }
    
    def stop_stream(self, stream_id: str) -> Dict[str, Any]:
        """
        停止视频流检测
        
        Args:
            stream_id: 视频流ID
            
        Returns:
            停止结果
        """
        with self.stream_lock:
            if stream_id not in self.streams:
                return {
                    'success': False,
                    'error': f'流ID不存在: {stream_id}',
                    'stream_id': stream_id
                }
            
            stream_info = self.streams[stream_id]
            
            try:
                # 停止检测
                success = self.detection_engine.stop_detection(stream_id)
                
                # 更新状态
                stream_info.status = StreamStatus.INACTIVE
                
                if success:
                    self.logger.info(f"视频流停止成功: {stream_id}")
                    return {
                        'success': True,
                        'message': '视频流停止成功',
                        'stream_id': stream_id,
                        'final_stats': stream_info.performance_stats
                    }
                else:
                    return {
                        'success': False,
                        'error': '停止检测失败',
                        'stream_id': stream_id
                    }
                    
            except Exception as e:
                self.logger.error(f"停止视频流失败: {e}")
                return {
                    'success': False,
                    'error': f'停止失败: {str(e)}',
                    'stream_id': stream_id
                }
    
    def get_stream_info(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """
        获取视频流信息
        
        Args:
            stream_id: 视频流ID
            
        Returns:
            流信息字典
        """
        with self.stream_lock:
            if stream_id not in self.streams:
                return None
            
            stream_info = self.streams[stream_id]
            return self._get_stream_detail(stream_info)
    
    def get_all_streams(self) -> List[Dict[str, Any]]:
        """
        获取所有视频流信息
        
        Returns:
            所有流信息列表
        """
        with self.stream_lock:
            return [
                self._get_stream_summary(stream_info)
                for stream_info in self.streams.values()
            ]
    
    def get_stream_stats(self) -> Dict[str, Any]:
        """
        获取流管理器统计信息
        
        Returns:
            统计信息字典
        """
        with self.stream_lock:
            status_count = {}
            for status in StreamStatus:
                status_count[status.value] = 0
            
            total_frames = 0
            total_detections = 0
            
            for stream_info in self.streams.values():
                status_count[stream_info.status.value] += 1
                total_frames += stream_info.frame_count
                total_detections += stream_info.detection_count
            
            return {
                'total_streams': len(self.streams),
                'max_streams': self.max_streams,
                'status_distribution': status_count,
                'total_frames_processed': total_frames,
                'total_detections': total_detections,
                'engine_stats': self.detection_engine.get_stats()
            }
    
    def update_stream_config(self, stream_id: str, 
                           config_updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新视频流配置
        
        Args:
            stream_id: 视频流ID
            config_updates: 配置更新字典
            
        Returns:
            更新结果
        """
        with self.stream_lock:
            if stream_id not in self.streams:
                return {
                    'success': False,
                    'error': f'流ID不存在: {stream_id}',
                    'stream_id': stream_id
                }
            
            try:
                stream_info = self.streams[stream_id]
                config = stream_info.config
                
                # 更新配置
                for key, value in config_updates.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                
                # 如果流正在运行，需要重启以应用新配置
                was_active = stream_info.status == StreamStatus.ACTIVE
                if was_active:
                    self.stop_stream(stream_id)
                    time.sleep(1)  # 等待停止完成
                    self.start_stream(stream_id)
                
                self.logger.info(f"视频流配置更新成功: {stream_id}")
                
                return {
                    'success': True,
                    'message': '配置更新成功',
                    'stream_id': stream_id,
                    'restarted': was_active,
                    'updated_config': asdict(config)
                }
                
            except Exception as e:
                self.logger.error(f"更新视频流配置失败: {e}")
                return {
                    'success': False,
                    'error': f'更新失败: {str(e)}',
                    'stream_id': stream_id
                }
    
    def register_callback(self, stream_id: str, callback_type: str, 
                         callback_func: Callable) -> bool:
        """
        注册回调函数
        
        Args:
            stream_id: 视频流ID
            callback_type: 回调类型 ('detection' 或 'alarm')
            callback_func: 回调函数
            
        Returns:
            是否注册成功
        """
        if stream_id not in self.streams:
            self.logger.error(f"注册回调失败，流ID不存在: {stream_id}")
            return False
        
        try:
            if callback_type == 'detection':
                self.detection_callbacks[stream_id] = callback_func
            elif callback_type == 'alarm':
                self.alarm_callbacks[stream_id] = callback_func
            else:
                self.logger.error(f"不支持的回调类型: {callback_type}")
                return False
            
            self.logger.info(f"回调函数注册成功: {stream_id} - {callback_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"注册回调函数失败: {e}")
            return False
    
    def _on_detection_result(self, result: DetectionResult) -> None:
        """处理检测结果回调"""
        stream_id = result.stream_id
        
        # 更新流信息
        if stream_id in self.streams:
            stream_info = self.streams[stream_id]
            stream_info.frame_count = result.frame_id
            stream_info.detection_count += result.bbox_count
            stream_info.last_active_time = result.timestamp
            
            # 如果流之前有错误，现在恢复正常，更新状态
            if stream_info.status in [StreamStatus.ERROR, StreamStatus.RECONNECTING]:
                stream_info.status = StreamStatus.ACTIVE
                stream_info.last_error = ""
                self.logger.info(f"流 {stream_id} 状态恢复为活跃")
            
            # 更新性能统计
            if result.processing_time > 0:
                stats = stream_info.performance_stats
                stats['total_detections'] += result.bbox_count
                stats['average_processing_time'] = result.processing_time
                stats['average_fps'] = 1.0 / result.processing_time if result.processing_time > 0 else 0
        
        # 调用用户注册的回调
        if stream_id in self.detection_callbacks:
            try:
                self.detection_callbacks[stream_id](result)
            except Exception as e:
                self.logger.error(f"用户检测回调执行失败: {e}")
    
    def _on_alarm_event(self, alarm: AlarmEvent) -> None:
        """处理报警事件回调"""
        stream_id = alarm.stream_id
        
        # 调用用户注册的回调
        if stream_id in self.alarm_callbacks:
            try:
                self.alarm_callbacks[stream_id](alarm)
            except Exception as e:
                self.logger.error(f"用户报警回调执行失败: {e}")
        
        # 记录报警日志
        self.logger.warning(
            f"报警事件: 流ID={stream_id}, 类型={alarm.alarm_type}, "
            f"目标={alarm.class_name}, 置信度={alarm.confidence:.2f}"
        )
    
    def _on_stream_event(self, event: StreamEvent) -> None:
        """处理流状态事件回调"""
        stream_id = event.stream_id
        
        if stream_id in self.streams:
            stream_info = self.streams[stream_id]
            
            if event.event_type == "disconnected":
                # 流断开，更新状态
                stream_info.status = StreamStatus.ERROR
                stream_info.error_count += 1
                stream_info.last_error = event.message
                self.logger.info(f"流 {stream_id} 已断开: {event.message}")
                
            elif event.event_type == "reconnecting":
                # 流重连中
                stream_info.status = StreamStatus.RECONNECTING
                self.logger.info(f"流 {stream_id} 重连中: {event.message}")
                
            elif event.event_type == "connected":
                # 流连接成功
                stream_info.status = StreamStatus.ACTIVE
                stream_info.last_error = ""
                self.logger.info(f"流 {stream_id} 已连接: {event.message}")
                
            elif event.event_type == "error":
                # 流错误
                stream_info.status = StreamStatus.ERROR
                stream_info.error_count += 1
                stream_info.last_error = event.message
                self.logger.error(f"流 {stream_id} 错误: {event.message}")
    
    def start_monitor(self) -> None:
        """启动监控线程"""
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.monitor_running = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_streams,
                daemon=True
            )
            self.monitor_thread.start()
            self.logger.info("流监控线程启动")
    
    def stop_monitor(self) -> None:
        """停止监控线程"""
        self.monitor_running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5.0)
        self.logger.info("流监控线程停止")
    
    def _monitor_streams(self) -> None:
        """监控视频流状态"""
        while self.monitor_running:
            try:
                current_time = time.time()
                
                with self.stream_lock:
                    for stream_id, stream_info in self.streams.items():
                        # 检查超时
                        if (stream_info.status == StreamStatus.ACTIVE and
                            current_time - stream_info.last_active_time > 60):  # 60秒超时
                            
                            self.logger.warning(f"检测到流超时: {stream_id}")
                            stream_info.status = StreamStatus.ERROR
                            stream_info.error_count += 1
                            stream_info.last_error = "流超时"
                            
                        # 检查是否有长时间处于重连状态的流
                        elif (stream_info.status == StreamStatus.RECONNECTING and
                              current_time - stream_info.last_active_time > 120):  # 120秒重连超时
                            
                            self.logger.error(f"流重连超时: {stream_id}")
                            stream_info.status = StreamStatus.ERROR
                            stream_info.error_count += 1
                            stream_info.last_error = "重连超时"
                
                time.sleep(10)  # 每10秒检查一次
                
            except Exception as e:
                self.logger.error(f"监控线程异常: {e}")
                time.sleep(5)
    
    def _get_stream_summary(self, stream_info: StreamInfo) -> Dict[str, Any]:
        """获取流的摘要信息"""
        return {
            'stream_id': stream_info.config.stream_id,
            'name': stream_info.config.name,
            'status': stream_info.status.value,
            'rtsp_url': stream_info.config.rtsp_url,
            'created_time': stream_info.created_time,
            'last_active_time': stream_info.last_active_time,
            'frame_count': stream_info.frame_count,
            'detection_count': stream_info.detection_count,
            'error_count': stream_info.error_count
        }
    
    def _get_stream_detail(self, stream_info: StreamInfo) -> Dict[str, Any]:
        """获取流的详细信息"""
        return {
            'config': asdict(stream_info.config),
            'status': stream_info.status.value,
            'created_time': stream_info.created_time,
            'last_active_time': stream_info.last_active_time,
            'frame_count': stream_info.frame_count,
            'detection_count': stream_info.detection_count,
            'error_count': stream_info.error_count,
            'last_error': stream_info.last_error,
            'performance_stats': stream_info.performance_stats
        }
    
    def shutdown(self) -> None:
        """关闭流管理器"""
        self.logger.info("正在关闭流管理器...")
        
        # 停止监控
        self.stop_monitor()
        
        # 停止所有流
        with self.stream_lock:
            stream_ids = list(self.streams.keys())
            for stream_id in stream_ids:
                self.stop_stream(stream_id)
        
        self.logger.info("流管理器已关闭")
