#!/bin/bash

# stop docker-compose
echo "Stopping docker-compose..."
docker-compose down


# Start docker-compose
echo "Starting docker-compose..."
docker-compose up -d

# Check if containers are running
echo "Checking container status..."
docker-compose ps

echo "Docker-compose started successfully!"
