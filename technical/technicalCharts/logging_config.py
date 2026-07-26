import logging

# Configure logging (only once)
logging.basicConfig(
    filename="app.log",  # Single log file for the entire application
    level=logging.INFO,  # Log all levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Create a logger function that all modules can use
def get_logger(name):
    return logging.getLogger(name)
