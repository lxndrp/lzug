"""Small SQLAlchemy CRUD adapter used only inside repository-owned sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import Resource, model_to_dict


class Store:
    """SQLAlchemy-backed CRUD adapter kept behind repositories.

    ``Store`` flushes changes so callers can use generated values immediately,
    but it never commits or rolls back. The caller that opened
    :func:`backend.database.session_scope` owns the transaction boundary.
    """

    def __init__(self, session: Session):
        self.session = session

    def all(self, resource: Resource) -> list[dict[str, Any]]:
        return self.where(resource)

    def where(self, resource: Resource, **filters: Any) -> list[dict[str, Any]]:
        statement = select(resource.model)
        statement = self._filter(statement, resource, filters)
        statement = self._order(statement, resource)
        rows = self.session.scalars(statement).all()
        return [model_to_dict(row, resource) for row in rows]

    def first(self, resource: Resource, **filters: Any) -> dict[str, Any] | None:
        statement = select(resource.model)
        statement = self._filter(statement, resource, filters)
        statement = self._order(statement, resource)
        row = self.session.scalars(statement).first()
        return model_to_dict(row, resource) if row else None

    def get(self, resource: Resource, resource_id: int) -> dict[str, Any] | None:
        row = self.session.get(resource.model, resource_id)
        return model_to_dict(row, resource) if row else None

    def create(self, resource: Resource, values: dict[str, Any]) -> dict[str, Any]:
        """Add and flush a model after accepting only writable resource fields.

        The returned dictionary reflects the flushed row, not a committed
        transaction. An enclosing repository or service may still roll this
        write back.
        """
        row = resource.model(**self._payload(resource, values))
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return model_to_dict(row, resource)

    def update(
        self,
        resource: Resource,
        resource_id: int,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Apply writable fields, refresh timestamps, and flush without commit.

        Returns ``None`` for an absent row; invalid field names raise
        ``ValueError`` before any mutation is flushed.
        """
        row = self.session.get(resource.model, resource_id)
        if row is None:
            return None
        for field, value in self._payload(resource, values).items():
            setattr(row, field, value)
        if hasattr(row, "updated_at"):
            row.updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
        self.session.flush()
        self.session.refresh(row)
        return model_to_dict(row, resource)

    def delete(self, resource: Resource, resource_id: int) -> bool:
        row = self.session.get(resource.model, resource_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    def delete_where(self, resource: Resource, **filters: Any) -> int:
        self._validate_fields(resource, filters)
        statement = delete(resource.model)
        for field, value in filters.items():
            statement = statement.where(getattr(resource.model, field) == value)
        result = self.session.execute(statement)
        return int(result.rowcount or 0)

    def count(self, resource: Resource, **filters: Any) -> int:
        statement = select(func.count()).select_from(resource.model)
        statement = self._filter(statement, resource, filters)
        return int(self.session.scalar(statement) or 0)

    def grouped_counts(
        self,
        resource: Resource,
        group_field: str,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        if group_field not in resource.fields:
            raise ValueError(f"Unknown group field: {group_field}")
        group_column = getattr(resource.model, group_field)
        statement = (
            select(group_column, func.count().label("count"))
            .select_from(resource.model)
            .group_by(group_column)
            .order_by(group_column)
        )
        statement = self._filter(statement, resource, filters)
        return [
            {group_field: value, "count": int(count)}
            for value, count in self.session.execute(statement)
        ]

    def _filter(self, statement, resource: Resource, filters: dict[str, Any]):
        self._validate_fields(resource, filters)
        for field, value in filters.items():
            statement = statement.where(getattr(resource.model, field) == value)
        return statement

    def _order(self, statement, resource: Resource):
        for field in resource.order_by:
            descending = field.startswith("-")
            column = getattr(resource.model, field[1:] if descending else field)
            statement = statement.order_by(column.desc() if descending else column)
        return statement

    def _payload(self, resource: Resource, values: dict[str, Any]) -> dict[str, Any]:
        return {field: values[field] for field in resource.writable_fields if field in values}

    def _validate_fields(self, resource: Resource, values: dict[str, Any]) -> None:
        known_fields = set(resource.readable_fields)
        for field in values:
            if field not in known_fields:
                raise ValueError(f"Unknown field for {resource.model.__tablename__}: {field}")
