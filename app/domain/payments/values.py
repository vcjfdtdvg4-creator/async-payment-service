from enum import StrEnum


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class Status(StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
