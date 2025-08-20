#!/usr/bin/env python3
"""
检测结果查看工具
用于浏览和分析保存的检测结果
"""

import os
import json
import sys
from datetime import datetime
from typing import Dict, List, Any
import argparse


class ResultsViewer:
    """检测结果查看器"""
    
    def __init__(self, results_path: str = "results"):
        """
        初始化结果查看器
        
        Args:
            results_path: 结果保存路径
        """
        self.results_path = results_path
        
        if not os.path.exists(results_path):
            print(f"❌ 结果目录不存在: {results_path}")
            sys.exit(1)
    
    def list_dates(self) -> List[str]:
        """列出所有可用的日期"""
        dates = []
        
        for item in os.listdir(self.results_path):
            item_path = os.path.join(self.results_path, item)
            if os.path.isdir(item_path) and item.count('-') == 2:  # YYYY-MM-DD格式
                dates.append(item)
        
        return sorted(dates, reverse=True)
    
    def list_streams(self, date: str) -> List[str]:
        """列出指定日期的所有流"""
        date_path = os.path.join(self.results_path, date)
        
        if not os.path.exists(date_path):
            return []
        
        streams = []
        for item in os.listdir(date_path):
            item_path = os.path.join(date_path, item)
            if os.path.isdir(item_path):
                streams.append(item)
        
        return sorted(streams)
    
    def list_detections(self, date: str, stream_id: str) -> List[Dict[str, Any]]:
        """列出指定日期和流的所有检测结果"""
        stream_path = os.path.join(self.results_path, date, stream_id)
        
        if not os.path.exists(stream_path):
            return []
        
        detections = []
        for item in os.listdir(stream_path):
            item_path = os.path.join(stream_path, item)
            if os.path.isdir(item_path):
                info_file = os.path.join(item_path, 'detection_info.json')
                if os.path.exists(info_file):
                    try:
                        with open(info_file, 'r', encoding='utf-8') as f:
                            detection_info = json.load(f)
                        
                        detections.append({
                            'folder': item,
                            'path': item_path,
                            'info': detection_info,
                            'timestamp': detection_info['basic_info']['timestamp'],
                            'object_count': detection_info['detection_results']['total_objects'],
                            'has_alarm': detection_info['alarm_info']['has_alarm'],
                            'alarm_level': detection_info['alarm_info']['alarm_level']
                        })
                    except Exception as e:
                        print(f"⚠️ 读取检测信息失败: {info_file}, {e}")
        
        # 按时间戳排序
        return sorted(detections, key=lambda x: x['timestamp'], reverse=True)
    
    def show_summary(self) -> None:
        """显示结果总览"""
        print("📊 检测结果总览")
        print("=" * 50)
        
        dates = self.list_dates()
        if not dates:
            print("❌ 没有找到检测结果")
            return
        
        total_detections = 0
        total_alarms = 0
        
        for date in dates:
            streams = self.list_streams(date)
            date_detections = 0
            date_alarms = 0
            
            for stream_id in streams:
                detections = self.list_detections(date, stream_id)
                date_detections += len(detections)
                date_alarms += sum(1 for d in detections if d['has_alarm'])
            
            total_detections += date_detections
            total_alarms += date_alarms
            
            if date_detections > 0:
                print(f"📅 {date}: {date_detections} 个检测结果, {date_alarms} 个报警")
        
        print("-" * 50)
        print(f"📈 总计: {total_detections} 个检测结果, {total_alarms} 个报警")
        print(f"📁 涉及日期: {len(dates)} 天")
    
    def show_date_details(self, date: str) -> None:
        """显示指定日期的详细信息"""
        print(f"📅 {date} 详细信息")
        print("=" * 50)
        
        streams = self.list_streams(date)
        if not streams:
            print("❌ 该日期没有检测结果")
            return
        
        for stream_id in streams:
            detections = self.list_detections(date, stream_id)
            alarms = sum(1 for d in detections if d['has_alarm'])
            
            print(f"\n🎥 流ID: {stream_id}")
            print(f"   检测结果: {len(detections)} 个")
            print(f"   报警事件: {alarms} 个")
            
            if detections:
                latest = detections[0]
                earliest = detections[-1]
                print(f"   时间范围: {earliest['timestamp']} ~ {latest['timestamp']}")
                
                # 统计检测的目标类型
                class_stats = {}
                for detection in detections:
                    for obj in detection['info']['detection_results']['objects']:
                        class_name = obj['class_name']
                        class_stats[class_name] = class_stats.get(class_name, 0) + 1
                
                if class_stats:
                    print("   目标统计:", end="")
                    for class_name, count in class_stats.items():
                        print(f" {class_name}({count})", end="")
                    print()
    
    def show_detection_details(self, date: str, stream_id: str, detection_folder: str) -> None:
        """显示具体检测结果的详细信息"""
        detection_path = os.path.join(self.results_path, date, stream_id, detection_folder)
        info_file = os.path.join(detection_path, 'detection_info.json')
        
        if not os.path.exists(info_file):
            print(f"❌ 检测信息文件不存在: {info_file}")
            return
        
        try:
            with open(info_file, 'r', encoding='utf-8') as f:
                info = json.load(f)
            
            print(f"🔍 检测结果详情")
            print("=" * 50)
            
            # 基本信息
            basic = info['basic_info']
            print(f"⏰ 时间: {basic['timestamp']}")
            print(f"🎥 流ID: {basic['stream_id']}")
            print(f"🎬 帧号: {basic['frame_id']}")
            print(f"⚡ 处理时间: {basic['processing_time']:.3f}秒")
            print(f"📹 视频源: {basic['video_source']}")
            
            # 检测结果
            detection_results = info['detection_results']
            print(f"\n🎯 检测结果: 共 {detection_results['total_objects']} 个目标")
            
            for obj in detection_results['objects']:
                print(f"  #{obj['id']} {obj['class_name']}")
                print(f"     置信度: {obj['confidence']:.3f}")
                print(f"     位置: ({obj['bbox']['x1']:.0f}, {obj['bbox']['y1']:.0f}) - "
                      f"({obj['bbox']['x2']:.0f}, {obj['bbox']['y2']:.0f})")
                print(f"     尺寸: {obj['bbox']['width']:.0f} x {obj['bbox']['height']:.0f}")
                print(f"     面积: {obj['area']:.0f}")
            
            # 报警信息
            alarm_info = info['alarm_info']
            if alarm_info['has_alarm']:
                print(f"\n🚨 报警信息: {alarm_info['alarm_level']} 级")
                for alarm_obj in alarm_info['alarm_objects']:
                    print(f"  报警目标: {alarm_obj['class_name']} (置信度: {alarm_obj['confidence']:.3f})")
            else:
                print(f"\n✅ 无报警")
            
            # 文件信息
            print(f"\n📁 保存文件:")
            files = os.listdir(detection_path)
            for file in sorted(files):
                file_path = os.path.join(detection_path, file)
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    print(f"  📄 {file} ({size:,} bytes)")
                elif os.path.isdir(file_path):
                    sub_files = len(os.listdir(file_path))
                    print(f"  📁 {file}/ ({sub_files} 个文件)")
            
        except Exception as e:
            print(f"❌ 读取检测信息失败: {e}")
    
    def search_by_class(self, class_name: str, date: str = None) -> List[Dict]:
        """按目标类别搜索检测结果"""
        print(f"🔍 搜索目标类别: {class_name}")
        if date:
            print(f"📅 限定日期: {date}")
        print("=" * 50)
        
        results = []
        dates_to_search = [date] if date else self.list_dates()
        
        for search_date in dates_to_search:
            streams = self.list_streams(search_date)
            
            for stream_id in streams:
                detections = self.list_detections(search_date, stream_id)
                
                for detection in detections:
                    # 检查是否包含指定类别
                    for obj in detection['info']['detection_results']['objects']:
                        if obj['class_name'].lower() == class_name.lower():
                            results.append({
                                'date': search_date,
                                'stream_id': stream_id,
                                'folder': detection['folder'],
                                'timestamp': detection['timestamp'],
                                'confidence': obj['confidence'],
                                'bbox': obj['bbox']
                            })
                            break
        
        if results:
            print(f"✅ 找到 {len(results)} 个匹配结果:")
            
            # 按时间排序
            results.sort(key=lambda x: x['timestamp'], reverse=True)
            
            for result in results[:20]:  # 只显示前20个
                print(f"  📅 {result['date']} {result['timestamp']}")
                print(f"     流: {result['stream_id']}, 置信度: {result['confidence']:.3f}")
                print(f"     路径: {result['date']}/{result['stream_id']}/{result['folder']}")
                print()
            
            if len(results) > 20:
                print(f"... 还有 {len(results) - 20} 个结果未显示")
        else:
            print("❌ 没有找到匹配的结果")
    
    def cleanup_old_results(self, days: int = 30) -> None:
        """清理旧的检测结果"""
        print(f"🧹 清理 {days} 天前的检测结果")
        print("=" * 50)
        
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days)
        dates = self.list_dates()
        
        removed_count = 0
        
        for date_str in dates:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if date_obj < cutoff_date:
                    date_path = os.path.join(self.results_path, date_str)
                    
                    # 计算要删除的文件数
                    total_files = 0
                    for root, dirs, files in os.walk(date_path):
                        total_files += len(files)
                    
                    import shutil
                    shutil.rmtree(date_path)
                    removed_count += total_files
                    
                    print(f"🗑️ 删除日期: {date_str} ({total_files} 个文件)")
                    
            except ValueError:
                print(f"⚠️ 跳过无效日期格式: {date_str}")
        
        print(f"✅ 清理完成，共删除 {removed_count} 个文件")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='检测结果查看工具')
    parser.add_argument('--results-path', default='results', help='结果保存路径')
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 总览命令
    subparsers.add_parser('summary', help='显示结果总览')
    
    # 日期详情命令
    date_parser = subparsers.add_parser('date', help='显示指定日期的详情')
    date_parser.add_argument('date', help='日期 (YYYY-MM-DD)')
    
    # 检测详情命令
    detail_parser = subparsers.add_parser('detail', help='显示具体检测结果')
    detail_parser.add_argument('date', help='日期 (YYYY-MM-DD)')
    detail_parser.add_argument('stream_id', help='流ID')
    detail_parser.add_argument('folder', help='检测结果文件夹名')
    
    # 搜索命令
    search_parser = subparsers.add_parser('search', help='按类别搜索')
    search_parser.add_argument('class_name', help='目标类别名称')
    search_parser.add_argument('--date', help='限定搜索日期')
    
    # 清理命令
    cleanup_parser = subparsers.add_parser('cleanup', help='清理旧结果')
    cleanup_parser.add_argument('--days', type=int, default=30, help='保留天数')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    viewer = ResultsViewer(args.results_path)
    
    if args.command == 'summary':
        viewer.show_summary()
    
    elif args.command == 'date':
        viewer.show_date_details(args.date)
    
    elif args.command == 'detail':
        viewer.show_detection_details(args.date, args.stream_id, args.folder)
    
    elif args.command == 'search':
        viewer.search_by_class(args.class_name, args.date)
    
    elif args.command == 'cleanup':
        viewer.cleanup_old_results(args.days)


if __name__ == "__main__":
    main()
