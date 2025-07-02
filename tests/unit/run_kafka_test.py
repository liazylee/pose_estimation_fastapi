#!/usr/bin/env python3
"""
Simple runner for Kafka + YOLOX integration test.
"""
import logging
import os
import subprocess
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_requirements():
    """Check if all requirements are met."""
    logger.info("🔍 Checking requirements...")

    # Check if Kafka is running
    try:
        from kafka import KafkaProducer
        test_producer = KafkaProducer(bootstrap_servers='localhost:9092')
        test_producer.close()
        logger.info("✅ Kafka is running")
    except Exception as e:
        logger.error("❌ Kafka is not running or not accessible")
        logger.error("Please start Kafka first:")
        logger.error("  1. Start Zookeeper: bin/zookeeper-server-start.sh config/zookeeper.properties")
        logger.error("  2. Start Kafka: bin/kafka-server-start.sh config/server.properties")
        return False

    # Check if test image exists
    image_path = "human-pose.jpeg"
    if os.path.exists(image_path):
        logger.info("✅ Test image found")
    else:
        logger.error(f"❌ Test image not found: {image_path}")
        return False

    # Check if config file exists
    config_path = "../../apps/dev_pose_estimation_config.yaml"
    if os.path.exists(config_path):
        logger.info("✅ Configuration file found")
    else:
        logger.error(f"❌ Configuration file not found: {config_path}")
        return False

    return True


def run_test():
    """Run the Kafka + YOLOX integration test."""
    if not check_requirements():
        logger.error("❌ Requirements check failed. Please fix the issues above.")
        return False

    logger.info("🚀 Starting Kafka + YOLOX integration test...")

    try:
        # Run the test script
        result = subprocess.run([
            sys.executable,
            "tests/unit/test_push_kafka.py"
        ], capture_output=True, text=True, cwd=".")

        if result.returncode == 0:
            logger.info("✅ Test completed successfully!")
            print("STDOUT:")
            print(result.stdout)
        else:
            logger.error("❌ Test failed!")
            print("STDERR:")
            print(result.stderr)
            print("STDOUT:")
            print(result.stdout)

        return result.returncode == 0

    except Exception as e:
        logger.error(f"❌ Error running test: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Kafka + YOLOX Integration Test Runner")
    print("=" * 60)

    success = run_test()

    print("\n" + "=" * 60)
    if success:
        print("🎉 All tests passed!")
    else:
        print("💥 Test failed!")
    print("=" * 60)

    sys.exit(0 if success else 1)
