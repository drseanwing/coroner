#!/bin/bash
# Patient Safety Monitor - Docker Entrypoint Script
# Manages startup of all services within a single container

set -e

# =============================================================================
# Configuration
# =============================================================================
APP_USER="${APP_USER:-appuser}"
LOG_DIR="${LOG_DIR:-/app/logs}"
DATA_DIR="${DATA_DIR:-/app/data}"
WAIT_FOR_DB="${WAIT_FOR_DB:-true}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
SEED_SOURCES="${SEED_SOURCES:-true}"
START_SCHEDULER="${START_SCHEDULER:-true}"
START_APP="${START_APP:-true}"

# =============================================================================
# Colors for output
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# =============================================================================
# Wait for PostgreSQL to be ready
# =============================================================================
wait_for_database() {
    if [ "$WAIT_FOR_DB" != "true" ]; then
        log_info "Skipping database wait (WAIT_FOR_DB=false)"
        return 0
    fi

    log_info "Waiting for PostgreSQL database..."

    # Extract connection details from DATABASE_URL
    # Format: postgresql://user:password@host:port/database
    if [ -z "$DATABASE_URL" ]; then
        log_error "DATABASE_URL environment variable is not set!"
        exit 1
    fi

    # Parse the DATABASE_URL
    DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:/]+).*|\1|')
    DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*:([0-9]+)/.*|\1|')

    if [ -z "$DB_PORT" ]; then
        DB_PORT=5432
    fi

    log_info "Connecting to database at $DB_HOST:$DB_PORT"

    MAX_RETRIES=30
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
            log_success "PostgreSQL is ready!"
            return 0
        fi

        RETRY_COUNT=$((RETRY_COUNT + 1))
        log_info "Waiting for PostgreSQL... (attempt $RETRY_COUNT/$MAX_RETRIES)"
        sleep 2
    done

    log_error "Failed to connect to PostgreSQL after $MAX_RETRIES attempts"
    exit 1
}

# =============================================================================
# Run database migrations
# =============================================================================
run_migrations() {
    if [ "$RUN_MIGRATIONS" != "true" ]; then
        log_info "Skipping migrations (RUN_MIGRATIONS=false)"
        return 0
    fi

    log_info "Running database migrations..."

    if alembic upgrade head; then
        log_success "Database migrations completed successfully"
    else
        log_error "Database migrations failed!"
        exit 1
    fi
}

# =============================================================================
# Seed data sources
# =============================================================================
seed_sources() {
    if [ "$SEED_SOURCES" != "true" ]; then
        log_info "Skipping source seeding (SEED_SOURCES=false)"
        return 0
    fi

    log_info "Seeding data sources..."

    if python -m scripts.seed_sources; then
        log_success "Data sources seeded successfully"
    else
        log_warning "Source seeding had issues (may be expected if already seeded)"
    fi
}

# =============================================================================
# Create required directories
# =============================================================================
setup_directories() {
    log_info "Setting up directories..."

    mkdir -p "$LOG_DIR" "$DATA_DIR"

    # Ensure proper permissions if running as root initially
    if [ "$(id -u)" = "0" ]; then
        chown -R "$APP_USER:$APP_USER" "$LOG_DIR" "$DATA_DIR"
    fi

    log_success "Directories configured"
}

# =============================================================================
# Start services
# =============================================================================
start_services() {
    log_info "Starting services..."

    # Determine run mode
    RUN_MODE="${RUN_MODE:-all}"

    case "$RUN_MODE" in
        "app")
            log_info "Starting web application only..."
            exec uvicorn admin.main:app --host 0.0.0.0 --port 7410
            ;;
        "scheduler")
            log_info "Starting scheduler only..."
            exec python -m scrapers.scheduler
            ;;
        "migrate")
            log_info "Running migrations only..."
            run_migrations
            seed_sources
            log_success "Migration complete - exiting"
            exit 0
            ;;
        "all"|"supervisor")
            log_info "Starting all services with supervisord..."
            exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
            ;;
        *)
            log_error "Unknown RUN_MODE: $RUN_MODE"
            log_info "Valid modes: all, app, scheduler, migrate"
            exit 1
            ;;
    esac
}

# =============================================================================
# Signal handlers for graceful shutdown
# =============================================================================
cleanup() {
    log_info "Received shutdown signal, cleaning up..."

    # If supervisord is running, let it handle the shutdown
    if pgrep supervisord > /dev/null 2>&1; then
        kill -TERM "$(pgrep supervisord)" 2>/dev/null || true
        sleep 2
    fi

    log_info "Shutdown complete"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGQUIT

# =============================================================================
# Main execution
# =============================================================================
main() {
    log_info "========================================"
    log_info "Patient Safety Monitor - Docker Startup"
    log_info "========================================"
    log_info "Run Mode: ${RUN_MODE:-all}"
    log_info "Environment: ${ENVIRONMENT:-development}"

    # Setup
    setup_directories

    # Wait for database
    wait_for_database

    # Run migrations (only if not in scheduler-only mode)
    if [ "${RUN_MODE:-all}" != "scheduler" ]; then
        run_migrations
        seed_sources
    fi

    # Start services
    start_services
}

# Execute main function
main "$@"
