#!/usr/bin/env python3
"""Shared serial bridge for human + agent access.

One process owns the physical serial port and exposes a local TCP socket.
Humans connect with the interactive client; agents connect with `send`.
"""

import argparse
import os
import select
import socket
import sys
import threading
import time
from datetime import datetime

import serial


def recv_until_idle(sock, idle_seconds, max_seconds):
    data = bytearray()
    end = time.time() + max_seconds
    last_rx = time.time()
    while time.time() < end:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            if time.time() - last_rx >= idle_seconds:
                break
            continue
        if not chunk:
            break
        data.extend(chunk)
        last_rx = time.time()
    return bytes(data)


def run_bridge(args):
    ser = serial.Serial(args.port, args.baud, timeout=0.05)
    if args.reset_dtr:
        ser.dtr = False
        time.sleep(0.3)
        ser.dtr = True
        time.sleep(2)
        ser.reset_input_buffer()

    clients = []
    lock = threading.Lock()
    logfile = args.log or f"serial_{args.port}_{datetime.now():%Y%m%d_%H%M%S}.log"

    def broadcast(data):
        with lock:
            for client in clients[:]:
                try:
                    client.sendall(data)
                except OSError:
                    clients.remove(client)

    def serial_reader():
        with open(logfile, "ab") as log:
            while True:
                try:
                    data = ser.read(4096)
                except OSError:
                    break
                if data:
                    log.write(data)
                    log.flush()
                    broadcast(data)

    def client_handler(conn):
        with lock:
            clients.append(conn)
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                if args.chardelay:
                    for byte in data:
                        ser.write(bytes([byte]))
                        time.sleep(args.chardelay)
                else:
                    ser.write(data)
        except OSError:
            pass
        finally:
            with lock:
                if conn in clients:
                    clients.remove(conn)
            conn.close()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.tcp))
    server.listen(8)
    server.settimeout(1)

    threading.Thread(target=serial_reader, daemon=True).start()
    print(
        f"bridge_start port={args.port} baud={args.baud} tcp={args.host}:{args.tcp} log={logfile}",
        flush=True,
    )
    try:
        while True:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=client_handler, args=(conn,), daemon=True).start()
    finally:
        ser.close()
        server.close()


def run_send(args):
    payload = args.data
    if args.newline:
        payload += "\r\n"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(args.socket_timeout)
    sock.connect((args.host, args.tcp))
    if payload:
        sock.sendall(payload.encode(args.encoding))
    out = recv_until_idle(sock, args.idle, args.max_wait)
    sock.close()
    sys.stdout.write(out.decode(args.encoding, errors="replace"))


def run_connect(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.05)
    sock.connect((args.host, args.tcp))
    print(f"connected {args.host}:{args.tcp}; Ctrl+C exits")

    def reader():
        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            sys.stdout.write(data.decode(args.encoding, errors="replace"))
            sys.stdout.flush()

    threading.Thread(target=reader, daemon=True).start()
    try:
        if os.name == "nt":
            import msvcrt

            buf = ""
            while True:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch == "\x03":
                        break
                    if ch == "\r":
                        sock.sendall((buf + "\r\n").encode(args.encoding))
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        buf = ""
                    elif ch in ("\b", "\x7f"):
                        buf = buf[:-1]
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    else:
                        buf += ch
                        sys.stdout.write(ch)
                        sys.stdout.flush()
                time.sleep(0.01)
        else:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if ready:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    sock.sendall(line.encode(args.encoding))
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print("\ndisconnected")


def build_parser():
    parser = argparse.ArgumentParser(description="Shared serial bridge for human + agent access")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bridge = sub.add_parser("bridge", help="own the serial port and expose a local TCP bridge")
    bridge.add_argument("--port", required=True)
    bridge.add_argument("--baud", type=int, required=True)
    bridge.add_argument("--host", default="127.0.0.1")
    bridge.add_argument("--tcp", type=int, default=8888)
    bridge.add_argument("--chardelay", type=float, default=0.0)
    bridge.add_argument("--log")
    bridge.add_argument("--reset-dtr", action="store_true")
    bridge.set_defaults(func=run_bridge)

    connect = sub.add_parser("connect", help="interactive human terminal for a running bridge")
    connect.add_argument("--host", default="127.0.0.1")
    connect.add_argument("--tcp", type=int, default=8888)
    connect.add_argument("--encoding", default="utf-8")
    connect.set_defaults(func=run_connect)

    send = sub.add_parser("send", help="agent command sender for a running bridge")
    send.add_argument("data", nargs="?", default="")
    send.add_argument("--host", default="127.0.0.1")
    send.add_argument("--tcp", type=int, default=8888)
    send.add_argument("--encoding", default="utf-8")
    send.add_argument("--newline", action="store_true")
    send.add_argument("--idle", type=float, default=0.8)
    send.add_argument("--max-wait", type=float, default=5.0)
    send.add_argument("--socket-timeout", type=float, default=0.2)
    send.set_defaults(func=run_send)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
