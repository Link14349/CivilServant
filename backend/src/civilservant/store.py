import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from .config import DATA_DIR, DATABASE_PATH
from .models import StoredGame


class Base(DeclarativeBase):
    pass


class GameRecord(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    player_name: Mapped[str] = mapped_column(String(40), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    api_base: Mapped[str] = mapped_column(String(512), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    history_json: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GameStore:
    def __init__(self, database_url: Optional[str] = None) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        url = database_url or "sqlite:///{}".format(DATABASE_PATH)
        engine_kwargs = {"connect_args": {"check_same_thread": False}}
        if url == "sqlite:///:memory:":
            # FastAPI's test client handles requests in a worker thread. A static
            # pool keeps an in-memory database on one connection across threads.
            engine_kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **engine_kwargs)
        Base.metadata.create_all(self.engine)

    def create(self, game: StoredGame) -> None:
        now = datetime.now(timezone.utc)
        record = GameRecord(
            id=game.id,
            version=game.version,
            player_name=game.player_name,
            mode=game.mode,
            model=game.model,
            api_base=game.api_base,
            seed=game.seed,
            turn_index=game.turn_index,
            status=game.status,
            state_json=json.dumps(game.state, ensure_ascii=False),
            history_json=json.dumps(game.history, ensure_ascii=False),
            outcome_json=(json.dumps(game.outcome, ensure_ascii=False) if game.outcome else None),
            created_at=now,
            updated_at=now,
        )
        with Session(self.engine) as session:
            session.add(record)
            session.commit()

    def get(self, game_id: str) -> Optional[StoredGame]:
        with Session(self.engine) as session:
            record = session.scalar(select(GameRecord).where(GameRecord.id == game_id))
            if record is None:
                return None
            return self._to_model(record)

    def save(self, game: StoredGame, expected_version: int) -> bool:
        values = {
            "version": game.version,
            "turn_index": game.turn_index,
            "status": game.status,
            "state_json": json.dumps(game.state, ensure_ascii=False),
            "history_json": json.dumps(game.history, ensure_ascii=False),
            "outcome_json": json.dumps(game.outcome, ensure_ascii=False) if game.outcome else None,
            "updated_at": datetime.now(timezone.utc),
        }
        with Session(self.engine) as session:
            result = session.execute(
                update(GameRecord)
                .where(GameRecord.id == game.id, GameRecord.version == expected_version)
                .values(**values)
            )
            session.commit()
            return result.rowcount == 1

    @staticmethod
    def _to_model(record: GameRecord) -> StoredGame:
        return StoredGame(
            id=record.id,
            version=record.version,
            player_name=record.player_name,
            mode=record.mode,
            model=record.model,
            api_base=record.api_base,
            seed=record.seed,
            turn_index=record.turn_index,
            status=record.status,
            state=json.loads(record.state_json),
            history=json.loads(record.history_json),
            outcome=json.loads(record.outcome_json) if record.outcome_json else None,
        )
