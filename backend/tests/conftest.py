import os

# Provide sane defaults so app.config doesn't blow up if .env is missing in CI.
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("MASTER_KEY", "uF3xoNLPI4VPQ6W3UwFvhaxQg9e0G4U_D2X1L5FgLaY=")  # Fernet key
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://trader:trader@localhost:5432/trader")
