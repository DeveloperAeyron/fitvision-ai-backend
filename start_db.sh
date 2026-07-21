#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting PostgreSQL Database via Docker..."
docker-compose up -d
echo "Database started. You can now start the server."
