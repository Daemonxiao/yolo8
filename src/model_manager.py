"""
模型管理器
负责管理多个YOLO模型的加载和使用
"""

import logging
import os
from typing import Dict, Optional
from ultralytics import YOLO
import torch


# 修复 PyTorch 2.6+ 的 weights_only 安全警告
# 允许加载 YOLO 模型需要的自定义类
try:
    # 添加 YOLO 和 PyTorch 需要的安全全局类
    from ultralytics.nn.tasks import DetectionModel
    from torch.nn.modules.container import Sequential
    
    safe_globals = [
        DetectionModel,
        Sequential,
    ]
    
    # 尝试添加其他可能需要的类
    try:
        from ultralytics.nn.modules import (
            Conv, C2f, SPPF, Detect, 
            Bottleneck, C3, DWConv
        )
        safe_globals.extend([Conv, C2f, SPPF, Detect, Bottleneck, C3, DWConv])
    except ImportError:
        pass
    
    # 添加到 PyTorch 安全全局列表
    torch.serialization.add_safe_globals(safe_globals)
    
except Exception as e:
    # 旧版本 PyTorch 不需要此设置，或者导入失败时使用备用方案
    import logging
    logging.getLogger(__name__).debug(f"跳过 PyTorch 安全全局设置: {e}")


