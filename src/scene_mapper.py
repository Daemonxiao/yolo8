"""
场景映射管理器
负责将算法名称映射到模型文件
"""

import logging
from typing import Optional, List
import os
from .config_manager import config_manager


class SceneMapper:
    """算法到模型的映射管理器"""
    
    def __init__(self):
        """初始化场景映射管理器"""
        self.logger = logging.getLogger(__name__)
        
        # 从配置文件加载算法模型映射
        self.algorithm_models = config_manager.get('model.algorithm_models', {})
        
        if not self.algorithm_models:
            self.logger.warning("未配置算法模型映射，请在配置文件中添加 model.algorithm_models")
        else:
            self.logger.info(f"加载算法映射: {len(self.algorithm_models)} 个算法")
            for algorithm, model_path in self.algorithm_models.items():
                self.logger.debug(f"  - {algorithm}: {model_path}")
    
    def get_model_by_algorithm(self, algorithm_name: str) -> Optional[str]:
        """
        根据算法名称获取模型文件路径
        
        Args:
            algorithm_name: 算法名称，如"火焰检测"
            
        Returns:
            模型文件路径，如果未找到返回None
        """
        model_path = self.algorithm_models.get(algorithm_name)
        
        if model_path:
            # 检查模型文件是否存在
            if os.path.exists(model_path):
                self.logger.info(f"算法 '{algorithm_name}' -> 模型: {model_path}")
                return model_path
            else:
                self.logger.warning(f"算法 '{algorithm_name}' 的模型文件不存在: {model_path}")
                return None
        
        self.logger.warning(f"未找到算法 '{algorithm_name}' 的配置，请检查 model.algorithm_models")
        return None
    
    def get_target_classes_by_algorithm(self, algorithm_name: str) -> Optional[List[str]]:
        """
        根据算法名称获取目标检测类别（可选）
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            目标类别列表，如果不限制则返回None
        """
        # 可以根据需要在配置文件中添加类别过滤配置
        # 例如: model.algorithm_classes.火焰检测 = ["fire", "smoke"]
        algorithm_classes = config_manager.get('model.algorithm_classes', {})
        return algorithm_classes.get(algorithm_name)
    
    def get_custom_type_by_algorithm(self, algorithm_name: str) -> Optional[str]:
        """
        根据算法名称获取自定义处理类型（可选）
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            自定义处理类型，如 "helmet_detection_alert"，如果未配置则返回None
        """
        algorithm_custom_types = config_manager.get('model.algorithm_custom_types', {})
        return algorithm_custom_types.get(algorithm_name)
    
    def get_all_algorithms(self) -> List[str]:
        """
        获取所有已配置的算法名称
        
        Returns:
            算法名称列表
        """
        return list(self.algorithm_models.keys())
    
    def validate_algorithm(self, algorithm_name: str) -> bool:
        """
        验证算法是否已配置
        
        Args:
            algorithm_name: 算法名称
            
        Returns:
            是否已配置
        """
        return algorithm_name in self.algorithm_models
    
    def get_algorithm_info(self) -> dict:
        """
        获取所有算法的配置信息
        
        Returns:
            算法配置字典
        """
        info = {}
        algorithm_classes = config_manager.get('model.algorithm_classes', {})
        
        for algorithm, model_path in self.algorithm_models.items():
            info[algorithm] = {
                'model_path': model_path,
                'exists': os.path.exists(model_path),
                'target_classes': algorithm_classes.get(algorithm, [])
            }
        return info
