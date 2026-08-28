#!/usr/bin/env python3
"""Share one serial port between an interactive terminal and command senders."""

import argparse
import os
import select
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import serial


LINE_ENDINGS = {"cr": "\r", "lf": "\n", "crlf": "\r\n"}
BACKSPACES = {"bs": "\x08", "del": "\x7f"}


def close_socket(sock):
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def open_serial(port, baud):
    # serial_for_url also accepts normal COM names and lets us test with loop://.
    return serial.serial_for_url(port, baudrate=baud, timeout=0.05)


def run_bridge(args):
    serial_port = open_serial(args.port, args.baud)
    state = {"serial": serial_port}
    serial_lock = threading.Lock()
    clients = []
    clients_lock = threading.Lock()
    stop = threading.Event()

    log_path = Path(args.log or f"serial_{args.port}_{datetime.now():%Y%m%d_%H%M%S}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def get_serial():
        with serial_lock:
            return state["serial"]

    def disconnect_clients():
        with clients_lock:
            old_clients = clients[:]
            clients.clear()
        for client in old_clients:
            close_socket(client)

    def invalidate_serial(failed_port):
        with serial_lock:
            if state["serial"] is not failed_port:
                return
            state["serial"] = None
        try:
            failed_port.close()
        except (OSError, serial.SerialException):
            pass
        disconnect_clients()
        print(f"serial_disconnected port={args.port}; retrying", flush=True)

    def reconnect_serial():
        while not stop.is_set() and get_serial() is None:
            try:
                reopened = open_serial(args.port, args.baud)
            except (OSError, serial.SerialException):
                stop.wait(1)
                continue
            with serial_lock:
                if state["serial"] is None:
                    state["serial"] = reopened
                    print(f"serial_reconnected port={args.port} baud={args.baud}", flush=True)
                    return reopened
            reopened.close()
        return get_serial()

    def broadcast(data):
        with clients_lock:
            current_clients = clients[:]
        for client in current_clients:
            try:
                client.sendall(data)
            except OSError:
                with clients_lock:
                    if client in clients:
                        clients.remove(client)
                close_socket(client)

    def serial_reader():
        with log_path.open("ab") as log_file:
            while not stop.is_set():
                current = get_serial() or reconnect_serial()
                if current is None:
                    continue
                try:
                    data = current.read(4096)
                except (OSError, serial.SerialException):
                    invalidate_serial(current)
                    continue
                if data:
                    log_file.write(data)
                    log_file.flush()
                    broadcast(data)

    def client_handler(conn):
        conn.settimeout(0.5)
        with clients_lock:
            clients.append(conn)
        try:
            while not stop.is_set():
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                current = get_serial()
                if current is None:
                    break
                try:
                    if args.chardelay:
                        for byte in data:
                            current.write(bytes([byte]))
                            time.sleep(args.chardelay)
                    else:
                        current.write(data)
                except (OSError, serial.SerialException):
                    invalidate_serial(current)
                    break
        finally:
            with clients_lock:
                if conn in clients:
                    clients.remove(conn)
            close_socket(conn)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.tcp))
    server.listen(8)
    server.settimeout(1)

    threading.Thread(target=serial_reader, daemon=True).start()
    print(
        f"bridge_start port={args.port} baud={args.baud} "
        f"tcp={args.host}:{args.tcp} log={log_path}",
        flush=True,
    )
    try:
        while True:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=client_handler, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        current = get_serial()
        if current is not None:
            current.close()
        disconnect_clients()
        server.close()


def receive_until_idle(sock, idle_seconds, max_seconds):
    output = bytearray()
    disconnected = False
    deadline = time.monotonic() + max_seconds
    last_receive = time.monotonic()
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            if time.monotonic() - last_receive >= idle_seconds:
                break
            continue
        if not chunk:
            disconnected = True
            break
        output.extend(chunk)
        last_receive = time.monotonic()
    return bytes(output), disconnected


def run_send(args):
    payload = args.data
    if args.newline:
        payload += LINE_ENDINGS[args.line_ending]
    sock = socket.create_connection((args.host, args.tcp), timeout=args.socket_timeout)
    sock.settimeout(args.socket_timeout)
    if payload:
        sock.sendall(payload.encode(args.encoding))
    output, disconnected = receive_until_idle(sock, args.idle, args.max_wait)
    close_socket(sock)
    sys.stdout.write(output.decode(args.encoding, errors="replace"))
    if disconnected:
        sys.stderr.write("[bridge] disconnected before response became idle\n")
        return 2
    return 0


