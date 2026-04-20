from flask_socketio import SocketIO

# Disabled eventlet to prevent greenlet threading errors
# Use sync/threading mode - eventlet conflicts are handled separately
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    ping_timeout=10,
    ping_interval=5,
    logger=False,
    engineio_logger=False,
)
