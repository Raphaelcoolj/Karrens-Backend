import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from app.services.notification_service import (
    compute_signal_fingerprint,
    should_notify,
    build_notification_body,
)
from app.models.notification import (
    PushSubscriptionCreate,
    PushSubscriptionKeys,
    NotificationPayload,
)


# ──────────────────────────────────────────────
# Signal Fingerprint
# ──────────────────────────────────────────────

class TestSignalFingerprint:
    def test_identical_signals_same_fingerprint(self):
        fp1 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        fp2 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        assert fp1 == fp2

    def test_different_symbol_different_fingerprint(self):
        fp1 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        fp2 = compute_signal_fingerprint("ETHUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        assert fp1 != fp2

    def test_different_direction_different_fingerprint(self):
        fp1 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        fp2 = compute_signal_fingerprint("BTCUSD", "15m", "SHORT", 77.20, 75.80, 82.50)
        assert fp1 != fp2

    def test_different_entry_different_fingerprint(self):
        fp1 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        fp2 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.50, 75.80, 82.50)
        assert fp1 != fp2

    def test_different_sl_different_fingerprint(self):
        fp1 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        fp2 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 76.00, 82.50)
        assert fp1 != fp2

    def test_different_tp_different_fingerprint(self):
        fp1 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        fp2 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 85.00)
        assert fp1 != fp2

    def test_different_timeframe_different_fingerprint(self):
        fp1 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        fp2 = compute_signal_fingerprint("BTCUSD", "1H", "LONG", 77.20, 75.80, 82.50)
        assert fp1 != fp2

    def test_fingerprint_is_deterministic_hex(self):
        fp = compute_signal_fingerprint("EURUSD", "4H", "SHORT", 1.17342, 1.17600, 1.16500)
        assert len(fp) == 32
        assert all(c in "0123456789abcdef" for c in fp)

    def test_symbol_case_insensitive(self):
        fp1 = compute_signal_fingerprint("btcusd", "15m", "LONG", 77.20, 75.80, 82.50)
        fp2 = compute_signal_fingerprint("BTCUSD", "15m", "LONG", 77.20, 75.80, 82.50)
        assert fp1 == fp2


# ──────────────────────────────────────────────
# Notification Decision Engine
# ──────────────────────────────────────────────

class TestShouldNotify:
    def test_validated_long_with_entry(self):
        assert should_notify("VALIDATED", "LONG", 77.20, 75.80, 82.50, 3.5) is True

    def test_validated_short_with_entry(self):
        assert should_notify("VALIDATED", "SHORT", 77.20, 78.50, 72.00, 2.8) is True

    def test_no_setup_does_not_notify(self):
        assert should_notify("NO_SETUP", "NEUTRAL", None, None, None, None) is False

    def test_waiting_for_confirmation_does_not_notify(self):
        assert should_notify("WAITING_FOR_CONFIRMATION", "LONG", None, None, None, None) is False

    def test_insufficient_data_does_not_notify(self):
        assert should_notify("INSUFFICIENT_DATA", "NEUTRAL", None, None, None, None) is False

    def test_invalidated_does_not_notify(self):
        assert should_notify("INVALIDATED", "LONG", 77.20, 75.80, 82.50, 3.5) is False

    def test_neutral_direction_does_not_notify(self):
        assert should_notify("VALIDATED", "NEUTRAL", 77.20, 75.80, 82.50, 3.5) is False

    def test_no_entry_does_not_notify(self):
        assert should_notify("VALIDATED", "LONG", None, 75.80, 82.50, 3.5) is False

    def test_no_sl_does_not_notify(self):
        assert should_notify("VALIDATED", "LONG", 77.20, None, 82.50, 3.5) is False

    def test_no_tp_does_not_notify(self):
        assert should_notify("VALIDATED", "LONG", 77.20, 75.80, None, 3.5) is False

    def test_low_rr_does_not_notify(self):
        assert should_notify("VALIDATED", "LONG", 77.20, 75.80, 82.50, 0.5) is False

    def test_rr_exactly_one_notifies(self):
        assert should_notify("VALIDATED", "LONG", 77.20, 75.80, 78.20, 1.0) is True

    def test_balanced_does_not_notify(self):
        assert should_notify("NO_SETUP", "NEUTRAL", None, None, None, None) is False


