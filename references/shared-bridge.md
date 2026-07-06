# Shared Bridge Workflow

Use the bundled bridge when a human and agent need the same local serial port at the same time.

The bridge process owns the physical port. Human terminals and agent senders connect to `127.0.0.1:<tcp>`.

## Start The Bridge

```bash
python scripts/shared_serial_bridge.py bridge --port COM10 --baud 57600 --tcp 8888 --chardelay 0.005
```

On Windows, launch the bridge hidden or in a separate terminal so it keeps running.

## Human Terminal

```bash
python scripts/shared_serial_bridge.py connect --tcp 8888
```

The human can watch live output and type commands here.

## Agent Command

```bash
python scripts/shared_serial_bridge.py send "misc md 0x00000000 4" --tcp 8888 --newline
```

Use `--newline` for command shells that execute on Enter. The agent's command and device response are visible to other clients connected to the bridge.

## Coordination Rules

- Do not kill the human terminal to let the agent send a command.
- Do not open the physical COM port directly while the bridge owns it.
- If a command changes state, announce it first.
- Keep commands small and read the response before sending the next command.
- Use the bridge log when reconstructing what happened.

## Known Good Example

For `COM10` at `57600`:

```bash
python scripts/shared_serial_bridge.py bridge --port COM10 --baud 57600 --tcp 8888 --chardelay 0.005
python scripts/shared_serial_bridge.py connect --tcp 8888
python scripts/shared_serial_bridge.py send "misc md 0x00000000 4" --tcp 8888 --newline
```

Expected style of output:

```text
misc md 0x00000000 4
I/misc_TEST ... 0x00000000 :  0x342022f3
atom_io>>
```
