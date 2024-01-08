#!/bin/bash

# Ensure the script stops if there is an error
set -e

# Read version from the VERSION file
VERSION=$(cat VERSION)

# Build the Docker image with the version tag
docker build -t krestaino/sptnr:$VERSION .

# Tag the built image as latest
docker tag krestaino/sptnr:$VERSION krestaino/sptnr:latest

# Push both tags to the Docker registry
docker push krestaino/sptnr:$VERSION
docker push krestaino/sptnr:latest

echo "Docker images tagged and pushed: $VERSION and latest"
