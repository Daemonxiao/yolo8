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
    
    def __init__(self):
        """初始化报警系统"""
        self.logger = logging.getLogger(__name__)
        
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
        """发送HTTP回调通知"""
        # 这里需要从流配置中获取回调URL
        # 实际实现中需要与StreamManager协调
        pass
    

    
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
