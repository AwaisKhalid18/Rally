"""M7 Notification — in-app notifications, email dispatch, retries, delivery state.

Owns  : `outbox`, `notification`
Serves: FR-10, FR-12; ASR-11, ASR-12
Never : makes a business decision; persists or logs a contact address.
Depends on: M1 Identity only, for the delivery address at send time.

No business module depends on M7. Modules append to the outbox through Platform's
`OutboxAppender` port (rule 3); the worker drives dispatch from the other side.
"""
