from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
import jwt
import bcrypt
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Authentication API",
    description="JWT-based authentication backend",
    version="1.0.0"
)

# CORS configuration for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Single user from environment variables - validate BEFORE creating CryptContext
USERNAME = os.getenv("USERNAME", "")
USER_EMAIL = os.getenv("USER_EMAIL", "")
USER_PASSWORD = os.getenv("USER_PASSWORD", "")

# Validate and handle password length BEFORE creating CryptContext (bcrypt has 72-byte limit)
# This must happen before CryptContext creation because passlib initializes bcrypt
# during CryptContext creation, and it will fail if password is too long
if USER_PASSWORD:
    password_bytes = USER_PASSWORD.encode('utf-8')
    if len(password_bytes) > 72:
        # Truncate to 72 bytes to avoid bcrypt error
        # Note: This is a workaround - ideally use a shorter password
        USER_PASSWORD = password_bytes[:72].decode('utf-8', errors='ignore')
        print(f"⚠️  WARNING: Password was truncated to 72 bytes (bcrypt limit)")

# Use bcrypt directly instead of passlib to avoid initialization issues
security = HTTPBearer()

USER_PASSWORD_HASH = None
user_data = None


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class UserResponse(BaseModel):
    username: str
    email: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    # Ensure password doesn't exceed bcrypt's 72-byte limit
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        plain_password = password_bytes[:72].decode('utf-8', errors='ignore')
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Hash a password."""
    # Ensure password doesn't exceed bcrypt's 72-byte limit
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password = password_bytes[:72].decode('utf-8', errors='ignore')
    # Generate salt and hash password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


# Initialize password hashing context before using it
# This needs to be defined before we use it in the module-level code




def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return current user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    # Only allow the single user from environment variables
    if username != USERNAME:
        raise credentials_exception
    
    return user_data


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Authentication API is running", "status": "healthy"}


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(user: UserLogin):
    """Authenticate user and return JWT token."""
    # Only allow the single user from environment variables
    if user.username != USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    if not verify_password(user.password, USER_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": USERNAME}, expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user information."""
    return UserResponse(
        username=current_user["username"],
        email=current_user["email"]
    )


@app.get("/api/auth/verify")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """Verify if token is valid."""
    return {"valid": True, "username": current_user["username"]}


# Initialize user from environment variables (after all functions are defined)
# Validate required environment variables
if not USERNAME or not USER_EMAIL or not USER_PASSWORD:
    raise ValueError(
        "Missing required environment variables: USERNAME, USER_EMAIL, USER_PASSWORD. "
        "Please set these in your .env file."
    )

# Hash password (password length already validated above)
USER_PASSWORD_HASH = get_password_hash(USER_PASSWORD)

# Create user data structure
user_data = {
    "username": USERNAME,
    "email": USER_EMAIL,
    "hashed_password": USER_PASSWORD_HASH
}

print(f"✅ User '{USERNAME}' initialized from environment variables")


