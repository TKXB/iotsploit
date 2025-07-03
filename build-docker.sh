#!/bin/bash

# SAT Toolkit Docker Build Script
set -e

echo "🚀 SAT Toolkit Docker Build Script"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    print_success "Docker and Docker Compose are installed"
}

# Check system requirements
check_requirements() {
    print_status "Checking system requirements..."
    
    # Check if pyproject.toml exists
    if [ ! -f "pyproject.toml" ]; then
        print_error "pyproject.toml not found. This project requires Poetry for dependency management."
        exit 1
    fi
    
    # Check available disk space (in GB)
    available_space=$(df . | awk 'NR==2 {print int($4/1024/1024)}')
    if [ "$available_space" -lt 10 ]; then
        print_warning "Available disk space is ${available_space}GB. Recommended: 10GB+"
    fi
    
    # Check available memory (in GB)
    available_memory=$(free -g | awk 'NR==2{print $7}')
    if [ "$available_memory" -lt 4 ]; then
        print_warning "Available memory is ${available_memory}GB. Recommended: 4GB+"
    fi
    
    print_success "System requirements check completed"
}

# Build the Docker image
build_image() {
    print_status "Building SAT Toolkit Docker image..."
    
    # Check if Flutter build exists
    if [ ! -d "ui/build/web" ]; then
        print_warning "Flutter web build not found. It will be built inside Docker."
    fi
    
    # Build with Docker Compose
    if docker-compose build --no-cache; then
        print_success "Docker image built successfully"
    else
        print_error "Failed to build Docker image"
        exit 1
    fi
}

# Start the services
start_services() {
    print_status "Starting SAT Toolkit services..."
    
    if docker-compose up -d; then
        print_success "Services started successfully"
    else
        print_error "Failed to start services"
        exit 1
    fi
}

# Wait for services to be ready
wait_for_services() {
    print_status "Waiting for services to be ready..."
    
    # Wait for health check
    max_attempts=30
    attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost/health > /dev/null 2>&1; then
            print_success "All services are ready!"
            break
        fi
        
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        print_warning "Services may not be fully ready yet. Check logs with: docker-compose logs -f"
    fi
}

# Display access information
show_access_info() {
    echo ""
    echo "🌐 SAT Toolkit is now running!"
    echo "=============================="
    echo ""
    echo "Access Points:"
    echo "  📱 Web UI:        http://localhost"
    echo "  🔧 API:           http://localhost/api/"
    echo "  👤 Admin:         http://localhost/admin/"
    echo "  🔍 Health Check:  http://localhost/health"
    echo ""
    echo "Default Credentials:"
    echo "  👤 Django Admin: admin / admin123"
    echo ""
    echo "Management Commands:"
    echo "  📊 View logs:     docker-compose logs -f"
    echo "  🔄 Restart:       docker-compose restart"
    echo "  🛑 Stop:          docker-compose down"
    echo "  🗑️  Clean up:      docker-compose down -v"
    echo ""
}

# Main function
main() {
    # Parse command line arguments
    case "${1:-build}" in
        "build")
            check_docker
            check_requirements
            build_image
            start_services
            wait_for_services
            show_access_info
            ;;
        "start")
            check_docker
            start_services
            wait_for_services
            show_access_info
            ;;
        "stop")
            print_status "Stopping SAT Toolkit services..."
            docker-compose down
            print_success "Services stopped"
            ;;
        "restart")
            print_status "Restarting SAT Toolkit services..."
            docker-compose restart
            wait_for_services
            show_access_info
            ;;
        "logs")
            docker-compose logs -f
            ;;
        "clean")
            print_warning "This will remove all containers and data!"
            read -p "Are you sure? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                docker-compose down -v
                docker system prune -f
                print_success "Cleanup completed"
            else
                print_status "Cleanup cancelled"
            fi
            ;;
        "help"|"-h"|"--help")
            echo "SAT Toolkit Docker Build Script"
            echo ""
            echo "Usage: $0 [COMMAND]"
            echo ""
            echo "Commands:"
            echo "  build     Build and start the SAT Toolkit (default)"
            echo "  start     Start existing SAT Toolkit services"
            echo "  stop      Stop SAT Toolkit services"
            echo "  restart   Restart SAT Toolkit services"
            echo "  logs      Show service logs"
            echo "  clean     Remove all containers and data"
            echo "  help      Show this help message"
            echo ""
            ;;
        *)
            print_error "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@" 