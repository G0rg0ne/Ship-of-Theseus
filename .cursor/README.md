# Project Name

> **Note**: This README is a living document that should be updated with every significant change to the project.

## 📋 Overview

Brief description of what this application does and why it exists.

## 🏗️ Technology Stack

### Backend
- **FastAPI** - Modern Python web framework
- **Pydantic** - Data validation
- **SQLAlchemy** - ORM (if using database)
- **Uvicorn** - ASGI server
- Python 3.10+

### Frontend
- **Streamlit** - Data/web app framework
- **Requests** - HTTP client
- Additional libraries as needed

## 📁 Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app initialization
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/   # API route handlers
│   │   │       └── deps.py      # Dependencies
│   │   ├── core/
│   │   │   ├── config.py        # Settings
│   │   │   └── security.py      # Auth utilities
│   │   ├── models/              # Database models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business logic
│   │   └── db/
│   │       └── database.py      # Database connection
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── app.py                   # Main Streamlit app
│   ├── pages/                   # Multi-page app pages
│   ├── components/              # Reusable UI components
│   ├── services/
│   │   └── api_client.py        # API client
│   ├── utils/                   # Helper functions
│   ├── requirements.txt
│   └── .streamlit/
│       └── config.toml
├── shared/                      # Shared utilities
├── tests/                       # Test files
├── README.md                    # This file
├── DEVELOPMENT.md               # Development log
├── .env.example                 # Environment variables template
└── .gitignore
```

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Virtual environment tool (optional but recommended)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd <project-name>
   ```

2. **Set up virtual environment** (recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install backend dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. **Install frontend dependencies**
   ```bash
   cd ../frontend
   pip install -r requirements.txt
   ```

5. **Set up environment variables**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env with your configuration
   # See "Environment Variables" section below
   ```

## ⚙️ Environment Variables

### Backend (.env in project root or backend/)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | Database connection string | `sqlite:///./app.db` | Yes |
| `SECRET_KEY` | Secret key for JWT/sessions | - | Yes |
| `DEBUG` | Enable debug mode | `False` | No |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:8501` | Yes |
| `API_V1_PREFIX` | API version prefix | `/api/v1` | No |

### Frontend (.env in frontend/)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `API_BASE_URL` | Backend API URL | `http://localhost:8000` | Yes |

## 🏃 Running the Application

### Development Mode

1. **Start the backend server**
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```
   
   The API will be available at:
   - API: http://localhost:8000
   - Interactive docs: http://localhost:8000/docs
   - Alternative docs: http://localhost:8000/redoc

2. **Start the frontend** (in a new terminal)
   ```bash
   cd frontend
   streamlit run app.py
   ```
   
   The Streamlit app will be available at:
   - Frontend: http://localhost:8501

### Production Mode

[Add production deployment instructions here]

## 📡 API Endpoints

### Base URL
`http://localhost:8000/api/v1`

### Endpoints

#### Example Resource
- `GET /items` - List all items
  - Query params: `skip` (int), `limit` (int)
  - Returns: List of items
  
- `GET /items/{item_id}` - Get item by ID
  - Returns: Single item or 404
  
- `POST /items` - Create new item
  - Body: `ItemCreate` schema
  - Returns: Created item
  
- `PUT /items/{item_id}` - Update item
  - Body: `ItemUpdate` schema
  - Returns: Updated item
  
- `DELETE /items/{item_id}` - Delete item
  - Returns: 204 No Content

[Update this section as endpoints are added]

## 🖥️ Frontend Pages

### Available Pages

1. **Home** (`app.py`)
   - Description of home page functionality
   
2. **Page Name** (`pages/1_PageName.py`)
   - Description of page functionality

[Update this section as pages are added]

## 🧪 Testing

### Running Tests

**Backend tests:**
```bash
cd backend
pytest
```

**Frontend tests:**
```bash
cd frontend
pytest
```

**Run with coverage:**
```bash
pytest --cov=app --cov-report=html
```

### Test Structure

```
tests/
├── backend/
│   ├── test_endpoints.py
│   ├── test_services.py
│   └── test_models.py
└── frontend/
    └── test_components.py
```

## 🔧 Development

### Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for functions and classes
- Keep functions small and focused

### Adding New Features

1. Create a feature branch
2. Implement the feature
3. Write tests
4. Update README.md with new endpoints/pages/env vars
5. Add entry to DEVELOPMENT.md
6. Submit pull request

### Database Migrations (if using Alembic)

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## 📚 Additional Documentation

- [DEVELOPMENT.md](DEVELOPMENT.md) - Detailed development log and changelog
- [API Documentation](http://localhost:8000/docs) - Interactive API docs (when running)

## 🐛 Troubleshooting

### Common Issues

**Issue**: Cannot connect to backend from frontend
- **Solution**: Ensure backend is running and CORS_ORIGINS is set correctly

**Issue**: Database errors
- **Solution**: Check DATABASE_URL and run migrations

**Issue**: Module not found errors
- **Solution**: Ensure virtual environment is activated and dependencies are installed

## 📝 Recent Changes

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed changelog.

### Latest Updates
- [Date] - Brief description of latest change
- [Date] - Brief description of previous change

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Update documentation
5. Submit a pull request

## 📄 License

[Your license here]

## 👥 Authors

[Your name/team]

## 🙏 Acknowledgments

[Any acknowledgments]

---

**Last Updated**: [Date]  
**Version**: [Version number if applicable]
