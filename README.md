# Ship of Theseus - Authentication System

An authentication system with FastAPI backend and Streamlit frontend, containerized with Docker. Features a clean, modular architecture following best practices.

## Features

- 🔐 JWT-based authentication
- 📄 PDF document upload and text extraction
- 🚀 FastAPI backend with modular architecture
- 🎨 Streamlit frontend with component-based design
- 🐳 Docker Compose orchestration
- 📁 Well-organized project structure
- ✅ Ready for testing and extension

## 📁 Project Structure

```
Ship-of-Theseus/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app initialization
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/   # API route handlers
│   │   │       │   ├── auth.py
│   │   │       │   └── documents.py
│   │   │       └── deps.py      # Dependencies
│   │   ├── core/
│   │   │   ├── config.py        # Settings & configuration
│   │   │   └── security.py      # JWT & password utilities
│   │   ├── models/              # Database models (empty - ready for expansion)
│   │   ├── schemas/             # Pydantic schemas
│   │   │   └── auth.py
│   │   ├── services/            # Business logic
│   │   │   └── user_service.py
│   │   └── db/                  # Database connection (empty - ready for expansion)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app.py                   # Main Streamlit app
│   ├── pages/                   # Multi-page app pages (empty - ready for expansion)
│   ├── components/              # Reusable UI components
│   │   ├── login_form.py
│   │   ├── welcome_page.py
│   │   └── pdf_section.py
│   ├── services/
│   │   └── api_client.py        # API client
│   ├── utils/                   # Helper functions
│   │   └── auth_utils.py
│   ├── .streamlit/
│   │   └── config.toml
│   ├── requirements.txt
│   └── Dockerfile
├── shared/                      # Shared utilities (ready for expansion)
├── tests/                       # Test files
│   ├── backend/
│   └── frontend/
├── .env.example                 # Environment variables template
├── .gitignore
├── docker-compose.yml
└── README.md                    # This file
```

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose

### Setup

1. **Create `.env` file**:
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Generate a secure secret key (Linux/Mac)
   SECRET_KEY=$(openssl rand -hex 32)
   
   # Or manually edit .env with your values:
   # - SECRET_KEY: Use a strong random string
   # - USERNAME: Your admin username
   # - USER_EMAIL: Your admin email
   # - USER_PASSWORD: Your secure password
   ```

2. **Start services**:
   ```bash
   docker-compose up -d
   ```

3. **Access the application**:
   - Frontend: http://localhost:8501
   - Backend API: http://localhost:8000
   - Health check: http://localhost:8000/

## ⚙️ Environment Variables

See `.env.example` for all available configuration options.

### Required Variables (app will not start without these):
- `SECRET_KEY` - JWT secret key (generate with `openssl rand -hex 32`) - **REQUIRED**
- `USERNAME` - Admin username - **REQUIRED**
- `USER_EMAIL` - Admin email - **REQUIRED**
- `USER_PASSWORD` - Admin password - **REQUIRED**

### Optional Variables (have defaults):
- `ALLOWED_ORIGINS` - CORS origins (comma-separated, default: `http://localhost:8501`)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiration in minutes (default: `30`)
- `DEBUG` - Debug mode (default: `False`)

## 🏃 Running Locally (Development)

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

## 📡 API Endpoints

### Base URL
`http://localhost:8000/api`

### Authentication Endpoints
- `POST /auth/login` - Login and get JWT token
- `GET /auth/me` - Get current user info (requires auth)
- `GET /auth/verify` - Verify token validity (requires auth)

### Document Management Endpoints
- `POST /documents/upload` - Upload PDF and extract text (requires auth, max 10MB)
- `GET /documents/current` - Get currently stored document (requires auth)
- `DELETE /documents/current` - Clear stored document (requires auth)

## 🐳 Docker Commands

```bash
# View logs
docker-compose logs -f [service_name]

# Rebuild service
docker-compose build [service_name]
docker-compose up -d [service_name]

# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## 📚 Documentation

- [DEVELOPMENT.md](DEVELOPMENT.md) - Development log and changelog
- [.cursor/rules/README.mdc](.cursor/rules/README.mdc) - Complete project documentation and standards
- [.cursor/rules/cursorrules.mdc](.cursor/rules/cursorrules.mdc) - Cursor AI assistant rules
- [.cursor/rules/context.mdc](.cursor/rules/context.mdc) - Project context for AI assistant
- [.cursor/rules/DEVELOPMENT.mdc](.cursor/rules/DEVELOPMENT.mdc) - Development guidelines
- [tests/README.md](tests/README.md) - Testing guide
- [shared/README.md](shared/README.md) - Shared utilities guide

## 🔧 Development

The project follows a modular architecture:

- **Backend**: FastAPI with clean separation of concerns (routes, services, schemas, core)
- **Frontend**: Streamlit with component-based design
- **Shared**: Common utilities that can be used by both services
- **Tests**: Comprehensive test coverage for both services

See [.cursor/rules/README.mdc](.cursor/rules/README.mdc) for detailed development guidelines and project standards.

## License

MIT
