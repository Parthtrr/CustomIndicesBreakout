import importlib
import pkgutil
import inspect
from typing import List
from pattern_helpers.base import CandlePatternHelper as PatternHelper  # Your base class all helpers inherit from

def load_helpers_from_package(package_path: str) -> List[PatternHelper]:
    """Dynamically load and instantiate all helper classes from a given package."""
    helpers = []
    package = importlib.import_module(package_path)

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package_path}.{module_name}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, PatternHelper) and obj is not PatternHelper:
                helpers.append(obj())  # instantiate the helper

    return helpers
