"""Routes for the fairdataspace application."""

from app.routes.main import main_bp
from app.routes.fdp import fdp_bp
from app.routes.datasets import datasets_bp
from app.routes.request import request_bp

__all__ = [
    'main_bp',
    'fdp_bp',
    'datasets_bp',
    'request_bp',
]
