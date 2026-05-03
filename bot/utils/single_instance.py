# bot/utils/single_instance.py
"""
Single-instance guard using a loopback TCP socket.

Why sockets instead of PID files or OS file-locks:
  - The OS releases the port AUTOMATICALLY when the process dies, even on crash.
    No stale locks, no manual cleanup, no "file in use" scenarios.
  - Zero filesystem interaction — OneDrive, Dropbox, and git can never interfere.

Usage — bool pattern (recommended):

    instance = SingleInstance()
    if not instance.acquire():
        print("Bot already running. Exit.")
        return
    try:
        start_bot()
    finally:
        instance.release()

Usage — context manager:

    with SingleInstance():
        start_bot()   # raises SingleInstanceError if port is occupied
"""
import logging
import socket

logger = logging.getLogger(__name__)

_HOST = "127.0.0.1"
_DEFAULT_PORT = 65432


class SingleInstanceError(RuntimeError):
    """Raised by the context-manager protocol when another instance is running."""


class SingleInstance:
    """
    Loopback-socket single-instance guard.

    acquire() → bool   : True = this process now owns the lock.
                         False = another process already holds it.

    release()           : Close the socket; port freed immediately.

    Context manager     : calls acquire() / release() automatically;
                         raises SingleInstanceError on failure.
    """

    def __init__(self, port: int = _DEFAULT_PORT) -> None:
        self.port = port
        self._sock: socket.socket | None = None

    # ── Core acquire / release ─────────────────────────────────────────────────

    def acquire(self) -> bool:
        """
        Try to bind 127.0.0.1:<port>.

        Returns True  — lock acquired, this process is the sole instance.
        Returns False — port already occupied, another instance is running.

        Raises OSError only for unexpected system errors (not "address in use").
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR intentionally NOT set: we want the bind to fail when
        # another process holds the port.
        try:
            sock.bind((_HOST, self.port))
            # Not calling listen() — the bound socket is the lock only;
            # we never accept any connections.
        except OSError as exc:
            sock.close()
            # WSAEADDRINUSE (10048) on Windows, EADDRINUSE (98) on Linux,
            # EADDRINUSE (48) on macOS — all mean another instance is running.
            import errno
            if exc.errno in (errno.EADDRINUSE, 10048):
                logger.error(
                    "Another bot instance is already running (port %d is occupied).",
                    self.port,
                )
                return False
            # Any other OSError is unexpected — re-raise so the caller sees it.
            raise

        self._sock = sock
        logger.info("Single-instance lock acquired on 127.0.0.1:%d", self.port)
        return True

    def release(self) -> None:
        """Close the socket, freeing the port immediately."""
        if self._sock is not None:
            try:
                self._sock.close()
                logger.info("Single-instance lock released (port %d)", self.port)
            except Exception as exc:
                logger.debug("Error closing instance socket: %s", exc)
            finally:
                self._sock = None

    # ── Context manager ────────────────────────────────────────────────────────

    def __enter__(self) -> "SingleInstance":
        if not self.acquire():
            raise SingleInstanceError(
                f"Another bot instance is already running "
                f"(port {self.port} is occupied). "
                f"Stop the existing process and try again."
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


# Back-compat alias so existing imports of SingleInstanceLock keep working.
SingleInstanceLock = SingleInstance
