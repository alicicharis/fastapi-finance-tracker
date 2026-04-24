import uuid
from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_CATEGORIES = [
    "Food", "Transport", "Housing", "Utilities",
    "Healthcare", "Entertainment", "Shopping", "Other",
]


def seed_default_categories(connection) -> None:
    for name in DEFAULT_CATEGORIES:
        connection.execute(
            text(
                "INSERT INTO categories (id, name, is_default, user_id, created_at) "
                "VALUES (:id, :name, :is_default, NULL, :created_at) "
                "ON CONFLICT (lower(name)) WHERE user_id IS NULL DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "name": name,
                "is_default": True,
                "created_at": datetime.now(timezone.utc),
            },
        )
