# Shared Serial Debug

This repository owns one physical serial port in a background service. Legacy `bridge`, `connect`, `send`, and `socket://` clients continue to use the raw TCP endpoint. New GUI and machine clients use the newline-delimited JSON control endpoint.

Install on Windows with `python -m pip install -r windows/requirements.txt`. Start the managed service with `python scripts/serial_service_cli.py --port COM10 --baud 115200`, then run `python scripts/serial_gui.py` or invoke an action with `python scripts/serial_control.py status --control 8889`.

The service binds loopback only. Raw TCP defaults to port 8888 and management defaults to 8889. The management protocol is version 1, uses one JSON object per line, rejects messages over 256 KiB and sends over 64 KiB, and represents binary data as base64 in RX/TX events. `send.hex` accepts complete byte pairs such as `AA 55 01 02 FF`; malformed pairs are rejected before any write. Text uses UTF-8 by default and supports ASCII plus `none`, `cr`, `lf`, or `crlf` line endings.

An Agent must call `agent.acquire`, heartbeat at the returned interval, and pass its lease token to every mutating action. Heartbeat expiry, normal release, and `agent.takeover` invalidate the old token and cancel queued work. Takeover waits for an active byte write to stop before returning human control. A send result of `written` means the driver accepted the bytes; it does not mean the device executed the command. `unknown` must not be retried automatically.

Closing the GUI closes only its management session. `serial.close` releases the device while leaving the service and raw clients alive; it also disables automatic reconnect until `serial.open` or `serial.reconnect`. Logs are asynchronous and bounded; a log error or dropped client event is exposed in `status` and does not stop RX.

The Windows menu remains in `windows/serial_console.ps1`; `windows/serial_gui.cmd` starts the GUI. `serial_config.local.psd1` overrides the complete default configuration and is not committed. Hardware round trips still require the manual acceptance checklist: open the selected COM port, verify parameters and line endings, observe raw RX/TX, unplug and reinsert the board, release the device, and confirm control-line behavior.