class ModelManager:
    """多模型管理器"""
    
    def __init__(self, per_stream_model: bool = False):
        """
        初始化模型管理器
        
        Args:
            per_stream_model: 是否为每个流创建独立模型实例（提升并发性能，但占用更多内存）
        """
        self.logger = logging.getLogger(__name__)
        
        # 模型缓存 {model_path: YOLO_model} 或 {model_path: {stream_id: YOLO_model}}
        self.models: Dict[str, YOLO] = {}
        self.per_stream_model = per_stream_model
        
        # 如果启用每流独立模型，使用嵌套字典
        if self.per_stream_model:
            self.models = {}  # {model_path: {stream_id: YOLO_model}}
            self.logger.info("启用每流独立模型模式（提升并发性能）")
        
        # 设备检测
        self.device = self._get_device()
        
        # 优化PyTorch线程数（提升多流并发性能）
        self._optimize_torch_threads()
        
        self.logger.info(f"模型管理器初始化完成，使用设备: {self.device}")
    
    def _optimize_torch_threads(self) -> None:
        """优化PyTorch线程数配置"""
        import os
        cpu_count = os.cpu_count() or 4
        
        # 设置PyTorch线程数（建议为CPU核心数）
        torch.set_num_threads(cpu_count)
        # 设置inter-op线程数（用于并行操作）
        torch.set_num_interop_threads(max(1, cpu_count // 2))
        
        # 设置环境变量（确保所有PyTorch操作都使用这些设置）
        os.environ['OMP_NUM_THREADS'] = str(cpu_count)
        os.environ['MKL_NUM_THREADS'] = str(cpu_count)
        os.environ['NUMEXPR_MAX_THREADS'] = str(cpu_count)
        
        self.logger.info(
            f"PyTorch线程优化: "
            f"num_threads={torch.get_num_threads()}, "
            f"num_interop_threads={torch.get_num_interop_threads()}, "
            f"CPU核心数={cpu_count}"
        )
    
    def _get_device(self) -> str:
        """获取推理设备"""
        if torch.cuda.is_available():
            device = 'cuda'
            self.logger.info(f"检测到GPU: {torch.cuda.get_device_name(0)}")
        elif torch.backends.mps.is_available():
            device = 'mps'
            self.logger.info("检测到Apple Silicon GPU (MPS)")
        else:
            device = 'cpu'
            self.logger.info("使用CPU进行推理")
        
        return device
    
    def load_model(self, model_path: str, force_reload: bool = False, stream_id: str = None) -> bool:
        """
        加载模型
        
        Args:
            model_path: 模型文件路径
            force_reload: 是否强制重新加载
            stream_id: 流ID（当per_stream_model=True时使用）
            
        Returns:
            是否加载成功
        """
        if self.per_stream_model and stream_id:
            # 每流独立模型模式
            if model_path not in self.models:
                self.models[model_path] = {}
            
            stream_models = self.models[model_path]
            
            # 如果该流的模型已加载且不强制重载，直接返回
            if stream_id in stream_models and not force_reload:
                self.logger.debug(f"流 {stream_id} 的模型已加载: {model_path}")
                return True
        else:
            # 共享模型模式
            # 如果模型已加载且不强制重载，直接返回
            if model_path in self.models and not force_reload:
                self.logger.debug(f"模型已加载: {model_path}")
                return True
        
        try:
            # 检查文件是否存在
            if not os.path.exists(model_path):
                self.logger.error(f"模型文件不存在: {model_path}")
                return False
            
            self.logger.info(f"正在加载模型: {model_path}")
            
            # 加载YOLO模型
            # 对于可信任的本地模型文件，设置 weights_only=False
            import torch
            _original_load = torch.load
            
            def _patched_load(*args, **kwargs):
                # 强制设置 weights_only=False 用于 YOLO 模型加载
                kwargs['weights_only'] = False
                return _original_load(*args, **kwargs)
            
            # 临时替换 torch.load
            torch.load = _patched_load
            try:
                model = YOLO(model_path)
                model.to(self.device)
            finally:
                # 恢复原始 torch.load
                torch.load = _original_load
            
            # 缓存模型
            if self.per_stream_model and stream_id:
                # 每流独立模型模式
                if model_path not in self.models:
                    self.models[model_path] = {}
                self.models[model_path][stream_id] = model
                self.logger.info(f"为流 {stream_id} 加载独立模型: {model_path}")
            else:
                # 共享模型模式
                self.models[model_path] = model
            
            # 获取模型信息
            model_info = {
                'path': model_path,
                'classes': model.names if hasattr(model, 'names') else {},
                'device': self.device
            }
            
            log_msg = f"模型加载成功: {model_path}\n  - 类别数量: {len(model_info['classes'])}\n  - 设备: {model_info['device']}"
            if self.per_stream_model and stream_id:
                log_msg += f"\n  - 流ID: {stream_id}"
            
            self.logger.info(log_msg)
            
            return True
            
        except Exception as e:
            self.logger.error(f"模型加载失败 {model_path}: {e}")
            return False
    
    def get_model(self, model_path: str, stream_id: str = None) -> Optional[YOLO]:
        """
        获取已加载的模型
        
        Args:
            model_path: 模型文件路径
            stream_id: 流ID（当per_stream_model=True时必需）
            
        Returns:
            YOLO模型实例，如果未加载则返回None
            
        注意：
            - 如果per_stream_model=False：多个流共享同一个模型实例（节省内存，但可能串行执行）
            - 如果per_stream_model=True：每个流使用独立的模型实例（提升并发性能，但占用更多内存）
        """
        if self.per_stream_model:
            # 每流独立模型模式
            if not stream_id:
                self.logger.warning("per_stream_model=True时，需要提供stream_id")
                return None
            
            if model_path not in self.models:
                self.models[model_path] = {}
            
            stream_models = self.models[model_path]
            
            if stream_id not in stream_models:
                # 为这个流加载独立的模型实例
                if self.load_model(model_path, stream_id=stream_id):
                    return stream_models.get(stream_id)
                return None
            
            return stream_models.get(stream_id)
        else:
            # 共享模型模式（原有逻辑）
            if model_path not in self.models:
                # 尝试自动加载
                if self.load_model(model_path):
                    return self.models.get(model_path)
                return None
            
            return self.models.get(model_path)
    
    def unload_model(self, model_path: str) -> bool:
        """
        卸载模型（共享模式：卸载整个模型；每流独立模式：卸载所有流的该模型）
        
        Args:
            model_path: 模型文件路径
            
        Returns:
            是否卸载成功
        """
        if self.per_stream_model:
            # 每流独立模型模式：卸载该模型路径下的所有流模型
            if model_path in self.models:
                stream_count = len(self.models[model_path])
                del self.models[model_path]
                self.logger.info(f"模型已卸载: {model_path} (共 {stream_count} 个流实例)")
                return True
        else:
            # 共享模型模式：卸载共享模型
            if model_path in self.models:
                del self.models[model_path]
                self.logger.info(f"模型已卸载: {model_path}")
                return True
        return False
    
    def unload_stream_model(self, model_path: str, stream_id: str) -> bool:
        """
        卸载特定流的模型实例（仅用于每流独立模型模式）
        
        Args:
            model_path: 模型文件路径
            stream_id: 流ID
            
        Returns:
            是否卸载成功
        """
        if not self.per_stream_model:
            # 共享模式不需要卸载单个流的模型
            return False
        
        if model_path in self.models and stream_id in self.models[model_path]:
            del self.models[model_path][stream_id]
            self.logger.info(f"流 {stream_id} 的模型已卸载: {model_path}")
            
            # 如果该模型路径下没有其他流了，清理空字典
            if len(self.models[model_path]) == 0:
                del self.models[model_path]
                self.logger.debug(f"模型路径 {model_path} 下已无流，清理空字典")
            
            return True
        return False
    
    def get_loaded_models(self) -> Dict[str, dict]:
        """
        获取所有已加载的模型信息
        
        Returns:
            模型信息字典 {model_path: model_info}
        """
        models_info = {}
        
        for model_path, model in self.models.items():
            models_info[model_path] = {
                'path': model_path,
                'classes': model.names if hasattr(model, 'names') else {},
                'num_classes': len(model.names) if hasattr(model, 'names') else 0,
                'device': self.device
            }
        
        return models_info
    
    def preload_models(self, model_paths: list) -> Dict[str, bool]:
        """
        批量预加载模型
        
        Args:
            model_paths: 模型文件路径列表
            
        Returns:
            加载结果 {model_path: success}
        """
        results = {}
        
        for model_path in model_paths:
            results[model_path] = self.load_model(model_path)
        
        success_count = sum(1 for v in results.values() if v)
        self.logger.info(
            f"批量加载完成: {success_count}/{len(model_paths)} 个模型加载成功"
        )
        
        return results
    
    def clear_all_models(self):
        """清空所有已加载的模型"""
        count = len(self.models)
        self.models.clear()
        self.logger.info(f"已清空所有模型，共 {count} 个")
    
    def get_model_classes(self, model_path: str) -> Dict[int, str]:
        """
        获取模型的类别映射
        
        Args:
            model_path: 模型文件路径
            
        Returns:
            类别映射 {class_id: class_name}
        """
        model = self.get_model(model_path)
        if model and hasattr(model, 'names'):
            return model.names
        return {}


# 全局模型管理器实例
# 默认使用共享模型模式（节省内存）
# 如需提升多流并发性能，可以改为 per_stream_model=True
model_manager = ModelManager(per_stream_model=True)

