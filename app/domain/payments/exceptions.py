import uuid


class PaymentError(Exception): ...


class PaymentNotFoundError(PaymentError):
    def __init__(self, payment_id: uuid.UUID) -> None:
        super().__init__(f"Payment {payment_id} not found")
        self.payment_id = payment_id


class DuplicateIdempotencyKeyError(PaymentError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Duplicate idempotency key: {key}")
        self.key = key


class IdempotencyConflictError(PaymentError):
    def __init__(self, key: str) -> None:
        super().__init__("Idempotency-Key was already used with a different request body")
        self.key = key
