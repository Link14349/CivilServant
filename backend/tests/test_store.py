from civilservant.engine import create_game
from civilservant.store import GameStore


def test_store_uses_optimistic_versioning() -> None:
    store = GameStore("sqlite:///:memory:")
    game = create_game(
        player_name="测试",
        mode="template",
        model="deepseek-v4-flash",
        api_base="https://api.deepseek.com",
        seed=99,
    )
    store.create(game)

    loaded = store.get(game.id)
    assert loaded is not None
    loaded.version = 2

    assert store.save(loaded, expected_version=1)
    assert not store.save(loaded, expected_version=1)

