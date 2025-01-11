import cv2
from ultralytics import YOLO
import numpy as np
import time
import os

class FireDetector:
    def __init__(self, model_path, conf_threshold=0.5):
        """
        初始化火情检测器
        model_path: 模型路径
        conf_threshold: 置信度阈值
        """
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        
    def draw_detection(self, frame, results):
        """
        在图像上绘制检测结果
        """
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # 获取边界框坐标
                x1, y1, x2, y2 = box.xyxy[0]
                x1, y1, x2, y2 = int(x1), int(y1), int(y2), int(y2)
                
                # 获取置信度
                conf = float(box.conf)
                
                if conf > self.conf_threshold:
                    # 绘制边界框
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    
                    # 添加标签
                    label = f'Fire: {conf:.2f}'
                    cv2.putText(frame, label, (x1, y1 - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        return frame
    
    def process_video(self, video_source=0, target_fps=2):
        """
        处理视频流
        video_source: 可以是摄像头索引或视频文件路径
        target_fps: 目标帧率
        """
        cap = cv2.VideoCapture(video_source)
        
        # 计算每帧之间的延迟时间（毫秒）
        delay = 1.0 / target_fps

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # 开始计时
            start_time = time.time()
            
            # 进行检测
            results = self.model(frame)
            
            # 计算FPS
            fps = 1.0 / (time.time() - start_time)
            
            # 绘制检测结果
            frame = self.draw_detection(frame, results)
            
            # 显示FPS
            cv2.putText(frame, f'FPS: {fps:.2f}', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # 显示结果
            cv2.imshow('Fire Detection', frame)
            
            # 按'q'退出
            if cv2.waitKey(int(delay * 1000)) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()

    def process_image(self, image_path):
        """
        处理单张图片
        image_path: 图片文件路径
        """
        # 读取图片
        frame = cv2.imread(image_path)
        if frame is None:
            print(f"无法读取图片: {image_path}")
            return
        
        # 进行检测
        results = self.model(frame)
        
        # 绘制检测结果
        frame = self.draw_detection(frame, results)
        
        # 显示结果
        cv2.imshow('Fire Detection', frame)
        cv2.waitKey(0)  # 等待按键
        cv2.destroyAllWindows()

def main():
    # 创建检测器实例
    detector = FireDetector(
        model_path='/Users/wq/PyProjects/YOLOv8-Fire-and-Smoke-Detection/runs/detect/train/weights/best.pt',
        conf_threshold=0.8
    )
    
    # 处理视频
    detector.process_video(0)  # 使用摄像头
    
    # 处理单张图片
    #image_path = '/Users/wq/Desktop/3000_004.jpg'  # 替换为你的图片路径
    #detector.process_image(image_path)

if __name__ == "__main__":
    main()
