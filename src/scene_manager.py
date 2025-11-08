"""
场景管理器
负责处理场景下发、设备管理等业务逻辑
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

from .device_platform_client import DevicePlatformClient, StreamAddress
from .heartbeat_manager import HeartbeatManager
from .scene_mapper import SceneMapper
from .stream_manager import StreamManager, StreamConfig
from .region_filter import RegionFilter


@dataclass
class DeviceInfo:
    """设备信息"""
    device_gb_code: str  # 设备国标编码
    area: str            # 检测区域字符串
    stream_addr: Optional[StreamAddress] = None  # 流地址
    stream_id: Optional[str] = None  # 内部流ID


@dataclass
class SceneDeployment:
    """场景部署信息"""
    scene: str  # 场景名称
    algorithm: str  # 算法名称
    start_date: str  # 开始时间
    end_date: str  # 结束时间
    devices: List[DeviceInfo]  # 设备列表
    model_path: Optional[str] = None  # 模型路径
    target_classes: Optional[List[str]] = None  # 目标类别


class SceneManager:
    """场景管理器"""
    
    def __init__(
        self,
        device_client: DevicePlatformClient,
        heartbeat_manager: HeartbeatManager,
        scene_mapper: SceneMapper,
        stream_manager: StreamManager
    ):
        """
        初始化场景管理器
        
        Args:
            device_client: 设备平台客户端
            heartbeat_manager: 心跳管理器
            scene_mapper: 场景映射器
            stream_manager: 流管理器
        """
        self.logger = logging.getLogger(__name__)
        self.device_client = device_client
        self.heartbeat_manager = heartbeat_manager
        self.scene_mapper = scene_mapper
        self.stream_manager = stream_manager
        self.region_filter = RegionFilter()
        
        # 部署记录
        self.deployments: Dict[str, SceneDeployment] = {}  # deployment_id -> deployment
        
        # 启动场景到期检查线程
        self.monitor_running = False
        self.monitor_thread = None
        self._start_expiration_monitor()
        
        self.logger.info("场景管理器初始化完成")
    
    def _start_expiration_monitor(self):
        """启动场景到期监控线程"""
        import threading
        self.monitor_running = True
        self.monitor_thread = threading.Thread(
            target=self._expiration_monitor_worker,
            daemon=True,
            name="SceneExpirationMonitor"
        )
        self.monitor_thread.start()
        self.logger.info("场景到期监控已启动")
    
    def _expiration_monitor_worker(self):
        """场景到期监控工作线程"""
        import time
        from datetime import datetime
        
        while self.monitor_running:
            try:
                current_time = datetime.now()
                expired_scenes = []
                
                # 检查所有部署的场景
                for deployment_id, deployment in self.deployments.items():
                    try:
                        # 解析结束时间
                        end_time = datetime.strptime(deployment.end_date, "%Y-%m-%d %H:%M:%S")
                        
                        # 如果已到期
                        if current_time >= end_time:
                            expired_scenes.append(deployment_id)
                            self.logger.info(
                                f"场景已到期: {deployment_id}, "
                                f"算法={deployment.algorithm}, "
                                f"结束时间={deployment.end_date}"
                            )
                    except Exception as e:
                        self.logger.error(f"解析场景时间失败: {deployment_id}, {e}")
                
                # 停止到期的场景
                for deployment_id in expired_scenes:
                    try:
                        self.stop_scene(deployment_id)
                        self.logger.info(f"已自动停止到期场景: {deployment_id}")
                    except Exception as e:
                        self.logger.error(f"停止到期场景失败: {deployment_id}, {e}")
                
                # 每30秒检查一次
                time.sleep(30)
                
            except Exception as e:
                self.logger.error(f"场景到期监控异常: {e}", exc_info=True)
                time.sleep(30)
    
    def stop(self):
        """停止场景管理器"""
        self.monitor_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info("场景管理器已停止")
    
    def deploy_scene(
        self,
        scene: str,
        algorithm: str,
        devices: List[Dict],
        start_date: str,
        end_date: str
    ) -> Dict:
        """
        部署场景
        
        Args:
            scene: 场景名称，如"明火告警"
            algorithm: 算法名称，如"火焰检测"
            devices: 设备列表，每个设备包含deviceGbCode和area字段
            start_date: 开始时间
            end_date: 结束时间
            
        Returns:
            部署结果字典
        """
        self.logger.info(f"开始部署场景: {scene}, 算法: {algorithm}, 设备数: {len(devices)}")
        
        # 1. 根据算法名称获取模型路径（忽略scene字段）
        model_path = self.scene_mapper.get_model_by_algorithm(algorithm)
        
        if not model_path:
            return {
                'status': 1,
                'message': f'未找到算法 "{algorithm}" 对应的模型',
                'data': {
                    'deployed_devices': 0,
                    'failed_devices': len(devices),
                    'failed_list': [
                        {
                            'deviceGbCode': dev.get('deviceGbCode'),
                            'reason': f'算法 "{algorithm}" 未配置模型'
                        }
                        for dev in devices
                    ]
                }
            }
        
        # 2. 获取目标检测类别（可选）
        target_classes = self.scene_mapper.get_target_classes_by_algorithm(algorithm)
        
        # 3. 逐个部署设备
        deployed_devices = []
        failed_devices = []
        
        for device_data in devices:
            device_gb_code = device_data.get('deviceGbCode')
            area = device_data.get('area', '')
            
            try:
                # 3.1 获取流地址
                stream_addr = self.device_client.get_play_url(device_gb_code)
                
                if not stream_addr or not stream_addr.rtsp:
                    failed_devices.append({
                        'deviceGbCode': device_gb_code,
                        'reason': '获取流地址失败'
                    })
                    continue
                
                # 3.2 生成内部流ID
                stream_id = f"scene_{scene}_{device_gb_code}".replace(' ', '_')
                
                # 3.3 启动检测任务
                success = self.stream_manager.add_stream(
                    stream_config=StreamConfig(
                        stream_id=stream_id,
                        rtsp_url=stream_addr.rtsp,
                        name=f"{scene}_{device_gb_code}",
                        model_path=model_path,
                        target_classes=target_classes,
                        region_str=area,
                        scene_name=scene
                    )
                )
                
                if not success:
                    failed_devices.append({
                        'deviceGbCode': device_gb_code,
                        'reason': '启动检测任务失败'
                    })
                    continue
                
                # 3.4 启动心跳
                self.heartbeat_manager.start_heartbeat(device_gb_code)
                
                # 记录部署成功
                device_info = DeviceInfo(
                    device_gb_code=device_gb_code,
                    area=area,
                    stream_addr=stream_addr,
                    stream_id=stream_id
                )
                deployed_devices.append(device_info)
                
                self.logger.info(f"设备 {device_gb_code} 部署成功")
                
            except Exception as e:
                self.logger.error(f"设备 {device_gb_code} 部署失败: {e}")
                failed_devices.append({
                    'deviceGbCode': device_gb_code,
                    'reason': str(e)
                })
        
        # 4. 记录部署信息
        deployment = SceneDeployment(
            scene=scene,
            algorithm=algorithm,
            start_date=start_date,
            end_date=end_date,
            devices=deployed_devices,
            model_path=model_path,
            target_classes=target_classes
        )
        
        deployment_id = f"{scene}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.deployments[deployment_id] = deployment
        
        # 5. 返回结果
        result = {
            'status': 0 if len(deployed_devices) > 0 else 1,
            'message': '场景部署成功' if len(deployed_devices) > 0 else '场景部署失败',
            'data': {
                'deployment_id': deployment_id,
                'deployed_devices': len(deployed_devices),
                'failed_devices': len(failed_devices),
                'failed_list': failed_devices
            }
        }
        
        self.logger.info(
            f"场景部署完成: 成功{len(deployed_devices)}个, 失败{len(failed_devices)}个"
        )
        
        return result
    
    def get_deployment_info(self, deployment_id: str) -> Optional[Dict]:
        """
        获取部署信息
        
        Args:
            deployment_id: 部署ID
            
        Returns:
            部署信息字典
        """
        deployment = self.deployments.get(deployment_id)
        if not deployment:
            return None
        
        return {
            'deployment_id': deployment_id,
            'scene': deployment.scene,
            'algorithm': deployment.algorithm,
            'start_date': deployment.start_date,
            'end_date': deployment.end_date,
            'model_path': deployment.model_path,
            'target_classes': deployment.target_classes,
            'devices': [
                {
                    'deviceGbCode': dev.device_gb_code,
                    'area': dev.area,
                    'stream_id': dev.stream_id,
                    'rtsp_url': dev.stream_addr.rtsp if dev.stream_addr else None
                }
                for dev in deployment.devices
            ]
        }
    
    def list_deployments(self) -> List[Dict]:
        """
        列出所有部署
        
        Returns:
            部署列表
        """
        return [
            self.get_deployment_info(deployment_id)
            for deployment_id in self.deployments.keys()
        ]
    
    def stop_deployment(self, deployment_id: str) -> bool:
        """
        停止部署
        
        Args:
            deployment_id: 部署ID
            
        Returns:
            是否成功
        """
        deployment = self.deployments.get(deployment_id)
        if not deployment:
            self.logger.warning(f"部署不存在: {deployment_id}")
            return False
        
        # 停止所有设备的检测和心跳
        for device_info in deployment.devices:
            if device_info.stream_id:
                self.stream_manager.remove_stream(device_info.stream_id)
            
            self.heartbeat_manager.stop_heartbeat(device_info.device_gb_code)
        
        # 移除部署记录
        del self.deployments[deployment_id]
        
        self.logger.info(f"部署 {deployment_id} 已停止")
        return True

