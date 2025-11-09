"""
设备平台客户端
负责调用设备管理平台的接口获取流地址和发送心跳
"""

import requests
import logging
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class StreamAddress:
    """视频流地址"""
    rtsp: str
    rtmp: Optional[str] = None
    hls: Optional[str] = None
    flv: Optional[str] = None
    webrtc: Optional[str] = None


class DevicePlatformClient:
    """设备平台客户端"""
    
    def __init__(self, base_url: str, timeout: int = 10, retry_times: int = 3):
        """
        初始化设备平台客户端
        
        Args:
            base_url: 设备平台基础URL，如 http://192.168.1.100:8080
            timeout: 请求超时时间（秒）
            retry_times: 失败重试次数
        """
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_times = retry_times
        
        self.logger.info(f"设备平台客户端初始化: {self.base_url}")
    
    def get_play_url(self, device_gb_code: str) -> Optional[StreamAddress]:
        """
        获取设备播放地址
        
        Args:
            device_gb_code: 设备国标编码
            
        Returns:
            StreamAddress对象，包含各种流地址；失败返回None
        """
        url = f"{self.base_url}/device/getPlayUrl"
        data = {"deviceGbCode": device_gb_code}
        
        for attempt in range(self.retry_times):
            try:
                self.logger.info(f"获取设备播放地址: {device_gb_code} (尝试 {attempt + 1}/{self.retry_times})")
                
                response = requests.post(
                    url,
                    json=data,
                    timeout=self.timeout,
                    headers={'Content-Type': 'application/json'}
                )
                
                result = response.json()
                
                if result.get('status') == 0:
                    stream_data = result.get('data', {})
                    stream_addr = StreamAddress(
                        rtsp=stream_data.get('rtsp', ''),
                        rtmp=stream_data.get('rtmp'),
                        hls=stream_data.get('hls'),
                        flv=stream_data.get('flv'),
                        webrtc=stream_data.get('webrtc')
                    )
                    
                    self.logger.info(f"成功获取设备 {device_gb_code} 的流地址: {stream_addr.rtsp}")
                    return stream_addr
                else:
                    self.logger.warning(f"获取播放地址失败: {result.get('message', '未知错误')}")
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"获取播放地址超时 (尝试 {attempt + 1}/{self.retry_times})")
            except requests.exceptions.RequestException as e:
                self.logger.error(f"获取播放地址请求失败: {e}")
            except Exception as e:
                self.logger.error(f"获取播放地址异常: {e}")
            
            if attempt < self.retry_times - 1:
                time.sleep(1)  # 重试前等待1秒
        
        self.logger.error(f"获取设备 {device_gb_code} 播放地址失败，已重试{self.retry_times}次")
        return None
    
    def send_heartbeat(self, device_gb_code: str) -> bool:
        """
        发送设备心跳
        
        Args:
            device_gb_code: 设备国标编码
            
        Returns:
            心跳是否成功
        """
        url = f"{self.base_url}/device/heartBeat"
        data = {"deviceGbCode": device_gb_code}
        
        try:
            response = requests.post(
                url,
                json=data,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            result = response.json()
            
            if result.get('status') == 0:
                self.logger.debug(f"设备 {device_gb_code} 心跳成功")
                return True
            else:
                self.logger.warning(f"设备 {device_gb_code} 心跳失败: {result.get('message', '未知错误')}")
                return False
                
        except requests.exceptions.Timeout:
            self.logger.warning(f"设备 {device_gb_code} 心跳超时")
            return False
        except Exception as e:
            self.logger.error(f"设备 {device_gb_code} 心跳异常: {e}")
            return False
    
    def send_alarm(self, alarm_data: Dict[str, Any]) -> bool:
        """
        发送告警事件到设备平台
        
        Args:
            alarm_data: 告警数据字典，包含：
                - deviceGbCode: 设备国标编码
                - alarmType: 告警类型
                - alarmLevel: 告警级别
                - alarmTime: 告警时间
                - pic: 告警图片URL
                - record: 告警录像URL
                - 其他自定义字段
        
        Returns:
            是否发送成功
        """
        url = f"{self.base_url}/event/alarm"
        
        try:
            response = requests.post(
                url,
                json=alarm_data,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            result = response.json()
            
            if result.get('status') == 0:
                self.logger.info(f"告警发送成功: {alarm_data.get('deviceGbCode')}, 类型: {alarm_data.get('alarmType')}")
                return True
            else:
                self.logger.warning(f"告警发送失败: {result.get('message', '未知错误')}")
                return False
                
        except requests.exceptions.Timeout:
            self.logger.warning(f"告警发送超时: {alarm_data.get('deviceGbCode')}")
            return False
        except Exception as e:
            self.logger.error(f"告警发送异常: {e}")
            return False

