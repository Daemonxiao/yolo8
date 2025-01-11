from ultralytics import YOLO
import os
import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def check_dataset_path():
    """检查数据集路径是否存在"""
    dataset_path = os.path.join('data', 'fire_dataset.yaml')
    if not os.path.exists(dataset_path):
        logging.error(f"数据集配置文件不存在: {dataset_path}")
        return False
    return True

def train_fire_detector():
    try:
        logging.info("开始加载预训练模型...")
        
        # 检查数据集配置
        if not check_dataset_path():
            return
        
        # 加载预训练模型
        model = YOLO('yolov8n.pt')
        logging.info("预训练模型加载成功")
        
        logging.info("开始训练模型...")
        # 训练模型
        results = model.train(
            data='data/fire_dataset.yaml',
            epochs=100,
            imgsz=640,
            batch=16,
            name='fire_detection',
            device='cpu',
            verbose=True  # 启用详细输出
        )
        
        logging.info("训练完成，开始验证...")
        # 验证模型
        results = model.val()
        
        logging.info("模型训练和验证完成")
        
    except Exception as e:
        logging.error(f"训练过程中发生错误: {str(e)}")
        raise

if __name__ == "__main__":
    train_fire_detector()
