"""
Kafka告警推送器
负责将告警消息推送到Kafka
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from kafka import KafkaProducer
from kafka.errors import KafkaError


class KafkaPublisher:
    """Kafka告警推送器"""
    
    def __init__(self, bootstrap_servers: str, topic: str, enabled: bool = True):
        """
        初始化Kafka推送器
        
        Args:
            bootstrap_servers: Kafka服务器地址，如 "192.168.1.200:9092"
            topic: 告警Topic名称，如 "event-alarm"
            enabled: 是否启用Kafka推送
        """
        self.logger = logging.getLogger(__name__)
        self.topic = topic
        self.enabled = enabled
        self.producer: Optional[KafkaProducer] = None
        
        if not self.enabled:
            self.logger.warning("Kafka推送已禁用")
            return
        
        try:
            self.logger.info(f"初始化Kafka生产者: {bootstrap_servers}, topic: {topic}")
            
            self.producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers.split(','),
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                acks='all',  # 等待所有副本确认
                retries=3,   # 失败重试3次
                max_in_flight_requests_per_connection=1,  # 保证顺序
                compression_type='gzip'  # 启用压缩
            )
            
            self.logger.info("Kafka生产者初始化成功")
            
        except Exception as e:
            self.logger.error(f"Kafka生产者初始化失败: {e}")
            self.producer = None
            self.enabled = False
    
    def publish_alarm(
        self,
        scene: str,
        device_gb_code: str,
        pic_url: str,
        record_url: str,
        alarm_time: Optional[datetime] = None
    ) -> bool:
        """
        推送告警消息到Kafka
        
        Args:
            scene: 告警场景名称，如"火警"
            device_gb_code: 设备国标编码
            pic_url: 告警抓拍图片URL
            record_url: 告警录像地址URL
            alarm_time: 告警时间，默认为当前时间
            
        Returns:
            是否推送成功
        """
        if not self.enabled or not self.producer:
            self.logger.warning("Kafka推送未启用，跳过告警推送")
            return False
        
        try:
            # 构建告警消息
            if alarm_time is None:
                alarm_time = datetime.now()
            
            message = {
                "scene": scene,
                "alarmTime": alarm_time.strftime('%Y-%m-%d %H:%M:%S'),
                "pic": pic_url,
                "deviceGbCode": device_gb_code,
                "record": record_url
            }
            
            self.logger.info(f"推送告警消息到Kafka: scene={scene}, device={device_gb_code}")
            self.logger.debug(f"告警消息内容: {message}")
            
            # 发送消息
            future = self.producer.send(self.topic, value=message)
            
            # 等待发送结果（同步发送）
            record_metadata = future.get(timeout=10)
            
            self.logger.info(
                f"告警消息推送成功: topic={record_metadata.topic}, "
                f"partition={record_metadata.partition}, offset={record_metadata.offset}"
            )
            
            return True
            
        except KafkaError as e:
            self.logger.error(f"Kafka推送失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"推送告警消息异常: {e}")
            return False
    
    def publish_batch_alarms(self, alarms: list) -> int:
        """
        批量推送告警消息
        
        Args:
            alarms: 告警消息列表，每个元素为字典，包含scene, device_gb_code等字段
            
        Returns:
            成功推送的消息数量
        """
        success_count = 0
        
        for alarm in alarms:
            if self.publish_alarm(
                scene=alarm['scene'],
                device_gb_code=alarm['device_gb_code'],
                pic_url=alarm['pic_url'],
                record_url=alarm['record_url'],
                alarm_time=alarm.get('alarm_time')
            ):
                success_count += 1
        
        return success_count
    
    def close(self) -> None:
        """关闭Kafka生产者"""
        if self.producer:
            try:
                self.producer.flush()  # 确保所有消息发送完成
                self.producer.close()
                self.logger.info("Kafka生产者已关闭")
            except Exception as e:
                self.logger.error(f"关闭Kafka生产者失败: {e}")
    
    def __del__(self):
        """析构函数，自动关闭连接"""
        self.close()

