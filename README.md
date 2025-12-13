# Ship of Theseus - Authentication System

A production-ready authentication system with FastAPI backend, Streamlit frontend, and Caddy reverse proxy—all containerized with Docker.

## Features

- 🔐 JWT-based authentication
- 🚀 FastAPI backend
- 🎨 Streamlit frontend
- 🔒 Automatic SSL/TLS via Caddy
- 🐳 Docker Compose orchestration

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Domain name pointing to your server
- Ports 80 and 443 open

### Setup

1. **Create `.env` file**:
   ```bash
   cat > .env << EOF
   SECRET_KEY=$(openssl rand -hex 32)
   USERNAME=admin
   USER_EMAIL=admin@example.com
   USER_PASSWORD=your-secure-password-here
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
   EOF
   ```

2. **Update `Caddyfile`** - Replace `gorgone.app` with your domain

3. **Start services**:
   ```bash
   docker-compose up -d
   ```

4. **Access**:
   - Frontend: `https://yourdomain.com`
   - Backend API: `https://yourdomain.com/api/`

## Project Structure

```
Ship-of-Theseus/
├── backend/          # FastAPI service
├── frontend/         # Streamlit service
├── Caddyfile         # Reverse proxy config
├── docker-compose.yml
└── CLAUDE.md         # Detailed documentation
```

## Services

- **Backend** (8000): FastAPI authentication API
- **Frontend** (8501): Streamlit web app
- **Caddy** (80/443): Reverse proxy with auto SSL

## Common Commands

```bash
# View logs
docker-compose logs -f [service_name]

# Rebuild service
docker-compose build [service_name]
docker-compose up -d [service_name]

# Stop all
docker-compose down
```

## License

MIT
