from types import SimpleNamespace

from app.utils.notification_triggers import admin_notification_recipients


class _Query:
    def __init__(self, setting):
        self.setting = setting

    def first(self):
        return self.setting


class _Db:
    def __init__(self, setting):
        self.setting = setting

    def query(self, _model):
        return _Query(self.setting)


def test_admin_lifecycle_email_uses_only_saved_settings_recipients():
    setting = SimpleNamespace(
        admin_notification_to="operations@example.test, Operations@example.test",
        admin_notification_cc="manager@example.test",
        admin_notification_bcc="audit@example.test",
    )

    recipients = admin_notification_recipients(_Db(setting))

    assert recipients == {
        "operations@example.test",
        "manager@example.test",
        "audit@example.test",
    }
