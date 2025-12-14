#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting deployment...${NC}"

# Navigate to project directory
cd /opt/ship-of-theseus

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo "Please create .env file with required environment variables."
    exit 1
fi

# Pull latest code (if using git on server)
if [ -d .git ]; then
    echo -e "${YELLOW}Pulling latest code...${NC}"
    git pull origin main || true
fi

# Stop existing containers gracefully
echo -e "${YELLOW}Stopping existing containers...${NC}"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml down --timeout 30 || true

# Remove old images (optional - saves disk space)
echo -e "${YELLOW}Cleaning up old images...${NC}"
docker image prune -f

# Build new images
echo -e "${YELLOW}Building Docker images...${NC}"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache

# Start services
echo -e "${YELLOW}Starting services...${NC}"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
sleep 10

# Health check
if [ -f scripts/health-check.sh ]; then
    chmod +x scripts/health-check.sh
    ./scripts/health-check.sh
fi

# Show running containers
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${YELLOW}Running containers:${NC}"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps

# Show logs (last 20 lines)
echo -e "${YELLOW}Recent logs:${NC}"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=20