def run_connect(args):
    stop = threading.Event()
    socket_lock = threading.Lock()
    socket_state = {"socket": None}
    connected_once = False

    def get_socket():
        with socket_lock:
            return socket_state["socket"]

    def set_socket(value):
        with socket_lock:
            socket_state["socket"] = value

    def drop_socket(failed_socket):
        with socket_lock:
            if socket_state["socket"] is failed_socket:
                socket_state["socket"] = None
        close_socket(failed_socket)

    def send_bytes(data):
        current = get_socket()
        if current is None:
            print("\n[bridge] disconnected; input discarded", flush=True)
            return
        try:
            current.sendall(data)
        except OSError:
            drop_socket(current)
            print("\n[bridge] connection lost; reconnecting", flush=True)

    def translate_windows_key(first_char, get_char):
        if first_char == "\r":
            return LINE_ENDINGS[args.line_ending].encode(args.encoding)
        if first_char == "\t":
            return b"\t"
        if first_char in ("\b", "\x7f"):
            return BACKSPACES[args.backspace_mode].encode(args.encoding)
        if first_char in ("\x00", "\xe0"):
            second = get_char()
            return {
                "H": b"\x1b[A", "P": b"\x1b[B", "K": b"\x1b[D", "M": b"\x1b[C",
                "G": b"\x1b[H", "O": b"\x1b[F", "S": b"\x1b[3~",
            }.get(second, b"")
        return first_char.encode(args.encoding)

    def reader():
        nonlocal connected_once
        while not stop.is_set():
            current = get_socket()
            if current is None:
                try:
                    current = socket.create_connection((args.host, args.tcp), timeout=1)
                except OSError:
                    stop.wait(1)
                    continue
                current.settimeout(0.05)
                set_socket(current)
                state = "reconnected" if connected_once else "connected"
                connected_once = True
                print(f"{state} {args.host}:{args.tcp}; Ctrl+C exits", flush=True)
            try:
                data = current.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                data = b""
            if not data:
                drop_socket(current)
                if not stop.is_set():
                    print("\n[bridge] disconnected; reconnecting", flush=True)
                    stop.wait(1)
                continue
            sys.stdout.write(data.decode(args.encoding, errors="replace"))
            sys.stdout.flush()

    threading.Thread(target=reader, daemon=True).start()
    try:
        if os.name == "nt":
            import msvcrt

            while True:
                if msvcrt.kbhit():
                    char = msvcrt.getwch()
                    if char == "\x03":
                        break
                    send_bytes(translate_windows_key(char, msvcrt.getwch))
                time.sleep(0.01)
        else:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    continue
                data = os.read(sys.stdin.fileno(), 1024)
                if not data or b"\x03" in data:
                    break
                data = data.replace(b"\x7f", BACKSPACES[args.backspace_mode].encode())
                if args.line_ending != "lf":
                    data = data.replace(b"\n", LINE_ENDINGS[args.line_ending].encode())
                send_bytes(data)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        close_socket(get_socket())
        print("\ndisconnected")


def build_parser():
    parser = argparse.ArgumentParser(description="Shared serial bridge")
    commands = parser.add_subparsers(dest="command", required=True)

    bridge = commands.add_parser("bridge", help="own a serial port and expose TCP")
    bridge.add_argument("--port", required=True)
    bridge.add_argument("--baud", type=int, required=True)
    bridge.add_argument("--host", default="127.0.0.1")
    bridge.add_argument("--tcp", type=int, default=8888)
    bridge.add_argument("--chardelay", type=float, default=0.0)
    bridge.add_argument("--log")
    bridge.set_defaults(func=run_bridge)

    connect = commands.add_parser("connect", help="open an interactive terminal")
    connect.add_argument("--host", default="127.0.0.1")
    connect.add_argument("--tcp", type=int, default=8888)
    connect.add_argument("--encoding", default="utf-8")
    connect.add_argument("--line-ending", choices=LINE_ENDINGS, default="cr")
    connect.add_argument("--backspace-mode", choices=BACKSPACES, default="bs")
    connect.set_defaults(func=run_connect)

    send = commands.add_parser("send", help="send one command through the bridge")
    send.add_argument("data", nargs="?", default="")
    send.add_argument("--host", default="127.0.0.1")
    send.add_argument("--tcp", type=int, default=8888)
    send.add_argument("--encoding", default="utf-8")
    send.add_argument("--newline", action="store_true")
    send.add_argument("--line-ending", choices=LINE_ENDINGS, default="cr")
    send.add_argument("--idle", type=float, default=0.8)
    send.add_argument("--max-wait", type=float, default=5.0)
    send.add_argument("--socket-timeout", type=float, default=0.2)
    send.set_defaults(func=run_send)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        result = args.func(args)
    except KeyboardInterrupt:
        result = 130
    if isinstance(result, int):
        raise SystemExit(result)


if __name__ == "__main__":
    main()
