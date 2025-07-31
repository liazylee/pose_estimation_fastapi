#!/usr/bin/env python3
"""
AI startup script for launching multiple AI services.
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
        "description": "YOLOX detection service"
    },
    "rtmpose": {
        "path": "apps/rtmpose_service",
        "port": 8002,
        "description": "RTMPose service"
    },
    "bytetrack": {
        "path": "apps/bytetrack_service",
        "port": 8003,
        "description": "ByteTrack tracking service"
    },
    "annotation": {
        "path": "apps/annotation_service",
        "port": 8004,
        "description": "annotation service"
    },
    "backend": {
        "path": "apps/fastapi_backend",
        "port": 8000,
        "description": "backend service"
    }
}


def start_service(service_name, host="0.0.0.0", reload=False):
    if service_name not in SERVICES:
        print(f"error:  unknow error '{service_name}'")
        print(f"valid services are: {', '.join(SERVICES.keys())}")
        return False

    service = SERVICES[service_name]
    print(f"launching {service['description']} on port {service['port']}...")

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
            print(f"error: directory '{service['path']}' does not exist")
            return False

        subprocess.run(cmd, cwd=cwd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f" launching {service['description']} failed: {e}")
        return False
    except KeyboardInterrupt:
        print(f"\n{service['description']} stopped by user")
        return True


def start_all_services(host="0.0.0.0", reload=False):
    """Start all AI services defined in the SERVICES dictionary."""
    print("starting all AI services...")

    processes = []
    for service_name, service in SERVICES.items():
        print(f"launching  {service['description']} (port {service['port']})...")

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
                print(f"error: directory '{service['path']}' does not exist")
                continue

            proc = subprocess.Popen(cmd, cwd=cwd)
            processes.append((service_name, proc))
            time.sleep(1)  #
        except Exception as e:
            print(f"error:  launching {service['description']} failed: {e}")

    if not processes:
        print("there are no services to start")
        return

    print(f"\n there are {len(processes)} services running:")
    for service_name, proc in processes:
        service = SERVICES[service_name]
        print(f"  - {service['description']}: http://{host}:{service['port']}")

    print("\ninterrupt the script to stop all services")

    try:

        for _, proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("\nStopping all services...")
        for service_name, proc in processes:
            print(f"stoping {service_name}...")
            proc.terminate()

        # 等待进程结束
        for _, proc in processes:
            proc.wait()
        print("all services stopped successfully")


def main():
    parser = argparse.ArgumentParser(description="AI service startup script")
    parser.add_argument(
        "service",
        nargs="?",
        choices=list(SERVICES.keys()) + ["all"],
        default="all",
        help="start a specific service or 'all' to start all services (default: all)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="blind to a specific host (default:0.0.0.0)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="enable auto-reload for development (default: False, only works with uvicorn)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list available AI services and their ports"
    )

    args = parser.parse_args()

    if args.list:
        print("Available AI services:")
        for name, service in SERVICES.items():
            print(f"  {name:12} - {service['description']} (port {service['port']})")
        return

    if args.service == "all":
        start_all_services(args.host, args.reload)
    else:
        start_service(args.service, args.host, args.reload)


if __name__ == "__main__":
    main()
