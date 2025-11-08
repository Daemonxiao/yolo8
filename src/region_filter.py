"""
区域检测过滤器
用于过滤检测区域外的目标
"""

import logging
from typing import List, Tuple
import cv2
import numpy as np


class RegionFilter:
    """区域检测过滤器"""
    
    def __init__(self):
        """初始化区域过滤器"""
        self.logger = logging.getLogger(__name__)
    
    def parse_region_string(self, region_str: str) -> List[List[Tuple[float, float]]]:
        """
        解析区域字符串
        
        格式示例:
        - 单区域: "(100,100),(500,100),(500,400),(100,400)"
        - 多区域: "(100,100),(200,100),(200,200),(100,200);(300,300),(400,300),(400,400),(300,400)"
        
        Args:
            region_str: 区域字符串
            
        Returns:
            区域列表，每个区域是一个点列表 [[(x1,y1), (x2,y2), ...], ...]
        """
        try:
            if not region_str or region_str.strip() == '':
                return []
            
            regions = []
            
            # 多区域用分号分隔
            region_parts = region_str.split(';')
            
            for part in region_parts:
                part = part.strip()
                if not part:
                    continue
                
                # 解析单个区域的点
                points = []
                # 匹配 (x,y) 格式
                point_matches = part.replace('(', '').replace(')', ',').split(',')
                point_matches = [p.strip() for p in point_matches if p.strip()]
                
                # 每两个数值组成一个点
                for i in range(0, len(point_matches), 2):
                    if i + 1 < len(point_matches):
                        try:
                            x = float(point_matches[i])
                            y = float(point_matches[i + 1])
                            points.append((x, y))
                        except ValueError:
                            continue
                
                if len(points) >= 3:  # 至少3个点才能构成区域
                    regions.append(points)
                else:
                    self.logger.warning(f"区域点数不足3个，跳过: {part}")
            
            if regions:
                self.logger.info(f"解析到 {len(regions)} 个检测区域")
            
            return regions
            
        except Exception as e:
            self.logger.error(f"解析区域字符串失败: {e}")
            return []
    
    def point_in_polygon(self, point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
        """
        判断点是否在多边形内（射线法）
        
        Args:
            point: 点坐标 (x, y)
            polygon: 多边形顶点列表 [(x1,y1), (x2,y2), ...]
            
        Returns:
            点是否在多边形内
        """
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def is_detection_in_regions(
        self,
        detection: dict,
        regions: List[List[Tuple[float, float]]]
    ) -> bool:
        """
        判断检测目标是否在指定区域内
        
        Args:
            detection: 检测结果字典，包含 'bbox' 或 'center' 字段
            regions: 区域列表
            
        Returns:
            目标是否在区域内
        """
        if not regions:
            # 没有设置区域，则不过滤
            return True
        
        # 获取目标中心点
        if 'center' in detection:
            center = tuple(detection['center'])
        elif 'bbox' in detection:
            bbox = detection['bbox']
            center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        else:
            self.logger.warning("检测结果缺少center或bbox字段，无法判断区域")
            return True
        
        # 判断中心点是否在任一区域内
        for region in regions:
            if self.point_in_polygon(center, region):
                return True
        
        return False
    
    def filter_detections(
        self,
        detections: List[dict],
        region_str: str
    ) -> List[dict]:
        """
        过滤检测结果，只保留区域内的目标
        
        Args:
            detections: 检测结果列表
            region_str: 区域字符串
            
        Returns:
            过滤后的检测结果列表
        """
        if not region_str or region_str.strip() == '':
            # 没有设置区域，返回所有检测结果
            return detections
        
        # 解析区域
        regions = self.parse_region_string(region_str)
        
        if not regions:
            return detections
        
        # 过滤检测结果
        filtered = []
        for detection in detections:
            if self.is_detection_in_regions(detection, regions):
                filtered.append(detection)
        
        if len(filtered) < len(detections):
            self.logger.debug(
                f"区域过滤: 原始{len(detections)}个目标，过滤后{len(filtered)}个"
            )
        
        return filtered
    
    def draw_regions_on_image(
        self,
        image: np.ndarray,
        region_str: str,
        color: Tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2
    ) -> np.ndarray:
        """
        在图像上绘制检测区域（用于调试）
        
        Args:
            image: 输入图像
            region_str: 区域字符串
            color: 绘制颜色 (B, G, R)
            thickness: 线条粗细
            
        Returns:
            绘制了区域的图像
        """
        regions = self.parse_region_string(region_str)
        
        if not regions:
            return image
        
        result = image.copy()
        
        for region in regions:
            # 转换为OpenCV格式的点
            pts = np.array(region, np.int32)
            pts = pts.reshape((-1, 1, 2))
            
            # 绘制多边形
            cv2.polylines(result, [pts], True, color, thickness)
        
        return result

