# Patient Safety Monitor - Docker Deployment Guide

This guide covers Docker deployment options for the Patient Safety Monitor application.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Options](#architecture-options)
- [Unified Image (Recommended)](#unified-image-recommended)
- [Multi-Container Setup](#multi-container-setup)
- [Configuration](#configuration)
- [Operations](#operations)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

- Docker 20.10+ and Docker Compose v2
- At least 4GB RAM available
- Anthropic API key

### 1. Clone and Configure

```bash
# Clone the repository
git clone <repository-url>
cd coroner

# Copy environment template
cp .env.example .env

# Edit .env with your settings
# Required: ANTHROPIC_API_KEY, SECRET_KEY, ADMIN_PASSWORD_HASH
```

### 2. Generate Password Hash

```bash
# Generate a bcrypt hash for your admin password (docker-compose compatible)
python scripts/hash_password.py your-password-here

# The output will have $$ escaping for docker-compose .env files
# Example: $$2b$$12$$...

# For raw bcrypt hash (non-docker usage), use --raw flag:
python scripts/hash_password.py your-password-here --raw
```

> **Note:** Docker Compose interprets `$` in `.env` files as variable references.
> The `hash_password.py` script automatically escapes `$` as `$$` for compatibility.

### 3. Start Services

```bash
# Using unified image (recommended)
docker-compose -f docker-compose.unified.yml up -d

# View logs
docker-compose -f docker-compose.unified.yml logs -f
```

### 4. Access Application

- Dashboard: http://localhost:7410/dashboard
- Health check: http://localhost:7410/health
- API docs: http://localhost:7410/docs

---

## Architecture Options

### Option 1: Unified Image (Recommended)

Single Docker image containing all services managed by supervisord.

**Pros:**
- Simple deployment - single container to manage
- Reduced resource overhead
- Easier configuration
- Ideal for small to medium deployments

**Files:**
- `Dockerfile.unified` - Multi-stage build
- `docker-compose.unified.yml` - Compose configuration
- `docker/supervisord.conf` - Process management
- `docker/docker-entrypoint.sh` - Startup script

### Option 2: Multi-Container Setup

Separate containers for each service (app, scheduler, migrate).

**Pros:**
- Better for horizontal scaling
- Independent service lifecycle
- Easier debugging of individual services

**Files:**
- `Dockerfile` - Original Dockerfile
- `docker-compose.yml` - Multi-container compose

---

## Unified Image (Recommended)

### Building the Image

```bash
# Production build
docker build -f Dockerfile.unified -t psm:latest .

# Development build (includes dev tools)
docker build -f Dockerfile.unified --target development -t psm:dev .
```

### Run Modes

The unified image supports multiple run modes via the `RUN_MODE` environment variable:

| Mode | Description | Services Started |
|------|-------------|------------------|
| `all` (default) | All services via supervisord | Web app + Scheduler |
| `app` | Web application only | Uvicorn server |
| `scheduler` | Background scheduler only | APScheduler |
| `migrate` | Run migrations and exit | Alembic + seed |

### Examples

```bash
# Run all services
docker run -d \
  -e RUN_MODE=all \
  -e DATABASE_URL=postgresql://user:pass@host:7411/db \
  -e ANTHROPIC_API_KEY=sk-ant-xxx \
  -p 7410:7410 \
  psm:latest

# Run web app only
docker run -d \
  -e RUN_MODE=app \
  -e DATABASE_URL=postgresql://user:pass@host:7411/db \
  -p 7410:7410 \
  psm:latest

# Run migrations only (one-time)
docker run --rm \
  -e RUN_MODE=migrate \
  -e DATABASE_URL=postgresql://user:pass@host:7411/db \
  psm:latest
```

### Docker Compose (Unified)

```bash
# Start all services
docker-compose -f docker-compose.unified.yml up -d

# View logs
docker-compose -f docker-compose.unified.yml logs -f psm

# Restart
docker-compose -f docker-compose.unified.yml restart

# Stop
docker-compose -f docker-compose.unified.yml down

# Stop and remove volumes (WARNING: deletes data)
docker-compose -f docker-compose.unified.yml down -v
```

---

## Multi-Container Setup

### Starting Services

```bash
# Start all services
docker-compose up -d

# Run migrations first (if not using unified)
docker-compose run --rm migrate

# View logs
docker-compose logs -f app
docker-compose logs -f scheduler
```

### Service Descriptions

| Service | Purpose | Port |
|---------|---------|------|
| `app` | FastAPI web application | 7410 |
| `scheduler` | APScheduler background jobs | - |
| `migrate` | Database migrations (one-time) | - |
| `db` | PostgreSQL database | 7411 |

---

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:7411/db` |
| `ANTHROPIC_API_KEY` | Claude API key | `sk-ant-api03-xxx` |
| `SECRET_KEY` | JWT signing key | Use `secrets.token_urlsafe(32)` |
| `ADMIN_USERNAME` | Admin login username | `admin` |
| `ADMIN_PASSWORD_HASH` | Bcrypt password hash | `$2b$12$xxx` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `production` | `development`, `staging`, `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `OPENAI_API_KEY` | - | Fallback LLM API key |
| `FTP_HOST` | - | Blog deployment FTP host |
| `FTP_USERNAME` | - | FTP username |
| `FTP_PASSWORD` | - | FTP password |
| `RUN_MODE` | `all` | `all`, `app`, `scheduler`, `migrate` |

### Runtime Configuration (Unified Image)

| Variable | Default | Description |
|----------|---------|-------------|
| `WAIT_FOR_DB` | `true` | Wait for database on startup |
| `RUN_MIGRATIONS` | `true` | Run Alembic migrations on startup |
| `SEED_SOURCES` | `true` | Seed data sources on startup |

---

## Operations

### Health Checks

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' patient-safety-monitor

# Manual health check
curl http://localhost:7410/health
```

### Viewing Logs

```bash
# All services (unified)
docker-compose -f docker-compose.unified.yml logs -f

# Specific service logs
docker exec patient-safety-monitor tail -f /app/logs/app.log
docker exec patient-safety-monitor tail -f /app/logs/scheduler.log
docker exec patient-safety-monitor tail -f /app/logs/supervisord.log
```

### Process Management (Unified)

```bash
# Check supervisor status
docker exec patient-safety-monitor supervisorctl status

# Restart specific service
docker exec patient-safety-monitor supervisorctl restart app
docker exec patient-safety-monitor supervisorctl restart scheduler

# Stop a service
docker exec patient-safety-monitor supervisorctl stop scheduler
```

### Database Operations

```bash
# Connect to database
docker exec -it psm-database psql -U psm_user -d patient_safety_monitor

# Backup database
docker exec psm-database pg_dump -U psm_user patient_safety_monitor > backup.sql

# Restore database
cat backup.sql | docker exec -i psm-database psql -U psm_user patient_safety_monitor

# Run migrations manually
docker exec patient-safety-monitor alembic upgrade head
```

### Updating the Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose -f docker-compose.unified.yml up -d --build

# Or with no downtime (rolling update)
docker-compose -f docker-compose.unified.yml build
docker-compose -f docker-compose.unified.yml up -d --no-deps psm
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose -f docker-compose.unified.yml logs psm

# Check if database is accessible
docker exec patient-safety-monitor pg_isready -h db -U psm_user

# Verify environment variables
docker exec patient-safety-monitor env | grep -E 'DATABASE|ANTHROPIC'
```

### Database Connection Issues

```bash
# Check database health
docker-compose -f docker-compose.unified.yml exec db pg_isready

# View database logs
docker-compose -f docker-compose.unified.yml logs db

# Test connection from app container
docker exec patient-safety-monitor python -c "
from database.connection import get_engine
engine = get_engine()
print('Connected successfully!')
"
```

### Playwright/Browser Issues

```bash
# Reinstall Playwright browsers
docker exec patient-safety-monitor playwright install chromium

# Check Playwright dependencies
docker exec patient-safety-monitor playwright install-deps
```

### Permission Issues

```bash
# Fix log directory permissions
docker exec -u root patient-safety-monitor chown -R appuser:appuser /app/logs /app/data

# Rebuild image with fixed permissions
docker-compose -f docker-compose.unified.yml build --no-cache
```

### Memory Issues

```bash
# Increase container memory limit
# In docker-compose.unified.yml, add:
services:
  psm:
    deploy:
      resources:
        limits:
          memory: 4G
```

---

## Production Recommendations

### Security

1. Use secrets management for sensitive values
2. Run with read-only root filesystem where possible
3. Keep the image updated with security patches
4. Use a reverse proxy (nginx/traefik) for TLS

### Performance

1. Use external PostgreSQL for better performance
2. Enable PostgreSQL connection pooling
3. Consider separate containers for horizontal scaling
4. Use named volumes for data persistence

### Monitoring

1. Use `docker stats` or container monitoring tools
2. Export logs to centralized logging (ELK, CloudWatch)
3. Set up alerting on container health checks
4. Monitor disk usage for logs and data volumes

### Backup Strategy

```bash
# Backup script example
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker exec psm-database pg_dump -U psm_user patient_safety_monitor | gzip > backup_$DATE.sql.gz
```

---

## File Reference

| File | Purpose |
|------|---------|
| `Dockerfile.unified` | Unified multi-stage Docker build |
| `docker-compose.unified.yml` | Compose config for unified deployment |
| `docker/docker-entrypoint.sh` | Container startup script |
| `docker/supervisord.conf` | Supervisor process configuration |
| `.dockerignore` | Build context exclusions |
| `Dockerfile` | Original single-service Dockerfile |
| `docker-compose.yml` | Original multi-container compose |
