#!/usr/bin/env sh

# The CLI is executed from the unchanged product image. Keys and artifacts remain
# in the disposable helper container and never enter the backend.
# Callers supply image, temporary_directory, container, socket_volume and stage.

lzug_prepare_operator_socket() {
    # Prevent Docker from replacing prepared ownership when an empty volume
    # is mounted again: the image directory intentionally belongs to root.
    docker volume create "$socket_volume" >/dev/null
    docker run --rm --user 0:0 --network none --read-only \
        --cap-drop ALL --cap-add CHOWN --cap-add FOWNER \
        --security-opt no-new-privileges:true \
        --mount "type=volume,source=$socket_volume,target=/run/lzug-admin,volume-nocopy" \
        --entrypoint sh "$image" -c \
        'chown 10001:10001 /run/lzug-admin && chmod 0750 /run/lzug-admin'
}

lzug_operator_cli() {
    cli_status=0
    printf '%s\n' "$stage" >"$temporary_directory/last-cli.stage"
    set -- --entrypoint /usr/local/bin/lzug-admin "$image" "$@"
    if [ "${operator_socket_ready:-false}" = true ]; then
        # SO_PEERCRED must see a positive PID. Sibling PID namespaces hide it.
        set -- --pid "container:$container" "$@"
    fi
    # The host owns the private artifact directory. The primary operator GID
    # authorizes the socket peer without granting access to backend persistence.
    docker run --rm --interactive --network none --read-only \
        --user "$(id -u):10001" --cap-drop ALL \
        --security-opt no-new-privileges:true \
        --mount "type=volume,source=$socket_volume,target=/run/lzug-admin,readonly,volume-nocopy" \
        --mount "type=bind,source=$temporary_directory,target=$temporary_directory" \
        "$@" >"$temporary_directory/last-cli.json" \
        2>"$temporary_directory/last-cli.stderr" || cli_status=$?
    printf '%s\n' "$cli_status" >"$temporary_directory/last-cli.status"
    if [ -f "$temporary_directory/backup.agekey" ] &&
        grep -F -f "$temporary_directory/backup.agekey" \
            "$temporary_directory/last-cli.json" "$temporary_directory/last-cli.stderr" >/dev/null; then
        echo "CLI output exposed the private recipient key: stage=$stage" >&2
        return 1
    fi
    cat "$temporary_directory/last-cli.json"
    return "$cli_status"
}

lzug_expect_operator_exit() {
    if [ "$1" -ne "$2" ]; then
        echo "Operator contract exit mismatch: stage=$stage expected=$1 actual=$2" >&2
        return 1
    fi
}

lzug_assert_operator_socket() {
    docker exec "$container" python -c '
import os
import stat
from pathlib import Path

assert (os.geteuid(), os.getegid()) == (10001, 10001)
for path, kind, mode in (
    (Path("/run/lzug-admin"), stat.S_ISDIR, 0o750),
    (Path("/run/lzug-admin/admin.sock"), stat.S_ISSOCK, 0o660),
):
    info = path.lstat()
    assert kind(info.st_mode), path.name
    assert (info.st_uid, info.st_gid) == (10001, 10001), path.name
    assert stat.S_IMODE(info.st_mode) == mode, path.name
print("Operator admin socket: uid=10001 gid=10001 directory=0750 socket=0660")
'
    operator_socket_ready=true
}

lzug_operator_failure() {
    echo "Operator container contract failed: stage=$stage exit=$1 image=$image" >&2
    echo "Reproduce: $0 $image (same checkout; Linux CLI matching the image architecture)" >&2
    # Only structural fields, never raw responses, stderr, environment or logs:
    # failures may themselves contain a leaked key, invitation or account data.
    docker logs "$container" >"$temporary_directory/backend.log" 2>&1 || true
    python3 "$root_dir/scripts/operator-smoke-diagnostics.py" "$temporary_directory" >&2 || true
    docker inspect --format \
        'Backend state={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} user={{.Config.User}} readonly={{.HostConfig.ReadonlyRootfs}}' \
        "$container" >&2 || true
    docker exec "$container" python -c '
import stat
from pathlib import Path
for path in (Path("/run/lzug-admin"), Path("/run/lzug-admin/admin.sock")):
    try:
        info = path.lstat()
    except OSError as error:
        print(f"{path.name}: unavailable errno={error.errno}")
    else:
        print(f"{path.name}: uid={info.st_uid} gid={info.st_gid} mode={stat.S_IMODE(info.st_mode):04o} socket={stat.S_ISSOCK(info.st_mode)}")
' >&2 || true
    docker exec "$container" python -c '
import socket
from time import monotonic
from backend.admin_socket_protocol import read_frame, write_frame
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        deadline = monotonic() + 3
        connection.settimeout(3)
        connection.connect("/run/lzug-admin/admin.sock")
        write_frame(connection, {"type": "hello", "protocol": 1, "schema": 1}, deadline)
        read_frame(connection, deadline, 1048576)
        write_frame(connection, {"version": 1, "command": "config", "arguments": {}}, deadline)
        response = read_frame(connection, deadline, 1048576)
        runtime = response["response"]["result"]["runtime"]
        state = runtime["state"]
        assert state in {"stopped", "initializing", "ready", "maintenance", "migration_required", "migrating", "error", "stopping"}
        print("Backend runtime state=" + state)
except Exception as error:
    print("Runtime diagnostic unavailable: " + type(error).__name__)
' >&2 || true
}
