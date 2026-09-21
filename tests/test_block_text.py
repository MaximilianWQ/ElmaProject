"""The block notice must quote the limit the deployment actually enforces.

``DEVICE_LIMIT`` is configurable and is what the panel is provisioned with, but
the notice hard-coded "Максимум по тарифу — 5 устройств". On a deployment where
the limit is not 5 the bot quoted a number it does not enforce — in the one
message whose entire job is justifying a revoked, non-refundable subscription.

Building the text at import time is what made it drift, so it is now rendered on
demand from the live config.
"""
import config
from app.handlers import admin


def test_quotes_the_configured_device_limit(monkeypatch):
    monkeypatch.setattr(config, "DEVICE_LIMIT", 3)
    assert "3 устройств" in admin.block_text()


def test_follows_a_different_limit(monkeypatch):
    monkeypatch.setattr(config, "DEVICE_LIMIT", 10)
    assert "10 устройств" in admin.block_text()


def test_still_points_at_support():
    assert config.SUPPORT_USERNAME in admin.block_text()
