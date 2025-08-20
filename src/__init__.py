"""
实时视频检测系统
"""

__version__ = "1.0.0"
__author__ = "Video Detection System"
__description__ = "实时视频目标检测系统，支持RTSP流管理和报警通知"

from .config_manager import config_manager
from .detection_engine import DetectionEngine, DetectionResult, AlarmEvent
from .stream_manager import StreamManager, StreamConfig, StreamStatus
from .alarm_system import AlarmSystem, AlarmRule, NotificationType
from .api_server import APIServer

__all__ = [
    'config_manager',
    'DetectionEngine',
    'DetectionResult', 
    'AlarmEvent',
    'StreamManager',
    'StreamConfig',
    'StreamStatus',
    'AlarmSystem',
    'AlarmRule',
    'NotificationType',
    'APIServer'
]
