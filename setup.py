from setuptools import setup, find_packages

setup(
    name="pose-estimation-fastapi",
    version="1.0.0",
    description="Multi-User AI Video Analysis Platform with Pose Estimation",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "pydantic>=2.0.0",
        "asyncio-mqtt",
        "kafka-python",
        "opencv-python",
        "numpy",
        "torch",
        "torchvision",
        # Add other dependencies as needed
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-asyncio",
            "black",
            "isort",
            "flake8",
        ]
    }
) 