# ──────────────────────────────────────────────
# Notification Body Builder
# ──────────────────────────────────────────────

class TestBuildNotificationBody:
    def test_basic_body_format(self):
        body = build_notification_body("BTCUSD", "LONG", 72, "HIGH CONVICTION", 77.20, 75.80, 82.50, 3.5)
        assert "LONG" in body
        assert "72/100" in body
        assert "HIGH CONVICTION" in body
        assert "Entry: 77.2" in body
        assert "SL: 75.8" in body
        assert "TP: 82.5" in body
        assert "RR: 1:3.5" in body

    def test_no_thousands_separators(self):
        body = build_notification_body("BTCUSD", "SHORT", 80, "EXTREME CONVICTION", 97590.00, 98500.00, 95000.00, 2.9)
        assert "97,590" not in body
        assert "98,500" not in body
        assert "95,000" not in body

    def test_short_direction(self):
        body = build_notification_body("EURUSD", "SHORT", 65, "MODERATE", 1.17342, 1.17600, 1.16500, 3.2)
        assert "SHORT" in body


# ──────────────────────────────────────────────
# Push Subscription Model
# ──────────────────────────────────────────────

class TestPushSubscriptionModel:
    def test_valid_subscription(self):
        sub = PushSubscriptionCreate(
            endpoint="https://fcm.googleapis.com/fcm/send/test123",
            keys=PushSubscriptionKeys(p256dh="testkey", auth="testauth"),
        )
        assert sub.endpoint.startswith("https://")
        assert sub.keys.p256dh == "testkey"
        assert sub.keys.auth == "testauth"

    def test_invalid_endpoint_rejected(self):
        with pytest.raises(Exception):
            PushSubscriptionCreate(
                endpoint="http://insecure.com/push",
                keys=PushSubscriptionKeys(p256dh="key", auth="auth"),
            )

    def test_https_endpoint_accepted(self):
        sub = PushSubscriptionCreate(
            endpoint="https://fcm.googleapis.com/fcm/send/abc123",
            keys=PushSubscriptionKeys(p256dh="key", auth="auth"),
        )
        assert sub.endpoint.startswith("https://")


# ──────────────────────────────────────────────
# Notification Payload Model
# ──────────────────────────────────────────────

class TestNotificationPayload:
    def test_default_payload(self):
        payload = NotificationPayload()
        assert payload.type == "TRADING_SIGNAL"
        assert payload.symbol == ""

    def test_payload_with_data(self):
        payload = NotificationPayload(
            type="TRADING_SIGNAL",
            signal_id="abc123",
            symbol="BTCUSD",
            direction="LONG",
            score=72,
            quality="HIGH CONVICTION",
            entry="77.20",
            sl="75.80",
            tp="82.50",
            rr="1:3.5",
            timeframe="15m",
            reason="IDM swept + bullish CHoCH",
        )
        assert payload.direction == "LONG"
        assert payload.entry == "77.20"
        assert payload.rr == "1:3.5"


# ──────────────────────────────────────────────
# Mocked Web Push Tests
# ──────────────────────────────────────────────

