import pytest

from workstation.config import Config
from workstation.executor import check_trade


def trade(**updates):
    return {
        "action": "buy",
        "shares": 50,
        "price": 100,
        "limit_price": 100,
        "ticker": "DEMO",
        "sector": "Industrials",
        "currency": "USD",
    } | updates


@pytest.mark.parametrize(
    "order,config,message",
    [
        (trade(limit_price=99), Config(), "Buy limit"),
        (trade(shares=101), Config(), "position size"),
        (trade(), Config(cash_floor=0.99), "Cash floor"),
        (trade(), Config(max_sector_exposure=0.01), "sector exposure"),
        (trade(action="sell"), Config(), "Short selling"),
        (trade(currency="EUR"), Config(), "currency"),
    ],
)
def test_execution_guards(order, config, message):
    with pytest.raises(ValueError, match=message):
        check_trade(order, {"cash": 100000, "positions": []}, config)


def test_sell_and_hold():
    portfolio = {
        "cash": 95000,
        "positions": [{"ticker": "DEMO", "shares": 50, "price": 100, "sector": "Industrials"}],
    }
    cash, positions = check_trade(trade(action="sell", shares=25), portfolio, Config())
    assert cash == 97500 and positions["DEMO"]["shares"] == 25
    assert check_trade(trade(action="hold", shares=0), portfolio, Config())[0] == 95000
