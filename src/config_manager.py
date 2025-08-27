"""
配置管理模块
负责加载、验证和管理系统配置
"""

import yaml
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = "config/default_config.yaml"):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
        # 延迟加载配置，避免在导入时立即加载
        self._loaded = False
    
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self.config = yaml.safe_load(file)
            
            self.logger.info(f"配置文件加载成功: {self.config_path}")
            self._validate_config()
            self._loaded = True
            
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")
            self._load_default_config()
            self._loaded = True
    
    def _validate_config(self) -> None:
        """验证配置文件的有效性"""
        required_sections = ['model', 'detection', 'alarm', 'video_streams', 'api']
        
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"配置文件缺少必要部分: {section}")
        
        # 验证模型路径 - 直接访问配置避免递归
        model_path = self.config.get('model', {}).get('path')
        if model_path and not os.path.exists(model_path):
            self.logger.warning(f"模型文件不存在: {model_path}")
        
        # 验证置信度阈值 - 直接访问配置避免递归
        confidence = self.config.get('detection', {}).get('confidence_threshold', 0.25)
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("置信度阈值必须在0.0-1.0之间")
    
    def _load_default_config(self) -> None:
        """加载默认配置"""
        self.config = {
            'model': {
                'path': 'constuction_waste/best.pt',
                'current_model': 'high_accuracy'
            },
            'detection': {
                'confidence_threshold': 0.25,
                'iou_threshold': 0.45,
                'image_size': 640,
                'fps_limit': 30,
                'max_streams': 10
            },
            'alarm': {
                'min_confidence': 0.5,
                'consecutive_frames': 3,
                'cooldown_seconds': 30
            },
            'video_streams': {
                'buffer_size': 5,
                'connection_timeout': 10,
                'reconnect_interval': 5,
                'max_reconnect_attempts': 3
            },
            'api': {
                'port': 8080,
                'host': '0.0.0.0',
                'version': 'v1',
                'debug': False
            },
            'logging': {
                'level': 'INFO',
                'file_path': 'logs/detection.log'
            },
            'performance': {
                'use_gpu': True,
                'gpu_device': 0,
                'worker_threads': 4
            }
        }
        self.logger.warning("使用默认配置")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值（支持点分隔的嵌套键）
        
        Args:
            key: 配置键，支持 'section.subsection.key' 格式
            default: 默认值
            
        Returns:
            配置值
        """
        # 确保配置已加载，但避免无限递归
        if not self._loaded and not hasattr(self, '_loading'):
            self._loading = True
            try:
                self.load_config()
            finally:
                delattr(self, '_loading')
            
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        """
        keys = key.split('.')
        config = self.config
        
        # 导航到最后一级
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # 设置值
        config[keys[-1]] = value
        self.logger.info(f"配置更新: {key} = {value}")
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """
        批量更新配置
        
        Args:
            updates: 要更新的配置字典
        """
        for key, value in updates.items():
            self.set(key, value)
    
    def save_config(self, path: Optional[str] = None) -> None:
        """
        保存配置到文件
        
        Args:
            path: 保存路径，为空则使用原路径
        """
        save_path = path or self.config_path
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            with open(save_path, 'w', encoding='utf-8') as file:
                yaml.dump(self.config, file, default_flow_style=False, 
                         allow_unicode=True, indent=2)
            
            self.logger.info(f"配置保存成功: {save_path}")
            
        except Exception as e:
            self.logger.error(f"保存配置文件失败: {e}")
    
    def reload_config(self) -> None:
        """重新加载配置文件"""
        self.logger.info("重新加载配置文件")
        self._loaded = False  # 重置加载标志
        self.load_config()
    
    def get_model_path(self) -> str:
        """获取当前模型路径"""
        # 确保配置已加载
        if not self._loaded:
            self.load_config()
            
        # 直接访问配置，避免递归调用get方法
        try:
            current_model = self.config.get('model', {}).get('current_model', 'high_accuracy')
            models = self.config.get('model', {}).get('models', {})
            model_path = models.get(current_model)
            
            if not model_path:
                model_path = self.config.get('model', {}).get('path')
            
            return model_path or "constuction_waste/best.pt"  # 默认路径
        except Exception:
            return "constuction_waste/best.pt"
    
    def get_detection_params(self) -> Dict[str, Any]:
        """获取检测参数"""
        # 确保配置已加载
        if not self._loaded:
            self.load_config()
            
        detection = self.config.get('detection', {})
        return {
            'confidence_threshold': detection.get('confidence_threshold', 0.25),
            'iou_threshold': detection.get('iou_threshold', 0.45),
            'image_size': detection.get('image_size', 640),
            'fps_limit': detection.get('fps_limit', 30)
        }
    
    def get_alarm_config(self) -> Dict[str, Any]:
        """获取报警配置"""
        # 确保配置已加载
        if not self._loaded:
            self.load_config()
            
        alarm = self.config.get('alarm', {})
        return {
            'min_confidence': alarm.get('min_confidence', 0.5),
            'consecutive_frames': alarm.get('consecutive_frames', 3),
            'cooldown_seconds': alarm.get('cooldown_seconds', 30),
            'levels': alarm.get('levels', {}),
            'notification_methods': alarm.get('notification_methods', ['callback', 'log'])
        }
    
    def get_api_config(self) -> Dict[str, Any]:
        """获取API配置"""
        # 确保配置已加载
        if not self._loaded:
            self.load_config()
            
        api = self.config.get('api', {})
        return {
            'host': api.get('host', '0.0.0.0'),
            'port': api.get('port', 8080),
            'version': api.get('version', 'v1'),
            'debug': api.get('debug', False),
            'cors_origins': api.get('cors_origins', ['*'])
        }


# 全局配置管理器实例
config_manager = ConfigManager()
