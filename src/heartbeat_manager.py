"""
心跳管理器
负责维护设备流的心跳保活
"""

import threading
import time
import logging
from typing import Dict, Set
from .device_platform_client import DevicePlatformClient


class HeartbeatManager:
    """心跳管理器"""
    
    def __init__(self, device_client: DevicePlatformClient, interval: int = 10):
        """
        初始化心跳管理器
        
        Args:
            device_client: 设备平台客户端
            interval: 心跳间隔（秒），默认10秒
        """
        self.logger = logging.getLogger(__name__)
        self.device_client = device_client
        self.interval = interval
        
        # 心跳线程管理
        self.heartbeat_threads: Dict[str, threading.Thread] = {}
        self.heartbeat_stop_flags: Dict[str, threading.Event] = {}
        
        # 心跳统计
        self.heartbeat_success_count: Dict[str, int] = {}
        self.heartbeat_fail_count: Dict[str, int] = {}
        self.last_heartbeat_time: Dict[str, float] = {}
        
        self.logger.info(f"心跳管理器初始化完成，心跳间隔: {interval}秒")
    
    def start_heartbeat(self, device_gb_code: str) -> bool:
        """
        启动设备心跳
        
        Args:
            device_gb_code: 设备国标编码
            
        Returns:
            是否成功启动
        """
        if device_gb_code in self.heartbeat_threads:
            self.logger.warning(f"设备 {device_gb_code} 心跳已在运行")
            return False
        
        # 创建停止标志
        stop_flag = threading.Event()
        self.heartbeat_stop_flags[device_gb_code] = stop_flag
        
        # 初始化统计
        self.heartbeat_success_count[device_gb_code] = 0
        self.heartbeat_fail_count[device_gb_code] = 0
        self.last_heartbeat_time[device_gb_code] = time.time()
        
        # 创建并启动心跳线程
        thread = threading.Thread(
            target=self._heartbeat_worker,
            args=(device_gb_code, stop_flag),
            daemon=True,
            name=f"heartbeat-{device_gb_code}"
        )
        
        self.heartbeat_threads[device_gb_code] = thread
        thread.start()
        
        self.logger.info(f"设备 {device_gb_code} 心跳线程已启动")
        return True
    
    def stop_heartbeat(self, device_gb_code: str) -> bool:
        """
        停止设备心跳
        
        Args:
            device_gb_code: 设备国标编码
            
        Returns:
            是否成功停止
        """
        if device_gb_code not in self.heartbeat_threads:
            self.logger.warning(f"设备 {device_gb_code} 心跳未运行")
            return False
        
        # 设置停止标志
        stop_flag = self.heartbeat_stop_flags.get(device_gb_code)
        if stop_flag:
            stop_flag.set()
        
        # 等待线程结束
        thread = self.heartbeat_threads.get(device_gb_code)
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        
        # 清理
        self.heartbeat_threads.pop(device_gb_code, None)
        self.heartbeat_stop_flags.pop(device_gb_code, None)
        
        self.logger.info(f"设备 {device_gb_code} 心跳线程已停止")
        return True
    
    def _heartbeat_worker(self, device_gb_code: str, stop_flag: threading.Event) -> None:
        """
        心跳工作线程
        
        Args:
            device_gb_code: 设备国标编码
            stop_flag: 停止标志
        """
        self.logger.info(f"设备 {device_gb_code} 心跳工作线程启动")
        
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        while not stop_flag.is_set():
            try:
                # 发送心跳
                success = self.device_client.send_heartbeat(device_gb_code)
                
                current_time = time.time()
                self.last_heartbeat_time[device_gb_code] = current_time
                
                if success:
                    self.heartbeat_success_count[device_gb_code] = \
                        self.heartbeat_success_count.get(device_gb_code, 0) + 1
                    consecutive_failures = 0
                else:
                    self.heartbeat_fail_count[device_gb_code] = \
                        self.heartbeat_fail_count.get(device_gb_code, 0) + 1
                    consecutive_failures += 1
                    
                    if consecutive_failures >= max_consecutive_failures:
                        self.logger.error(
                            f"设备 {device_gb_code} 心跳连续失败{consecutive_failures}次，可能需要重连"
                        )
                
            except Exception as e:
                self.logger.error(f"设备 {device_gb_code} 心跳异常: {e}")
                consecutive_failures += 1
            
            # 等待下次心跳（可被stop_flag中断）
            stop_flag.wait(self.interval)
        
        self.logger.info(f"设备 {device_gb_code} 心跳工作线程结束")
    
    def get_heartbeat_stats(self, device_gb_code: str) -> Dict[str, any]:
        """
        获取设备心跳统计信息
        
        Args:
            device_gb_code: 设备国标编码
            
        Returns:
            心跳统计信息字典
        """
        return {
            'device_gb_code': device_gb_code,
            'is_running': device_gb_code in self.heartbeat_threads,
            'success_count': self.heartbeat_success_count.get(device_gb_code, 0),
            'fail_count': self.heartbeat_fail_count.get(device_gb_code, 0),
            'last_heartbeat_time': self.last_heartbeat_time.get(device_gb_code, 0),
            'time_since_last_heartbeat': time.time() - self.last_heartbeat_time.get(device_gb_code, 0)
        }
    
    def get_all_stats(self) -> Dict[str, Dict[str, any]]:
        """
        获取所有设备的心跳统计
        
        Returns:
            所有设备的心跳统计字典
        """
        return {
            device_gb_code: self.get_heartbeat_stats(device_gb_code)
            for device_gb_code in self.heartbeat_threads.keys()
        }
    
    def stop_all(self) -> None:
        """停止所有心跳"""
        device_codes = list(self.heartbeat_threads.keys())
        for device_gb_code in device_codes:
            self.stop_heartbeat(device_gb_code)
        
        self.logger.info("所有心跳线程已停止")

