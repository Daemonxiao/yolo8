"""
报警系统
负责处理各种报警规则和通知方式
"""

import logging
import time
import threading
import json
import requests
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
import queue
from enum import Enum

from .detection_engine import AlarmEvent
from .config_manager import config_manager
from .kafka_publisher import KafkaPublisher


class NotificationType(Enum):
    """通知类型枚举"""
    LOG = "log"
    CALLBACK = "callback"
    WEBHOOK = "webhook"


@dataclass
class NotificationConfig:
    """通知配置"""
    type: NotificationType
    enabled: bool = True
    config: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}


@dataclass
class AlarmRule:
    """报警规则"""
    rule_id: str
    name: str
    stream_ids: List[str]  # 适用的流ID，空表示所有流
    class_names: List[str]  # 目标类别，空表示所有类别
    min_confidence: float = 0.5
    consecutive_frames: int = 3
    cooldown_seconds: int = 30
    time_range: Optional[Dict[str, str]] = None  # {'start': '08:00', 'end': '18:00'}
    enabled: bool = True
    notifications: List[NotificationType] = None
    
    def __post_init__(self):
        if self.notifications is None:
            self.notifications = [NotificationType.LOG]


class AlarmSystem:
    """报警系统"""
    
    def __init__(self, device_client=None, stream_manager=None, kafka_config=None):
        """
        初始化报警系统
        
        Args:
            device_client: 设备平台客户端（可选，用于发送告警到设备平台）
            stream_manager: 流管理器（可选，用于获取流配置和设备编号）
            kafka_config: Kafka配置（可选，用于推送告警到Kafka）
        """
        self.logger = logging.getLogger(__name__)
        
        # 设备平台客户端和流管理器（延迟初始化）
        self.device_client = device_client
        self.stream_manager = stream_manager
        
        # 初始化Kafka推送器
        self.kafka_publisher = None
        if kafka_config and kafka_config.get('enabled', False):
            try:
                self.kafka_publisher = KafkaPublisher(
                    bootstrap_servers=kafka_config.get('bootstrap_servers', '127.0.0.1:9092'),
                    topic=kafka_config.get('topic', 'event-alarm'),
                    enabled=True
                )
                self.logger.info("Kafka推送器初始化成功")
            except Exception as e:
                self.logger.error(f"Kafka推送器初始化失败: {e}")
                self.kafka_publisher = None
        
        # 告警通知方式配置
        self.notification_method = config_manager.get('alarm.notification_method', 'both')
        self.logger.info(f"告警通知方式: {self.notification_method}")
        
        # 报警规则管理
        self.rules: Dict[str, AlarmRule] = {}
        self.rules_lock = threading.RLock()
        
        # 通知配置
        self.notification_configs: Dict[NotificationType, NotificationConfig] = {}
        self._load_notification_configs()
        
        # 报警状态跟踪
        self.alarm_states: Dict[str, Dict] = {}  # stream_id -> {rule_id: last_alarm_time}
        self.consecutive_counts: Dict[str, Dict] = {}  # stream_id -> {rule_id: count}
        
        # 通知队列和处理线程
        self.notification_queue = queue.Queue(maxsize=1000)
        self.notification_workers: List[threading.Thread] = []
        self.workers_running = False
        
        # 统计信息
        self.stats = {
            'total_alarms': 0,
            'alarms_by_type': {},
            'notifications_sent': 0,
            'notifications_failed': 0
        }
        
        # 启动通知处理线程
        self._start_notification_workers()
        
        # 加载默认规则
        self._load_default_rules()
        
        self.logger.info("报警系统初始化完成")
    
    def _load_notification_configs(self) -> None:
        """加载通知配置"""
        # 日志通知
        self.notification_configs[NotificationType.LOG] = NotificationConfig(
            type=NotificationType.LOG,
            enabled=True
        )
        
        # HTTP回调通知
        self.notification_configs[NotificationType.CALLBACK] = NotificationConfig(
            type=NotificationType.CALLBACK,
            enabled=True,
            config={
                'timeout': 5,
                'retry_count': 3,
                'retry_interval': 1
            }
        )
        
        # Webhook通知
        webhook_config = config_manager.get('notification.webhook', {})
        self.notification_configs[NotificationType.WEBHOOK] = NotificationConfig(
            type=NotificationType.WEBHOOK,
            enabled=webhook_config.get('enabled', False),
            config=webhook_config
        )
    
    def _load_default_rules(self) -> None:
        """加载默认报警规则"""
        alarm_config = config_manager.get_alarm_config()
        
        default_rule = AlarmRule(
            rule_id="default",
            name="默认报警规则",
            stream_ids=[],  # 适用于所有流
            class_names=[],  # 适用于所有类别
            min_confidence=alarm_config.get('min_confidence', 0.5),
            consecutive_frames=alarm_config.get('consecutive_frames', 3),
            cooldown_seconds=alarm_config.get('cooldown_seconds', 30),
            notifications=[NotificationType.LOG, NotificationType.CALLBACK]
        )
        
        self.add_rule(default_rule)
    
    def add_rule(self, rule: AlarmRule) -> bool:
        """
        添加报警规则
        
        Args:
            rule: 报警规则
            
        Returns:
            是否添加成功
        """
        with self.rules_lock:
            if rule.rule_id in self.rules:
                self.logger.warning(f"报警规则已存在: {rule.rule_id}")
                return False
            
            self.rules[rule.rule_id] = rule
            self.logger.info(f"添加报警规则: {rule.rule_id} - {rule.name}")
            return True
    
    def remove_rule(self, rule_id: str) -> bool:
        """
        删除报警规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            是否删除成功
        """
        with self.rules_lock:
            if rule_id not in self.rules:
                self.logger.warning(f"报警规则不存在: {rule_id}")
                return False
            
            del self.rules[rule_id]
            self.logger.info(f"删除报警规则: {rule_id}")
            return True
    
    def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新报警规则
        
        Args:
            rule_id: 规则ID
            updates: 更新内容
            
        Returns:
            是否更新成功
        """
        with self.rules_lock:
            if rule_id not in self.rules:
                self.logger.warning(f"报警规则不存在: {rule_id}")
                return False
            
            rule = self.rules[rule_id]
            for key, value in updates.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            
            self.logger.info(f"更新报警规则: {rule_id}")
            return True
    
    def get_rule(self, rule_id: str) -> Optional[AlarmRule]:
        """
        获取报警规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            报警规则或None
        """
        return self.rules.get(rule_id)
    
    def get_all_rules(self) -> List[AlarmRule]:
        """
        获取所有报警规则
        
        Returns:
            报警规则列表
        """
        return list(self.rules.values())
    
    def process_alarm_event(self, alarm_event: AlarmEvent) -> None:
        """
        处理报警事件
        
        Args:
            alarm_event: 报警事件
        """
        stream_id = alarm_event.stream_id
        current_time = time.time()
        
        # 初始化状态跟踪
        if stream_id not in self.alarm_states:
            self.alarm_states[stream_id] = {}
            self.consecutive_counts[stream_id] = {}
        
        # 检查每个规则
        with self.rules_lock:
            for rule in self.rules.values():
                if not rule.enabled:
                    continue
                
                # 检查规则是否适用
                if not self._is_rule_applicable(rule, alarm_event):
                    continue
                
                # 检查时间范围
                if not self._is_time_in_range(rule.time_range):
                    continue
                
                # 检查冷却时间
                if not self._check_cooldown(stream_id, rule.rule_id, current_time, rule.cooldown_seconds):
                    continue
                
                # 更新连续计数
                if rule.rule_id not in self.consecutive_counts[stream_id]:
                    self.consecutive_counts[stream_id][rule.rule_id] = 0
                
                self.consecutive_counts[stream_id][rule.rule_id] += 1
                
                # 检查是否达到触发条件
                if (alarm_event.confidence >= rule.min_confidence and
                    self.consecutive_counts[stream_id][rule.rule_id] >= rule.consecutive_frames):
                    
                    # 触发报警
                    self._trigger_alarm(rule, alarm_event)
                    
                    # 更新状态
                    self.alarm_states[stream_id][rule.rule_id] = current_time
                    self.consecutive_counts[stream_id][rule.rule_id] = 0
                    
                    # 更新统计
                    self._update_stats(alarm_event)
    
    def _is_rule_applicable(self, rule: AlarmRule, alarm_event: AlarmEvent) -> bool:
        """检查规则是否适用于当前报警事件"""
        # 检查流ID
        if rule.stream_ids and alarm_event.stream_id not in rule.stream_ids:
            return False
        
        # 检查类别名称
        if rule.class_names and alarm_event.class_name not in rule.class_names:
            return False
        
        return True
    
    def _is_time_in_range(self, time_range: Optional[Dict[str, str]]) -> bool:
        """检查当前时间是否在指定范围内"""
        if not time_range:
            return True
        
        try:
            from datetime import datetime, time as dt_time
            
            current_time = datetime.now().time()
            start_time = datetime.strptime(time_range['start'], '%H:%M').time()
            end_time = datetime.strptime(time_range['end'], '%H:%M').time()
            
            if start_time <= end_time:
                return start_time <= current_time <= end_time
            else:
                # 跨午夜的情况
                return current_time >= start_time or current_time <= end_time
        
        except Exception as e:
            self.logger.error(f"时间范围检查失败: {e}")
            return True
    
    def _check_cooldown(self, stream_id: str, rule_id: str, 
                       current_time: float, cooldown_seconds: int) -> bool:
        """检查冷却时间"""
        if stream_id not in self.alarm_states:
            return True
        
        last_alarm_time = self.alarm_states[stream_id].get(rule_id, 0)
        return (current_time - last_alarm_time) >= cooldown_seconds
    
    def _trigger_alarm(self, rule: AlarmRule, alarm_event: AlarmEvent) -> None:
        """触发报警"""
        self.logger.warning(
            f"触发报警: 规则={rule.name}, 流={alarm_event.stream_id}, "
            f"类别={alarm_event.class_name}, 置信度={alarm_event.confidence:.2f}"
        )
        
        # 创建通知任务
        for notification_type in rule.notifications:
            notification_task = {
                'type': notification_type,
                'rule': rule,
                'alarm_event': alarm_event,
                'timestamp': time.time()
            }
            
            try:
                self.notification_queue.put_nowait(notification_task)
            except queue.Full:
                self.logger.error("通知队列已满，丢弃通知任务")
                self.stats['notifications_failed'] += 1
    
    def _start_notification_workers(self) -> None:
        """启动通知处理工作线程"""
        self.workers_running = True
        
        # 创建多个工作线程处理通知
        worker_count = config_manager.get('performance.worker_threads', 4)
        for i in range(worker_count):
            worker = threading.Thread(
                target=self._notification_worker,
                name=f"AlarmWorker-{i}",
                daemon=True
            )
            worker.start()
            self.notification_workers.append(worker)
        
        self.logger.info(f"启动 {worker_count} 个通知处理线程")
    
    def _notification_worker(self) -> None:
        """通知处理工作线程"""
        while self.workers_running:
            try:
                # 获取通知任务
                task = self.notification_queue.get(timeout=1.0)
                
                # 处理通知
                self._process_notification(task)
                
                # 标记任务完成
                self.notification_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"通知处理线程异常: {e}")
    
    def _process_notification(self, task: Dict[str, Any]) -> None:
        """处理通知任务"""
        notification_type = task['type']
        rule = task['rule']
        alarm_event = task['alarm_event']
        
        try:
            config = self.notification_configs.get(notification_type)
            if not config or not config.enabled:
                return
            
            # 根据通知类型处理
            if notification_type == NotificationType.LOG:
                self._send_log_notification(rule, alarm_event)
            elif notification_type == NotificationType.CALLBACK:
                self._send_callback_notification(rule, alarm_event)
            elif notification_type == NotificationType.WEBHOOK:
                self._send_webhook_notification(rule, alarm_event, config.config)
            
            self.stats['notifications_sent'] += 1
            
        except Exception as e:
            self.logger.error(f"发送通知失败: {notification_type.value}, {e}")
            self.stats['notifications_failed'] += 1
    
    def _send_log_notification(self, rule: AlarmRule, alarm_event: AlarmEvent) -> None:
        """发送日志通知"""
        message = (
            f"[ALARM] 规则: {rule.name} | "
            f"流: {alarm_event.stream_id} | "
            f"类别: {alarm_event.class_name} | "
            f"置信度: {alarm_event.confidence:.2f} | "
            f"级别: {alarm_event.alarm_type} | "
            f"连续帧数: {alarm_event.consecutive_count}"
        )
        
        self.logger.warning(message)
    
    def _send_callback_notification(self, rule: AlarmRule, alarm_event: AlarmEvent) -> None:
        """
        发送告警通知（支持HTTP回调和Kafka推送）
        
        根据配置的 notification_method 决定发送方式：
        - http: 只通过HTTP回调发送到设备平台
        - kafka: 只通过Kafka推送
        - both: 同时使用HTTP和Kafka
        
        告警数据格式：
        {
            "deviceGbCode": "设备编号",
            "alarmType": "告警类型",
            "alarmLevel": "告警级别",
            "alarmTime": "告警时间",
            "pic": "告警图片URL",
            "record": "告警录像URL"
        }
        """
        try:
            # 从流ID获取设备编号和场景信息
            device_gb_code, scene_name = self._extract_device_info(alarm_event.stream_id)
            
            if not device_gb_code:
                self.logger.warning(f"无法从流ID {alarm_event.stream_id} 获取设备编号，跳过告警通知")
                return
            
            # 格式化告警时间
            from datetime import datetime
            alarm_time_str = datetime.fromtimestamp(alarm_event.timestamp).strftime('%Y-%m-%d %H:%M:%S')
            alarm_time_obj = datetime.fromtimestamp(alarm_event.timestamp)
            
            # 构建告警数据
            alarm_data = {
                'deviceGbCode': device_gb_code,
                'alarmType': alarm_event.class_name,  # 告警类型（检测到的类别）
                'alarmLevel': alarm_event.alarm_type,  # 告警级别（high/medium/low）
                'alarmTime': alarm_time_str,
                'pic': alarm_event.image_url if hasattr(alarm_event, 'image_url') and alarm_event.image_url else '',
                'record': alarm_event.record_url if hasattr(alarm_event, 'record_url') and alarm_event.record_url else ''
            }
            
            # 根据配置决定发送方式
            http_success = False
            kafka_success = False
            
            # 发送HTTP回调
            if self.notification_method in ['http', 'both']:
                http_success = self._send_http_callback(alarm_data)
            
            # 发送Kafka消息
            if self.notification_method in ['kafka', 'both']:
                kafka_success = self._send_kafka_message(
                    scene=scene_name or alarm_event.class_name,
                    device_gb_code=device_gb_code,
                    pic_url=alarm_data['pic'],
                    record_url=alarm_data['record'],
                    alarm_time=alarm_time_obj
                )
            
            # 记录发送结果
            if self.notification_method == 'http':
                status = "成功" if http_success else "失败"
                self.logger.info(f"告警HTTP回调{status}: {device_gb_code}, 类型: {alarm_event.class_name}")
            elif self.notification_method == 'kafka':
                status = "成功" if kafka_success else "失败"
                self.logger.info(f"告警Kafka推送{status}: {device_gb_code}, 类型: {alarm_event.class_name}")
            else:  # both
                self.logger.info(
                    f"告警通知发送完成: {device_gb_code}, 类型: {alarm_event.class_name} "
                    f"(HTTP: {'✓' if http_success else '✗'}, Kafka: {'✓' if kafka_success else '✗'})"
                )
                
        except Exception as e:
            self.logger.error(f"告警通知发送异常: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _extract_device_info(self, stream_id: str) -> tuple:
        """
        从流ID中提取设备编号和场景名称
        
        Args:
            stream_id: 流ID，格式: scene_场景名_设备编号
            
        Returns:
            (device_gb_code, scene_name)
        """
        device_gb_code = None
        scene_name = None
        
        # 尝试从流ID中提取设备编号
        if '_' in stream_id:
            parts = stream_id.split('_')
            if len(parts) >= 3:
                # scene_场景名_设备编号
                scene_name = parts[1]
                device_gb_code = parts[-1]
            elif len(parts) == 2:
                # scene_设备编号
                device_gb_code = parts[-1]
        
        # 如果无法从流ID提取，尝试从流管理器获取
        if not device_gb_code and self.stream_manager:
            stream_info = self.stream_manager.get_stream_info(stream_id)
            if stream_info:
                # 尝试从流配置中获取设备编号
                # 这里需要根据实际的数据结构来获取
                pass
        
        return device_gb_code, scene_name
    
    def _send_http_callback(self, alarm_data: dict) -> bool:
        """
        通过HTTP回调发送告警到设备平台
        
        Args:
            alarm_data: 告警数据
            
        Returns:
            是否发送成功
        """
        if not self.device_client:
            self.logger.warning("设备平台客户端未配置，跳过HTTP回调")
            return False
        
        try:
            success = self.device_client.send_alarm(alarm_data)
            return success
        except Exception as e:
            self.logger.error(f"HTTP回调发送异常: {e}")
            return False
    
    def _send_kafka_message(
        self,
        scene: str,
        device_gb_code: str,
        pic_url: str,
        record_url: str,
        alarm_time
    ) -> bool:
        """
        通过Kafka推送告警消息
        
        Args:
            scene: 场景名称
            device_gb_code: 设备编号
            pic_url: 图片URL
            record_url: 录像URL
            alarm_time: 告警时间
            
        Returns:
            是否推送成功
        """
        if not self.kafka_publisher:
            self.logger.warning("Kafka推送器未初始化，跳过Kafka推送")
            return False
        
        try:
            success = self.kafka_publisher.publish_alarm(
                scene=scene,
                device_gb_code=device_gb_code,
                pic_url=pic_url,
                record_url=record_url,
                alarm_time=alarm_time
            )
            return success
        except Exception as e:
            self.logger.error(f"Kafka推送异常: {e}")
            return False
    

    
    def _send_webhook_notification(self, rule: AlarmRule, alarm_event: AlarmEvent,
                                  webhook_config: Dict[str, Any]) -> None:
        """发送Webhook通知"""
        if not webhook_config.get('enabled', False):
            return
        
        try:
            payload = {
                'type': 'alarm',
                'rule': {
                    'id': rule.rule_id,
                    'name': rule.name
                },
                'event': {
                    'stream_id': alarm_event.stream_id,
                    'timestamp': alarm_event.timestamp,
                    'class_name': alarm_event.class_name,
                    'confidence': alarm_event.confidence,
                    'alarm_type': alarm_event.alarm_type,
                    'bbox': alarm_event.bbox,
                    'consecutive_count': alarm_event.consecutive_count
                }
            }
            
            headers = {'Content-Type': 'application/json'}
            headers.update(webhook_config.get('headers', {}))
            
            response = requests.post(
                webhook_config['url'],
                json=payload,
                headers=headers,
                timeout=webhook_config.get('timeout', 10)
            )
            
            if response.status_code == 200:
                self.logger.info(f"Webhook通知发送成功: {alarm_event.stream_id}")
            else:
                self.logger.warning(
                    f"Webhook通知响应异常: {response.status_code}, {response.text}"
                )
            
        except Exception as e:
            self.logger.error(f"Webhook通知发送失败: {e}")
            raise
    
    def _update_stats(self, alarm_event: AlarmEvent) -> None:
        """更新统计信息"""
        self.stats['total_alarms'] += 1
        
        alarm_type = alarm_event.alarm_type
        if alarm_type not in self.stats['alarms_by_type']:
            self.stats['alarms_by_type'][alarm_type] = 0
        self.stats['alarms_by_type'][alarm_type] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取报警统计信息"""
        stats = self.stats.copy()
        stats['active_rules'] = len([r for r in self.rules.values() if r.enabled])
        stats['total_rules'] = len(self.rules)
        stats['queue_size'] = self.notification_queue.qsize()
        return stats
    
    def reset_consecutive_counts(self, stream_id: str) -> None:
        """重置指定流的连续计数"""
        if stream_id in self.consecutive_counts:
            self.consecutive_counts[stream_id] = {}
    
    def configure_notification(self, notification_type: NotificationType,
                              config: Dict[str, Any]) -> bool:
        """
        配置通知方式
        
        Args:
            notification_type: 通知类型
            config: 配置参数
            
        Returns:
            是否配置成功
        """
        try:
            if notification_type not in self.notification_configs:
                self.notification_configs[notification_type] = NotificationConfig(
                    type=notification_type
                )
            
            self.notification_configs[notification_type].config.update(config)
            self.notification_configs[notification_type].enabled = config.get('enabled', True)
            
            self.logger.info(f"通知配置更新成功: {notification_type.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"通知配置更新失败: {e}")
            return False
    
    def shutdown(self) -> None:
        """关闭报警系统"""
        self.logger.info("正在关闭报警系统...")
        
        # 停止工作线程
        self.workers_running = False
        
        # 等待队列处理完成
        self.notification_queue.join()
        
        # 等待工作线程结束
        for worker in self.notification_workers:
            if worker.is_alive():
                worker.join(timeout=2.0)
        
        self.logger.info("报警系统已关闭")
