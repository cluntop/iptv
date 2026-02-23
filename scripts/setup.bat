@echo off
echo Starting IPTV System setup...

REM Create necessary directories
if not exist data\logs mkdir data\logs
if not exist data\output mkdir data\output
if not exist data\downloads mkdir data\downloads

REM Install dependencies
echo Installing Python dependencies...
pip install -r requirements.txt

REM Run health check
echo Running system health check...
python cli.py health

echo Setup completed successfully!
echo.
echo Usage:
echo   python main.py          - Run main program
echo   python cli.py scrape    - Scrape IPTV channels
echo   python cli.py generate  - Generate IPTV files
echo   python cli.py stats     - Show statistics
echo   python cli.py health    - Check system health
