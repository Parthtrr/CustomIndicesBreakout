import logging
import sys

def get_logger(name: str = None) -> logging.Logger:
    """
    Returns a logger with the specified name.
    If no name is provided, uses root logger.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Prevent adding multiple handlers in multi-threaded environments
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)  # You can change to INFO or WARNING
        logger.propagate = False
    return logger
