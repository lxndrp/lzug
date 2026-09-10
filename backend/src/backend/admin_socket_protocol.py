"""Bounded length-prefixed JSON control frames, independent of artifact streaming."""

from __future__ import annotations

import json
import socket
import struct
from time import monotonic
from typing import Any

SOCKET_PROTOCOL = 1
SOCKET_SCHEMA = 1
MAX_FRAME_BYTES = 1024 * 1024


class SocketProtocolError(Exception):
    """A safe phase and allowlisted error code for the transport boundary."""

    def __init__(self, phase: str, code: str) -> None:
        super().__init__(code)
        self.phase = phase
        self.code = code


def remaining(connection: socket.socket, deadline: float) -> None:
    """Use an absolute deadline, including partial reads and slow writers."""
    timeout = deadline - monotonic()
    if timeout <= 0:
        raise TimeoutError()
    connection.settimeout(timeout)


def _receive(connection: socket.socket, size: int, deadline: float) -> bytes:
    result = bytearray()
    while len(result) < size:
        remaining(connection, deadline)
        chunk = connection.recv(size - len(result))
        if not chunk:
            raise ConnectionError()
        result.extend(chunk)
    return bytes(result)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def read_frame(connection: socket.socket, deadline: float, limit: int) -> dict[str, Any]:
    """Reject oversize frames before allocation, duplicate keys and non-object JSON."""
    size = struct.unpack("!I", _receive(connection, 4, deadline))[0]
    if not 0 < size <= limit:
        raise SocketProtocolError("validation", "frame_invalid")
    payload = _receive(connection, size, deadline)
    try:
        value = json.loads(payload, object_pairs_hook=_object)
        if not isinstance(value, dict):
            raise ValueError()
        # Re-encoding also rejects non-finite numeric constants.
        json.dumps(value, allow_nan=False)
        return value
    except ValueError, UnicodeError, RecursionError:
        raise SocketProtocolError("validation", "frame_invalid") from None


def write_frame(connection: socket.socket, value: dict[str, Any], deadline: float) -> None:
    """Write a single bounded response with a total time budget."""
    payload = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > MAX_FRAME_BYTES:
        raise SocketProtocolError("transfer", "result_too_large")
    remaining(connection, deadline)
    connection.sendall(struct.pack("!I", len(payload)) + payload)
