"""Linux pathname socket ownership; never follow or replace unexpected files."""

from __future__ import annotations

import errno
import os
import socket
import stat
import sys
from fcntl import LOCK_EX, LOCK_NB, flock
from pathlib import Path


class SocketSecurityError(RuntimeError):
    """Safe startup failure without exposing paths or system exception details."""

    def __init__(self) -> None:
        super().__init__("Admin socket security check failed")


class SocketPath:
    """Pin and lock a private runtime directory for the complete listener lifetime.

    Only root and the service UID are trusted to modify ancestors. A root-owned
    sticky ancestor (e.g. /tmp) is safe when followed by an owned private child.
    Operators have search permission but cannot replace directory entries.
    """

    def __init__(self, directory: Path, gid: int) -> None:
        self.directory = directory
        self.gid = gid
        self.fd: int | None = None
        self.inode: tuple[int, int] | None = None

    @property
    def address(self) -> str:
        """Bind through the pinned descriptor, avoiding global cwd and umask changes."""
        return f"/proc/self/fd/{self.fd}/admin.sock"

    def open(self) -> None:
        """Validate every component without following symlinks, then lock the leaf."""
        if sys.platform != "linux" or not self.directory.is_absolute():
            raise SocketSecurityError()
        parts = self.directory.parts[1:]
        if not parts or ".." in parts:
            raise SocketSecurityError()
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
                info = os.fstat(fd)
                sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
                if info.st_uid not in {0, os.geteuid()} or (
                    info.st_mode & 0o022 and not sticky_root
                ):
                    raise SocketSecurityError()
            info = os.fstat(fd)
            if (
                info.st_uid != os.geteuid()
                or info.st_gid != self.gid
                or stat.S_IMODE(info.st_mode) != 0o750
            ):
                raise SocketSecurityError()
            flock(fd, LOCK_EX | LOCK_NB)
            self.fd = fd
        except OSError, SocketSecurityError:
            os.close(fd)
            raise SocketSecurityError() from None

    def _stat(self) -> os.stat_result:
        return os.stat("admin.sock", dir_fd=self.fd, follow_symlinks=False)

    def _validate_socket(self, info: os.stat_result) -> None:
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_gid != self.gid
            or stat.S_IMODE(info.st_mode) != 0o660
        ):
            raise SocketSecurityError()

    def bind(self, listener: socket.socket) -> None:
        """Replace only an owned, inaccessible stale socket under the directory lock."""
        try:
            info = self._stat()
        except FileNotFoundError:
            pass
        else:
            self._validate_socket(info)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.2)
                try:
                    probe.connect(self.address)
                except OSError as error:
                    if error.errno != errno.ECONNREFUSED:
                        raise SocketSecurityError() from None
                else:
                    raise SocketSecurityError()
            current = self._stat()
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise SocketSecurityError()
            os.unlink("admin.sock", dir_fd=self.fd)
        listener.bind(self.address)
        info = self._stat()
        self.inode = (info.st_dev, info.st_ino)
        os.chown("admin.sock", os.geteuid(), self.gid, dir_fd=self.fd, follow_symlinks=False)
        os.chmod(self.address, 0o660)
        self._validate_socket(self._stat())

    def close(self) -> None:
        """Remove only our own inode, retaining replacement files untouched."""
        if self.fd is None:
            return
        try:
            if self.inode is not None:
                try:
                    info = self._stat()
                except FileNotFoundError:
                    pass
                else:
                    if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == self.inode:
                        os.unlink("admin.sock", dir_fd=self.fd)
        finally:
            os.close(self.fd)
            self.fd = None
            self.inode = None