class TestSendWebPush:
    @patch("pywebpush.webpush")
    @patch("app.core.config.get_settings")
    def test_successful_send(self, mock_settings, mock_webpush):
        from app.core.config import get_settings as real_get_settings
        real_get_settings.cache_clear()
        mock_settings.return_value = MagicMock(
            VAPID_PRIVATE_KEY="test-private-key",
            VAPID_PUBLIC_KEY="test-public-key",
            VAPID_SUBJECT="mailto:test@test.com",
        )
        mock_webpush.return_value = None

        from app.services.notification_service import send_web_push
        result = asyncio.run(
            send_web_push(
                {"endpoint": "https://fcm.googleapis.com/fcm/send/test", "keys": {"p256dh": "key", "auth": "auth"}},
                {"body": "Test signal"},
            )
        )
        assert result is True

    @patch("pywebpush.webpush")
    @patch("app.core.config.get_settings")
    @patch("app.services.notification_service.get_db")
    def test_expired_subscription_deactivates(self, mock_db, mock_settings, mock_webpush):
        from app.core.config import get_settings as real_get_settings
        real_get_settings.cache_clear()
        from pywebpush import WebPushException
        mock_webpush.side_effect = WebPushException("410 Gone: subscription has been unsubscribed")
        mock_settings.return_value = MagicMock(
            VAPID_PRIVATE_KEY="test-key",
            VAPID_PUBLIC_KEY="test-pub",
            VAPID_SUBJECT="mailto:test@test.com",
        )
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock()
        mock_db_instance = MagicMock()
        mock_db_instance.__getitem__ = MagicMock(return_value=mock_collection)
        mock_db.return_value = mock_db_instance

        from app.services.notification_service import send_web_push
        result = asyncio.run(
            send_web_push(
                {"endpoint": "https://fcm.googleapis.com/fcm/send/expired", "keys": {"p256dh": "key", "auth": "auth"}},
                {"body": "test"},
            )
        )
        assert result is False

    @patch("app.core.config.get_settings")
    def test_no_vapid_keys_skips(self, mock_settings):
        from app.core.config import get_settings as real_get_settings
        real_get_settings.cache_clear()
        mock_settings.return_value = MagicMock(
            VAPID_PRIVATE_KEY="",
            VAPID_PUBLIC_KEY="",
            VAPID_SUBJECT="mailto:test@test.com",
        )

        from app.services.notification_service import send_web_push
        result = asyncio.run(
            send_web_push(
                {"endpoint": "https://test.com", "keys": {"p256dh": "k", "auth": "a"}},
                {"body": "test"},
            )
        )
        assert result is False


# ──────────────────────────────────────────────
# Duplicate Prevention
# ──────────────────────────────────────────────

class TestDuplicatePrevention:
    @patch("pywebpush.webpush")
    @patch("app.core.config.get_settings")
    @patch("app.services.notification_service.get_db")
    def test_same_signal_not_notified_twice(self, mock_db, mock_settings, mock_webpush):
        from app.core.config import get_settings as real_get_settings
        real_get_settings.cache_clear()
        mock_webpush.return_value = None
        mock_settings.return_value = MagicMock(
            VAPID_PRIVATE_KEY="test-key",
            VAPID_PUBLIC_KEY="test-pub",
            VAPID_SUBJECT="mailto:test@test.com",
        )

        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        call_count = 0

        async def fake_find_one(query):
            nonlocal call_count
            if "signal_fingerprint" in query:
                call_count += 1
                if call_count > 1:
                    return {"_id": "existing", "signal_fingerprint": "fp", "subscription_id": "sub"}
            return None

        mock_db_instance.__getitem__ = MagicMock(return_value=MagicMock(
            find_one=AsyncMock(side_effect=fake_find_one),
            find=MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=[]))),
            insert_one=AsyncMock(inserted_id="new_id"),
            update_one=AsyncMock(),
        ))

        from app.services.notification_service import dispatch_signal_notification
        result = asyncio.run(
            dispatch_signal_notification(
                symbol="BTCUSD", timeframe="15m", direction="LONG",
                entry=77.20, stop_loss=75.80, take_profit=82.50,
                risk_reward=3.5, confidence=72, quality="HIGH CONVICTION",
                reasons=["test reason"],
            )
        )
