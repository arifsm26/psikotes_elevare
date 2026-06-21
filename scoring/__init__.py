# backend/scoring/__init__.py

from typing import Dict, Type
from .base import BaseScorer
from .ist import ISTScorer
from .papi import PapikostikScorer

SCORER_REGISTRY: Dict[str, Type[BaseScorer]] = {
    'ist': ISTScorer,
    'papi': PapikostikScorer,
    'default': BaseScorer, # Fallback
}

def get_scorer(module_name: str) -> Type[BaseScorer]:
    """Mengembalikan class scorer sesuai module_name. Jika tidak ada, gunakan BaseScorer."""
    return SCORER_REGISTRY.get(module_name, BaseScorer)
