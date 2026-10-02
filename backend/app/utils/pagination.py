"""Generic pagination utilities for list endpoints."""

from __future__ import annotations

from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PaginationParams(BaseModel):
    """Common query-parameter schema for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PagedResponse(BaseModel, Generic[T]):
    """Standard envelope for paginated list responses."""

    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

    model_config = {"arbitrary_types_allowed": True}


def make_page(
    items: List[T],
    total: int,
    params: PaginationParams,
) -> PagedResponse[T]:
    """Build a ``PagedResponse`` from a query result and pagination params."""
    total_pages = max(1, (total + params.page_size - 1) // params.page_size)
    return PagedResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
        has_next=params.page < total_pages,
        has_prev=params.page > 1,
    )
