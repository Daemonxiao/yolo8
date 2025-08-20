import cv2
import torch
from ultralytics import YOLO
from pathlib import Path
import argparse
import time
from ultralytics.nn.tasks import DetectionModel
from ultralytics.nn.modules.conv import Conv, Concat
from ultralytics.nn.modules.block import C2f, Bottleneck, SPPF, DFL
from ultralytics.nn.modules.head import Detect
from ultralytics.utils import IterableSimpleNamespace
from torch.nn import Sequential
from torch.nn.modules.conv import Conv2d
from torch.nn.modules.batchnorm import BatchNorm2d
from torch.nn.modules.activation import SiLU
from torch.nn.modules.container import ModuleList
from torch.nn.modules.pooling import MaxPool2d
from torch.nn.modules.upsampling import Upsample

# 添加安全全局变量以支持PyTorch 2.6+
torch.serialization.add_safe_globals([
    DetectionModel,
    Sequential,
    Conv,
    Conv2d,
    BatchNorm2d,
    SiLU,
    C2f,
    ModuleList,
    Bottleneck,
    SPPF,
    MaxPool2d,
    Upsample,
    Concat,
    Detect,
    DFL,
    IterableSimpleNamespace
])

# 保存原始的torch.load函数并创建安全版本
_original_torch_load = torch.load


def safe_torch_load(*args, **kwargs):
    """安全的torch.load函数，强制设置weights_only=False"""
    kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)


# 替换torch.load
torch.load = safe_torch_load


def detect_video(model_path, video_path=0, conf=0.25):
    # 加载训练好的模型
    model = YOLO(model_path)

    print(f"尝试打开视频源: {video_path}")

    # 打开视频文件或摄像头
    cap = cv2.VideoCapture(video_path)  # video_path=0 表示使用默认摄像头

    # 检查视频源是否成功打开
    if not cap.isOpened():
        if video_path == 0:
            print("❌ 无法打开默认摄像头")
            print("可能的原因:")
            print("1. 没有连接摄像头")
            print("2. 摄像头被其他程序占用")
            print("3. 摄像头权限问题")
            print("\n建议使用图片检测:")
            print("python scripts/detect.py --model <模型路径> --image <图片路径>")
        else:
            print(f"❌ 无法打开视频文件: {video_path}")
            print("请检查视频文件路径是否正确")
        return False

    print("✅ 视频源打开成功，按 'q' 键退出")

    frame_count = 0
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            print(f"视频播放完毕或读取失败 (处理了 {frame_count} 帧)")
            break

        # 运行推理
        results = model(frame, conf=conf)

        # 可视化结果
        annotated_frame = results[0].plot()

        # 显示结果
        cv2.imshow("Construction Waste Detection", annotated_frame)

        frame_count += 1
        if frame_count % 30 == 0:  # 每30帧显示一次进度
            print(f"已处理 {frame_count} 帧")

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("用户退出")
            break

    cap.release()
    cv2.destroyAllWindows()
    print(f"视频检测完成，总共处理 {frame_count} 帧")
    return True


def detect_image(model_path, image_path, conf=0.25):
    # 加载训练好的模型
    model = YOLO(model_path)

    # 读取图片
    image = cv2.imread(image_path)
    if image is None:
        print(f"错误：无法读取图片 {image_path}")
        return

    # 运行推理
    results = model(image, conf=conf)

    # 可视化结果
    annotated_image = results[0].plot()

    # 显示结果
    cv2.imshow("Fire and Smoke Detection", annotated_image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def run_stress_test(model_path, image_path=None, video_path=0, conf=0.25, num_runs=1):
    total_time = 0  # 总执行时间
    for i in range(num_runs):
        print(f"第 {i + 1} 轮测试开始...")

        # 记录开始时间
        start_time = time.time()

        if image_path:
            # 图片检测
            detect_image(model_path, image_path, conf)
        else:
            # 视频检测（使用摄像头或视频文件）
            success = detect_video(model_path, video_path, conf)
            if not success:
                print(f"第 {i + 1} 轮测试失败，跳过")
                continue

        # 记录结束时间
        end_time = time.time()

        # 计算本轮执行时间
        execution_time = end_time - start_time
        total_time += execution_time
        print(f"第 {i + 1} 轮测试完成，耗时: {execution_time:.2f} 秒")

    # 输出压测结果
    print(f"\n压测完成，总执行时间: {total_time:.2f} 秒")
    if num_runs > 1:
        print(f"平均每轮执行时间: {total_time / num_runs:.2f} 秒")


def main():
    parser = argparse.ArgumentParser(description='火灾和烟雾检测压测')
    parser.add_argument('--model', type=str,
                        default='runs/detect/fire_smoke_detector14/weights/best.pt',
                        help='模型路径')
    parser.add_argument('--image', type=str, help='要检测的图片路径')
    parser.add_argument('--video', type=str, help='要检测的视频路径')
    parser.add_argument('--conf', type=float, default=0.25, help='置信度阈值')
    parser.add_argument('--runs', type=int, default=1, help='压测轮次')
    args = parser.parse_args()

    # 运行压测
    run_stress_test(args.model, args.image, args.video, args.conf, args.runs)


if __name__ == '__main__':
    main()