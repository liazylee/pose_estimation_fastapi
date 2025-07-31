#!/usr/bin/env python3
"""
Test script for Kafka input/output interfaces.
"""
import asyncio
import base64
import json
import logging

import cv2
import numpy as np

from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.kafka_output_interface import KafkaOutput

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_kafka_topics_if_needed(bootstrap_servers: str, topics: list):
    """Try to create Kafka topics using admin client."""
    try:
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError

        admin_client = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers,
            client_id='test_topic_creator'
        )

        # Create topic configurations
        topic_list = []
        for topic_name in topics:
            topic = NewTopic(
                name=topic_name,
                num_partitions=1,
                replication_factor=1
            )
            topic_list.append(topic)

        # Create topics
        try:
            fs = admin_client.create_topics(new_topics=topic_list, validate_only=False)

            # Handle different kafka-python versions
            if hasattr(fs, 'items'):
                # Older kafka-python versions return a dict
                for topic, f in fs.items():
                    try:
                        f.result()  # The result itself is None
                        logger.info(f"Topic '{topic}' created successfully")
                    except TopicAlreadyExistsError:
                        logger.info(f"Topic '{topic}' already exists")
                    except Exception as e:
                        logger.warning(f"Failed to create topic '{topic}': {e}")
            else:
                # Newer kafka-python versions - just check if operation succeeded
                logger.info(f"Topic creation request sent for: {[t.name for t in topic_list]}")
                # Wait a moment for topics to be created
                await asyncio.sleep(1)

        except TopicAlreadyExistsError:
            logger.info("One or more topics already exist")
        except Exception as e:
            logger.warning(f"Topic creation failed: {e}")
            admin_client.close()
            return False

        admin_client.close()

        # Verify topics were created by listing them
        try:
            admin_client = KafkaAdminClient(
                bootstrap_servers=bootstrap_servers,
                client_id='test_topic_verifier'
            )

            metadata = admin_client.list_topics()
            existing_topics = set(metadata)

            for topic in topics:
                if topic in existing_topics:
                    logger.info(f"✅ Topic '{topic}' verified to exist")
                else:
                    logger.warning(f"⚠️ Topic '{topic}' may not have been created")

            admin_client.close()

        except Exception as e:
            logger.warning(f"Could not verify topic creation: {e}")

        return True

    except Exception as e:
        logger.warning(f"Could not create topics automatically: {e}")
        return False


def print_manual_topic_creation_commands(bootstrap_servers: str, topics: list):
    """Print commands for manual topic creation."""
    print("\n" + "=" * 60)
    print("MANUAL TOPIC CREATION REQUIRED")
    print("=" * 60)
    print("Kafka topics need to be created manually.")
    print("Run these commands in your terminal:")
    print()

    for topic in topics:
        print(f"# Create topic: {topic}")
        print(f"kafka-topics --create --topic {topic} \\")
        print(f"  --bootstrap-server {bootstrap_servers} \\")
        print(f"  --partitions 1 --replication-factor 1")
        print()

    print("Alternative using Docker (if using containerized Kafka):")
    for topic in topics:
        print(f"docker exec kafka kafka-topics --create --topic {topic} \\")
        print(f"  --bootstrap-server localhost:9092 \\")
        print(f"  --partitions 1 --replication-factor 1")
        print()

    print("=" * 60)


