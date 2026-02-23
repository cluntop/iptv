#!/bin/bash

echo "Starting IPTV System setup..."

# Create necessary directories
mkdir -p data/logs data/output data/downloads

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Run health check
echo "Running system health check..."
python cli.py health

# Generate initial configuration
echo "Generating initial configuration..."
if [ ! -f config.json ]; then
    echo "config.json not found, using default configuration"
fi

echo "Setup completed successfully!"
echo ""
echo "Usage:"
echo "  python main.py          - Run main program"
echo "  python cli.py scrape    - Scrape IPTV channels"
echo "  python cli.py generate  - Generate IPTV files"
echo "  python cli.py stats     - Show statistics"
echo "  python cli.py health    - Check system health"
