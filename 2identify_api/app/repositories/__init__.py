"""Persistence adapters for existing 2Identify entities."""

from app.repositories.dashboard_repository import DashboardCounts, DashboardRepository
from app.repositories.user_repository import UserRepository

__all__ = ["DashboardCounts", "DashboardRepository", "UserRepository"]