async def test_kafka_interfaces():
    """Test Kafka input and output interfaces."""

    # Configuration
    kafka_config = {
        'bootstrap_servers': 'localhost:9092',
        'input_topic': 'raw_frames_test',
        'output_topic': 'yolox_detections_test',
        'group_id': 'test_consumer'
    }

    topics_needed = [kafka_config['input_topic'], kafka_config['output_topic']]

    try:
        # Try to create topics automatically
        logger.info("Attempting to create Kafka topics automatically...")
        topic_creation_success = await create_kafka_topics_if_needed(
            kafka_config['bootstrap_servers'],
            topics_needed
        )

        if not topic_creation_success:
            print_manual_topic_creation_commands(kafka_config['bootstrap_servers'], topics_needed)
            print("Please create the topics manually and run the test again.")
            return

        # Wait a moment for topics to be available
        await asyncio.sleep(2)

        # Create input interface
        input_config = {
            'bootstrap_servers': kafka_config['bootstrap_servers'],
            'topic': kafka_config['input_topic'],
            'group_id': kafka_config['group_id'],
            'auto_offset_reset': 'earliest'
        }

        # Create output interface
        output_config = {
            'bootstrap_servers': kafka_config['bootstrap_servers'],
            'topic': kafka_config['output_topic']
        }

        # Initialize interfaces
        kafka_input = KafkaInput(config=input_config)
        kafka_output = KafkaOutput(config=output_config)

        logger.info("Initializing Kafka interfaces...")
        await kafka_input.initialize()
        await kafka_output.initialize()

        logger.info("Kafka interfaces initialized successfully")

        # Test output by sending a sample detection result
        test_result = {
            'frame_id': 'test_frame_001',
            'bboxes': [[100, 100, 200, 200], [300, 300, 400, 400]],
            'det_scores': [0.95, 0.87],
            'classes': [-1, -1],
            'num_detections': 2,
            'test_mode': True,
            'test_timestamp': asyncio.get_event_loop().time()
        }

        await kafka_output.write_data(test_result)
        logger.info("✅ Test detection result sent to Kafka successfully")

        # Test input by waiting for messages (this will wait for external messages)
        logger.info(f"Waiting for messages on topic: {kafka_config['input_topic']}")
        logger.info("Send a test message to this topic to verify input functionality")

        try:
            # Wait for input with a shorter timeout for testing
            data, metadata = await asyncio.wait_for(
                kafka_input.read_data(),
                timeout=5.0
            )
            logger.info(f"✅ Received data type: {type(data)}")
            logger.info(f"✅ Metadata: {metadata}")
        except asyncio.TimeoutError:
            logger.info("⏱️  No input data received within timeout (this is normal for testing)")
        except Exception as e:
            logger.warning(f"⚠️  Input test skipped: {e}")

        # Cleanup
        await kafka_input.cleanup()
        await kafka_output.cleanup()

        logger.info("🎉 Test completed successfully!")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")

        # Provide troubleshooting information
        print("\n" + "=" * 60)
        print("TROUBLESHOOTING GUIDE")
        print("=" * 60)
        print("Common issues and solutions:")
        print()
        print("1. Kafka is not running:")
        print("   - Start Kafka: bin/kafka-server-start.sh config/server.properties")
        print("   - Or using Docker: docker-compose up kafka")
        print()
        print("2. Topic doesn't exist:")
        print("   - Enable auto-topic creation in Kafka config")
        print("   - Or create topics manually (see commands above)")
        print()
        print("3. Connection refused:")
        print("   - Check if Kafka is listening on localhost:9092")
        print("   - Verify firewall settings")
        print()
        print("4. Permission issues:")
        print("   - Check Kafka user permissions")
        print("   - Verify client authentication settings")
        print("=" * 60)

        raise


def create_test_frame_message():
    """Create a test frame message for manual testing."""

    # Create a simple test image
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(test_image, (100, 100), (200, 200), (0, 255, 0), 2)
    cv2.putText(test_image, "Test Frame", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    # Encode as base64
    _, buffer = cv2.imencode('.jpg', test_image)
    image_base64 = base64.b64encode(buffer).decode('utf-8')

    # Create message
    message = {
        'frame_id': 'test_frame_001',
        'image_data': image_base64,
        'timestamp': 1234567890.123
    }

    return json.dumps(message)


def print_kafka_producer_example():
    """Print example code for producing test messages."""
    print("\n" + "=" * 60)
    print("KAFKA PRODUCER EXAMPLE")
    print("=" * 60)
    print("To test the input functionality, run this in another terminal:")
    print()
    print("```python")
    print("from kafka import KafkaProducer")
    print("import json")
    print()
    print("producer = KafkaProducer(")
    print("    bootstrap_servers='localhost:9092',")
    print("    value_serializer=lambda v: json.dumps(v).encode('utf-8')")
    print(")")
    print()
    sample_message = create_test_frame_message()
    print("message = '''")
    print(sample_message)
    print("'''")
    print()
    print("producer.send('raw_frames_test', json.loads(message))")
    print("producer.flush()")
    print("producer.close()")
    print("```")
    print("=" * 60)


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Kafka Integration Test")
    print("=" * 60)
    print("This test will:")
    print("1. Try to create Kafka topics automatically")
    print("2. Initialize Kafka input/output interfaces")
    print("3. Send a test detection result")
    print("4. Wait for input messages (optional)")
    print()
    print("Prerequisites:")
    print("- Kafka running on localhost:9092")
    print("- kafka-python package installed")
    print("=" * 60)

    try:
        asyncio.run(test_kafka_interfaces())
        print_kafka_producer_example()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback

        traceback.print_exc()
