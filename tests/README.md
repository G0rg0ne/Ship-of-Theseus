# Tests

This directory contains all test files for the project.

## Structure

```
tests/
├── backend/              # Backend tests
│   ├── test_endpoints.py
│   ├── test_services.py
│   └── test_models.py
└── frontend/             # Frontend tests
    └── test_components.py
```

## Running Tests

### Backend tests:
```bash
cd backend
pytest
```

### Frontend tests:
```bash
cd frontend
pytest
```

### Run with coverage:
```bash
pytest --cov=app --cov-report=html
```

## Writing Tests

- Use pytest for all tests
- Follow naming convention: `test_*.py`
- Use fixtures for common setup
- Mock external dependencies
- Aim for high test coverage
