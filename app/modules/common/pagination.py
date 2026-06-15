from math import ceil
from typing import Callable, TypeVar

from fastapi import Query

T = TypeVar("T")


def pagination_params(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=100),
    search: str = Query(default=""),
):
    return {
        "page": page,
        "limit": limit,
        "search": search.strip(),
    }


def paginated_response(
    *,
    items: list[T],
    total: int,
    page: int,
    limit: int,
    serializer: Callable[[T], object] | None = None,
):
    total_pages = max(1, ceil(total / limit)) if limit else 1
    serialized_items = [serializer(item) for item in items] if serializer else items

    return {
        "items": serialized_items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
    }
