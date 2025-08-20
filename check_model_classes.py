#!/usr/bin/env python3
"""
检查YOLO模型的类别信息
"""

import sys
import os
from ultralytics import YOLO

def check_model_classes():
    """检查模型的类别信息"""
    
    # 检查模型文件
    model_paths = [
        "constuction_waste/best.pt",  # 你的自定义模型
        "yolov8n.pt"                  # 默认模型
    ]
    
    for model_path in model_paths:
        print(f"\n{'='*60}")
        print(f"🔍 检查模型: {model_path}")
        print(f"{'='*60}")
        
        if not os.path.exists(model_path):
            print(f"❌ 模型文件不存在: {model_path}")
            continue
        
        try:
            # 临时设置torch加载参数以兼容新版本PyTorch
            import torch
            original_load = torch.load
            def safe_load(*args, **kwargs):
                kwargs['weights_only'] = False
                return original_load(*args, **kwargs)
            torch.load = safe_load
            
            # 加载模型
            model = YOLO(model_path)
            
            # 恢复原始torch.load
            torch.load = original_load
            
            # 获取类别信息
            class_names = model.names
            
            print(f"📊 模型信息:")
            print(f"  - 类别总数: {len(class_names)}")
            print(f"  - 模型类型: {type(model.model)}")
            
            print(f"\n📋 类别映射 (class_id -> class_name):")
            print("-" * 50)
            for class_id, class_name in class_names.items():
                print(f"  {class_id:2d}: {class_name}")
            
            # 检查模型元信息
            if hasattr(model.model, 'yaml'):
                yaml_info = model.model.yaml
                if 'names' in yaml_info:
                    print(f"\n🏷️  YAML中的类别信息:")
                    print(f"  {yaml_info['names']}")
            
            # 如果是自定义模型，显示训练信息
            if "best.pt" in model_path:
                print(f"\n🎯 自定义模型特征:")
                print(f"  - 这是一个训练好的模型")
                print(f"  - 类别名称来自训练时的数据集标签")
                print(f"  - 通常用于特定检测任务")
            
        except Exception as e:
            print(f"❌ 加载模型失败: {e}")

def show_class_mapping_process():
    """展示类别映射的工作原理"""
    print(f"\n{'='*60}")
    print(f"🧠 YOLO类别映射工作原理")
    print(f"{'='*60}")
    
    print("""
📝 工作流程:

1. 模型训练时:
   - 数据集包含标注文件 (如 classes.txt 或 YAML配置)
   - 每个类别分配一个数字ID (0, 1, 2, ...)
   - 类别名称与ID的映射保存在模型中

2. 模型推理时:
   - YOLO输出: 检测框 + 类别ID (如: cls=2)
   - 通过 model.names[int(cls)] 获取类别名称
   - 如: model.names[2] = "construction_waste"

3. 在代码中的使用:
   ```python
   results = model(frame)
   classes = result.boxes.cls.cpu().numpy()  # [0, 2, 1, ...]
   
   for cls in classes:
       class_id = int(cls)           # 2
       class_name = model.names[cls] # "construction_waste"
   ```

🔍 类别来源:
   - COCO模型: 80个预定义类别 (person, car, dog, ...)
   - 自定义模型: 训练时定义的类别 (construction_waste, ...)
   - YOLOv8n.pt: 使用COCO数据集的标准80类
""")

if __name__ == "__main__":
    check_model_classes()
    show_class_mapping_process()
