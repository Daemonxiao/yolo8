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
from datetime import datetime
from typing import Dict, List, Callable, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from ultralytics import YOLO
import numpy as np
from .config_manager import config_manager


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
        
        # 类别名称映射（可选的中文化）
        self.custom_class_names = config_manager.get('detection.custom_class_names', {}) or {}
        
        # 自动缩放配置
        self.auto_resize = config_manager.get('detection.auto_resize', True)
        self.max_resolution = config_manager.get('detection.max_resolution', 640)
        
        # 确保保存目录存在
        if self.save_results or self.save_images:
            os.makedirs(self.results_path, exist_ok=True)
            os.makedirs(self.images_path, exist_ok=True)
        
        self.logger.info("检测引擎初始化完成")
    
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
                       custom_params: Optional[Dict] = None) -> bool:
        """
        开始检测指定视频流
        
        Args:
            stream_id: 视频流唯一标识
            video_source: 视频源（RTSP URL、文件路径等）
            custom_params: 自定义检测参数
            
        Returns:
            是否成功启动
        """
        if stream_id in self.active_streams:
            self.logger.warning(f"视频流已存在: {stream_id}")
            return False
        
        try:
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
                'start_time': time.time(),
                'frame_count': 0,
                'detection_count': 0,
                'last_detection_time': 0
            }
            
            # 创建结果队列
            self.result_queues[stream_id] = queue.Queue(maxsize=100)
            
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
            # 打开视频源
            cap = cv2.VideoCapture(video_source)
            if not cap.isOpened():
                raise Exception(f"无法打开视频源: {video_source}")
            
            # 设置缓冲区大小为1，避免帧堆积
            buffer_size = 1  # 强制设置为1，避免旧帧堆积
            cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
            
            # 设置视频捕获质量参数
            # 首先尝试获取摄像头支持的分辨率
            original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # 尝试设置配置的分辨率，如果失败则使用原始分辨率
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_height)
            
            # 检查是否设置成功
            set_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            set_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            if set_width != self.capture_width or set_height != self.capture_height:
                self.logger.warning(f"流 {stream_id} 无法设置期望分辨率 {self.capture_width}x{self.capture_height}")
                self.logger.info(f"流 {stream_id} 使用摄像头原始分辨率 {set_width}x{set_height}")
            
            # 设置帧率（减少H264编码负担）
            cap.set(cv2.CAP_PROP_FPS, 15)  # 限制为15fps，减少编码压力
            
            # 尝试设置更兼容的编码格式
            # 优先使用YUYV（未压缩），其次MJPG，避免H264问题
            formats_to_try = [
                cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'),  # YUYV 未压缩
                cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'),  # MJPEG
                -1  # 使用默认格式
            ]
            
            for fmt in formats_to_try:
                if fmt == -1:
                    self.logger.info(f"流 {stream_id} 使用默认编码格式")
                    break
                else:
                    success = cap.set(cv2.CAP_PROP_FOURCC, fmt)
                    if success:
                        fmt_name = "YUYV" if fmt == cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V') else "MJPEG"
                        self.logger.info(f"流 {stream_id} 编码格式设置为: {fmt_name}")
                        break
            
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
                        self.logger.info(f"流 {stream_id} 帧率控制: 跳过帧 (间隔:{elapsed:.3f}s < {frame_interval:.3f}s)")
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
                    
                    # 保存检测结果
                    if self.save_results or self.save_images:
                        self._save_detection_result(result, frame, stream_info)
                    
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
                        self.logger.info(f"流 {stream_id} 已处理 {frame_id} 帧, 检测耗时: {processing_time:.3f}s, 实际帧间隔: {actual_interval/10:.3f}s")
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
            
            # 运行推理
            results = self.model(
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
                        # 获取原始类别名称
                        original_class_name = self.model.names[int(cls)]
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
                    
                    # 触发报警
                    alarm_event = AlarmEvent(
                        stream_id=stream_id,
                        timestamp=current_time,
                        alarm_type=self._get_alarm_level(detection['confidence']),
                        confidence=detection['confidence'],
                        bbox=detection['bbox'],
                        class_name=class_name,
                        consecutive_count=self.alarm_states[stream_id][class_name]
                    )
                    
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
    
    def _should_reconnect(self, stream_id: str) -> bool:
        """判断是否应该重连"""
        # 这里可以实现更复杂的重连逻辑
        return True
    
    def _reconnect_stream(self, video_source: str) -> Optional[cv2.VideoCapture]:
        """重连视频流"""
        max_attempts = config_manager.get('video_streams.max_reconnect_attempts', 3)
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
            
            # 2. 保存带检测框的图片
            if self.save_images:
                self._save_detection_image(result, frame, result_dir, timestamp)
            
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
                            result_dir: str, timestamp: datetime) -> None:
        """保存带检测框的图片"""
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
                if confidence >= 0.7:
                    color = (0, 255, 0)  # 绿色 - 高置信度
                elif confidence >= 0.5:
                    color = (0, 255, 255)  # 黄色 - 中等置信度
                else:
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
                id_text = f"#{i+1}"
                cv2.putText(annotated_frame, id_text,
                          (x1 + 5, y2 - 10),
                          font, 0.5, (255, 255, 255), 1)
            
            # 在图片上添加时间戳和流信息
            info_text = f"Stream: {result.stream_id} | Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
            cv2.putText(annotated_frame, info_text,
                      (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            stats_text = f"Frame: {result.frame_id} | Objects: {result.bbox_count} | Processing: {result.processing_time:.3f}s"
            cv2.putText(annotated_frame, stats_text,
                      (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
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
                            crop_file = os.path.join(crops_dir, f"{i+1}_{class_name}_{confidence:.2f}.png")
                            crop_params = [cv2.IMWRITE_PNG_COMPRESSION, self.png_compression]
                        else:
                            crop_file = os.path.join(crops_dir, f"{i+1}_{class_name}_{confidence:.2f}.jpg")
                            crop_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
                        
                        cv2.imwrite(crop_file, crop, crop_params)
            
        except Exception as e:
            self.logger.error(f"保存检测图片失败: {e}")
    
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
