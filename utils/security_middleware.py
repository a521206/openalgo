import logging

from flask import jsonify
from werkzeug.exceptions import BadHost

from database.traffic_db import IPBan, logs_session
from utils.ip_helper import get_real_ip_from_environ

logger = logging.getLogger(__name__)


class SecurityMiddleware:
    """WSGI middleware: blocks banned IPs and handles malformed Host headers."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        client_ip = get_real_ip_from_environ(environ)

        if IPBan.is_ip_banned(client_ip):
            # Session cleanup must happen here — Flask teardown won't run at WSGI level.
            logs_session.remove()
            logger.warning(f"Blocked banned IP: {client_ip}")
            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"Access Denied: Your IP has been banned"]

        try:
            return self.app(environ, start_response)
        except BadHost:
            # flask-restx re-raises BadHost inside its own error router, letting it
            # escape Flask's exception handling entirely. Catch it here and return 400.
            logger.warning(f"BadHost from {client_ip}: invalid Host header '{environ.get('HTTP_HOST', '')}'")
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"400 Bad Request: Invalid Host header"]


def init_security_middleware(app):
    app.wsgi_app = SecurityMiddleware(app.wsgi_app)

    @app.errorhandler(403)
    def handle_403(e):
        return jsonify({"error": "Access Denied"}), 403

    logger.debug("Security middleware initialized")
