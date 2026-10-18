from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Базовый класс доменных событий."""
