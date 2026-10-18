from app.domain.ports.uow import UnitOfWork
from app.infrastructure.db.session import session_factory
from app.infrastructure.uow import SqlAlchemyUnitOfWork


def get_uow() -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session_factory)
