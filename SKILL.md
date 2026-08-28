---
name: serial-debug
description: Shared serial console debugging for Codex and Claude Code. Use when a human and an agent need concurrent access to the same UART, RS-232, USB-serial, or COM port with live human viewing/input, agent command injection, logging, prompt synchronization, and safe recovery from desync or timeouts. Prefer the bundled TCP bridge on Windows/local setups; use Conserver when it is installed and already manages the serial console.
---

# Serial Debug

## Operating Rule

Use a shared middle layer whenever the human and agent both need the same live serial console. The middle layer owns the physical port; humans and agents connect to the middle layer. Do not close the human terminal just to let the agent send commands.

Use the bundled TCP bridge for local Windows/COM-port work. Use Conserver when it is already installed or the environment needs a managed multi-user console server.

## Workflow

1. For local Windows work where the human wants manual start/stop control, use the bundled menu:

```powershell
windows\serial_console.cmd
```

Configure `windows/serial_config.psd1`, then use the menu to start the bridge, open a terminal, inspect status, or stop and release the COM port. Exiting the menu does not stop an already-running bridge.

2. For command-line-only work, start the bundled bridge directly. The bridge owns the physical port and exposes a local TCP socket:

```bash
python scripts/shared_serial_bridge.py bridge --port COM10 --baud 57600 --tcp 8888 --chardelay 0.005
```

3. Open the human terminal against the bridge:

```bash
python scripts/shared_serial_bridge.py connect --tcp 8888
```

The bundled bridge defaults to `CR` for Enter because many embedded shells treat `CRLF` as two submissions and print the prompt twice.

4. Have the agent send through the same bridge:

```bash
python scripts/shared_serial_bridge.py send "misc md 0x00000000 4" --tcp 8888 --newline
```

5. Report command output from the shared channel. The human should be able to see the agent's command and device response in the terminal.

6. If Conserver is available, use its client instead of the bundled bridge:

```bash
conserver -V
console -V
console -s <CONSOLE>
console -a <CONSOLE>
```

7. Use prompt history and replay options to resynchronize after boot noise, resets, or missed output:

```bash
console -A <CONSOLE>
console -F <CONSOLE>
console -S <CONSOLE>
```

## References

- Read `references/shared-bridge.md` for the bundled bridge workflow.
- Read `windows/README.md` for the user-controlled Windows menu.
- Read `references/conserver.md` for Conserver workflow, access modes, and coordination rules.
- Read `references/console-client.md` for Conserver client command details.
- Read `references/hardware-safety.md` before changing baud, wiring, voltage levels, RTS, DTR, reset/boot lines, or any access mode that can reset the target.
- Read `references/troubleshooting.md` when a command fails, times out, loses sync, or two users collide on write access.

## Reporting

Report the shared endpoint, physical port, baud rate, command, exit status, and relevant output excerpt. If no hardware is connected, say that only bridge/client discovery was verified and mark device round-trip validation as manual.
