# Ship of Theseus - Authentication System

A production-ready authentication system built with FastAPI (backend), Streamlit (frontend), and Caddy (reverse proxy), all containerized with Docker.

## Features

- 🔐 JWT-based authentication
- 🚀 Production-ready FastAPI backend
- 🎨 Modern Streamlit frontend
- 🔒 Automatic SSL/TLS via Caddy with Let's Encrypt
- 🐳 Docker Compose orchestration
- 📦 Separate, evolvable services

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Domain name pointing to your server
- Ports 80 and 443 open

### Setup

1. **Clone and navigate to the project**:
   ```bash
   cd /home/deployer/Ship-of-Theseus
   ```

2. **Configure environment variables**:
   ```bash
   # Create .env file with required variables
   cat > .env << EOF
   SECRET_KEY=$(openssl rand -hex 32)
   USERNAME=admin
   USER_EMAIL=admin@example.com
   USER_PASSWORD=your-secure-password-here
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
   EOF
   # Edit .env and set your actual username, email, and password
   ```

3. **Update Caddyfile**:
   - Edit `Caddyfile`
   - Replace `gorgone.app` and `www.gorgone.app` with your actual domain
   - Caddy will automatically obtain SSL certificates via Let's Encrypt

4. **Build and start services**:
   ```bash
   docker-compose build
   docker-compose up -d
   ```

6. **Access your application**:
   - Frontend: `https://yourdomain.com`
   - Backend API: `https://yourdomain.com/api/`

## Project Structure

```
Ship-of-Theseus/
├── backend/          # FastAPI backend service
├── frontend/         # Streamlit frontend service
├── Caddyfile         # Caddy reverse proxy configuration
├── docker-compose.yml
└── CLAUDE.md         # Detailed architecture documentation
```

## Services

- **Backend** (Port 8000): FastAPI authentication API
- **Frontend** (Port 8501): Streamlit web application
- **Caddy** (Ports 80/443): Reverse proxy with automatic SSL/TLS

## Documentation

For detailed architecture, implementation details, and extension guide, see [CLAUDE.md](./CLAUDE.md).

## Development

### Rebuild a service:
```bash
docker-compose build [service_name]
docker-compose up -d [service_name]
```

### View logs:
```bash
docker-compose logs -f [service_name]
```

### Stop all services:
```bash
docker-compose down
```

## Security Notes

- Change the default `SECRET_KEY` in production
- Use strong, unique passwords
- Caddy automatically manages SSL certificates (no manual renewal needed)
- Regularly update dependencies

## License

MIT
