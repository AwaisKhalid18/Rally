"""M7's entry points.

`outbox_appender` — the implementation of Platform's `OutboxAppender` port, bound at
                    startup so a business module can append without importing M7.
`facade`          — what the worker calls to dispatch due records. Platform's worker host
                    is the only caller; no capability module may call it (rule 3).
"""
from rally.modules.notification.api import facade, outbox_appender  # noqa: F401

__all__ = ["facade", "outbox_appender"]
