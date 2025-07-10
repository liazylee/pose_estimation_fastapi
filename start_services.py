#!/usr/bin/env python3
"""
AI服务启动脚本
支持启动单个服务或所有服务
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

SERVICES = {
    "yolox": {
        "path": "apps/yolox_service", 
        "port": 8001,
        "description": "YOLOX物体检测服务"
    },
    "rtmpose": {
        "path": "apps/rtmpose_service",
        "port": 8002, 
        "description": "RTMPose姿态估计服务"
    },
    "annotation": {
        "path": "apps/annotation_service",
        "port": 8003,
        "description": "视频标注服务"
    }
}

def start_service(service_name, host="0.0.0.0", reload=False):
    """启动单个服务"""
    if service_name not in SERVICES:
        print(f"错误: 未知服务 '{service_name}'")
        print(f"可用服务: {', '.join(SERVICES.keys())}")
        return False
    
    service = SERVICES[service_name]
    print(f"启动 {service['description']} (端口 {service['port']})...")
    
    cmd = [
        sys.executable, "main.py",
        "--host", host,
        "--port", str(service['port'])
    ]
    
    if reload:
        cmd.append("--reload")
    
    try:
        # 改变到服务目录
        cwd = Path(service['path'])
        if not cwd.exists():
            print(f"错误: 服务目录 {service['path']} 不存在")
            return False
            
        subprocess.run(cmd, cwd=cwd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"启动服务失败: {e}")
        return False
    except KeyboardInterrupt:
        print(f"\n{service['description']} 被用户中断")
        return True

def start_all_services(host="0.0.0.0", reload=False):
    """启动所有服务（并发）"""
    print("启动所有AI服务...")
    
    processes = []
    for service_name, service in SERVICES.items():
        print(f"启动 {service['description']} (端口 {service['port']})...")
        
        cmd = [
            sys.executable, "main.py",
            "--host", host,
            "--port", str(service['port'])
        ]
        
        if reload:
            cmd.append("--reload")
        
        try:
            cwd = Path(service['path'])
            if not cwd.exists():
                print(f"错误: 服务目录 {service['path']} 不存在")
                continue
                
            proc = subprocess.Popen(cmd, cwd=cwd)
            processes.append((service_name, proc))
            time.sleep(1)  # 错开启动时间
        except Exception as e:
            print(f"启动 {service_name} 失败: {e}")
    
    if not processes:
        print("没有成功启动任何服务")
        return
    
    print(f"\n成功启动 {len(processes)} 个服务:")
    for service_name, proc in processes:
        service = SERVICES[service_name]
        print(f"  - {service['description']}: http://{host}:{service['port']}")
    
    print("\n按 Ctrl+C 停止所有服务")
    
    try:
        # 等待所有进程
        for _, proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止所有服务...")
        for service_name, proc in processes:
            print(f"停止 {service_name}...")
            proc.terminate()
        
        # 等待进程结束
        for _, proc in processes:
            proc.wait()
        print("所有服务已停止")

def main():
    parser = argparse.ArgumentParser(description="AI服务启动脚本")
    parser.add_argument(
        "service", 
        nargs="?", 
        choices=list(SERVICES.keys()) + ["all"],
        default="all",
        help="要启动的服务 (默认: all)"
    )
    parser.add_argument(
        "--host", 
        default="0.0.0.0", 
        help="绑定主机 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--reload", 
        action="store_true", 
        help="启用自动重载"
    )
    parser.add_argument(
        "--list", 
        action="store_true", 
        help="列出所有可用服务"
    )
    
    args = parser.parse_args()
    
    if args.list:
        print("可用的AI服务:")
        for name, service in SERVICES.items():
            print(f"  {name:12} - {service['description']} (端口 {service['port']})")
        return
    
    if args.service == "all":
        start_all_services(args.host, args.reload)
    else:
        start_service(args.service, args.host, args.reload)

if __name__ == "__main__":
    main() 