# Ship of Theseus - Authentication System

An authentication system with FastAPI backend and Streamlit frontend, containerized with Docker. Set up for local development first.

## Features

- 🔐 JWT-based authentication
- 🚀 FastAPI backend
- 🎨 Streamlit frontend
- 🐳 Docker Compose orchestration

## Quick Start (Development)

### Prerequisites

- Docker and Docker Compose

### Setup

1. **Create `.env` file**:
   ```bash
   cat > .env << EOF
   SECRET_KEY=$(openssl rand -hex 32)
   USERNAME=admin
   USER_EMAIL=admin@example.com
   USER_PASSWORD=your-secure-password-here
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   ALLOWED_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
   EOF
   ```

2. **Start services**:
   ```bash
   docker-compose up -d
   ```

3. **Access**:
   - Frontend: http://localhost:8501
   - Backend API: http://localhost:8000

## Project Structure

```
Ship-of-Theseus/
├── backend/          # FastAPI service
├── frontend/         # Streamlit service
├── docker-compose.yml
└── CLAUDE.md         # Detailed documentation
```

## Services

- **Backend** (8000): FastAPI authentication API
- **Frontend** (8501): Streamlit web app

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
