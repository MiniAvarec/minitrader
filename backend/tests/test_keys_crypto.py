from app.keys.crypto import decrypt, encrypt


def test_round_trip():
    plain = "binance-key-abc-XYZ-123"
    token = encrypt(plain)
    assert isinstance(token, bytes)
    assert decrypt(token) == plain
