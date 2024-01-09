#!/bin/bash

# Ensure the script stops if there is an error
set -e

# Read version from the VERSION file
VERSION=$(cat VERSION)

# Set up the builder instance (only needs to be done once, so you can comment this out after the first run)
# docker buildx create --name mybuilder --use
# docker buildx inspect mybuilder --bootstrap

# Build and push the Docker image for both arm64 and amd64 platforms with the version tag
docker buildx build --platform linux/arm64,linux/amd64 -t krestaino/sptnr:$VERSION . --push

# Build and push the 'latest' tag as well
docker buildx build --platform linux/arm64,linux/amd64 -t krestaino/sptnr:latest . --push

echo "Docker images tagged and pushed: $VERSION and latest"
