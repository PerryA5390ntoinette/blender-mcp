"""MCP server implementation for Blender integration.

This module defines the MCP (Model Context Protocol) server that exposes
Blender operations as tools callable by AI assistants.
"""

import json
import socket
import threading
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9876
BUFFER_SIZE = 4096


class BlenderConnection:
    """Manages a persistent TCP connection to the Blender addon server."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._socket: socket.socket | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Establish a connection to the Blender addon."""
        with self._lock:
            if self._socket is not None:
                return
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(10.0)
                self._socket.connect((self.host, self.port))
            except OSError as exc:
                self._socket = None
                raise ConnectionError(
                    f"Could not connect to Blender at {self.host}:{self.port}. "
                    "Make sure the Blender MCP addon is running."
                ) from exc

    def disconnect(self) -> None:
        """Close the connection to the Blender addon."""
        with self._lock:
            if self._socket is not None:
                try:
                    self._socket.close()
                except OSError:
                    pass
                finally:
                    self._socket = None

    def send_command(self, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON command to Blender and return the parsed response.

        Args:
            command: The name of the Blender command to execute.
            params: Optional dictionary of parameters for the command.

        Returns:
            Parsed JSON response from Blender.

        Raises:
            ConnectionError: If not connected or the connection is lost.
            ValueError: If the response cannot be decoded.
        """
        if self._socket is None:
            raise ConnectionError("Not connected to Blender. Call connect() first.")

        payload = json.dumps({"command": command, "params": params or {}}) + "\n"

        with self._lock:
            try:
                self._socket.sendall(payload.encode("utf-8"))
                raw = self._receive_response()
            except OSError as exc:
                self._socket = None
                raise ConnectionError("Connection to Blender was lost.") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON response from Blender: {raw!r}") from exc

    def _receive_response(self) -> str:
        """Read a newline-terminated response from the socket.

        Accumulates chunks until a newline is found, which signals the end
        of a complete JSON message from the Blender addon.
        """
        chunks: list[bytes] = []
        while True:
            chunk = self._socket.recv(BUFFER_SIZE)  # type: ignore[union-attr]
            if not chunk:
                raise OSError("Connection closed by Blender before response was complete.")
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        return b"".join(chunks).decode("utf-8").strip()
