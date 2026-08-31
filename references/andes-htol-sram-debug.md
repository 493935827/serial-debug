# Andes HTOL SRAM And Serial Debug

Use this workflow for Andes AICE/ICEman targets where HTOL firmware or another `.adx` image must run from SRAM and the result must be verified through a serial shell. Keep the shared bridge rules from `SKILL.md`; this reference adds the target-specific download and diagnosis sequence.

## Authorization Boundary

Treat these as separate operations:

- Discovering USB devices, COM mappings, running processes, ELF metadata, and existing ICEman listeners is read-only.
- Opening a COM port can assert the adapter's default DTR/RTS state. Announce that risk before opening a candidate and omit `--reset-dtr` unless the user explicitly authorizes a reset.
- Attaching GDB halts or otherwise changes CPU execution. SRAM `load`, setting PC, reset, and resume require explicit authorization for target-state changes.
- SRAM download permission does not authorize external SPI Flash erase/program, boot-strap changes, or persistent configuration changes.

Preserve the user's AndeSight workspace, launch files, linker scripts, toolchain installation, PATH, ICEman configuration, and project build products. Use process-local PATH changes and temporary artifacts.

## Establish A Tight Serial Signal

Use one deterministic pass/fail signal throughout the session: send a harmless shell command such as `help` with the confirmed line ending, require its command echo or response plus the next prompt, and record the sender's exit status. A successful TCP send with an empty serial log proves only transmission to the bridge; it does not prove the selected COM port reaches the target UART.

For the bundled bridge:

```powershell
python "<skill-dir>\scripts\shared_serial_bridge.py" send "help" `
  --host 127.0.0.1 --tcp 8888 --newline --line-ending cr `
  --idle 1.0 --max-wait 7
```

Treat a nonzero exit as an unknown device outcome. Treat exit zero with no device bytes as a red serial round trip and continue diagnosis.

## Identify The Physical UART

1. Enumerate present PnP devices, not only `Win32_SerialPort`. Windows CIM serial enumeration can omit working FTDI ports:

```powershell
Get-PnpDevice -PresentOnly |
  Where-Object {
    $_.Class -eq 'Ports' -or
    $_.FriendlyName -match 'FTDI|AICE|USB Serial|libusbK' -or
    $_.InstanceId -match 'VID_0403|AICE'
  } |
  Select-Object Status,Class,FriendlyName,InstanceId
```

2. Correlate FTDI VID/PID, interface number, serial number, recent terminal sessions, board schematics, and source-configured baud rate. An AICE dual-channel FTDI B interface is a candidate, not proof that it is wired to the SoC UART.

3. Preserve an existing human terminal. If it owns the physical COM port, attach through its established shared layer or coordinate migration to the bridge; never kill it just to test a candidate.

4. When no terminal owns a candidate, start one bridge per candidate on distinct TCP ports, without `--reset-dtr`. Test the strongest candidate first. Stop only rejected temporary bridges after recording their port, PID, endpoint, and result.

5. A candidate is confirmed only when the complete `help` round trip returns through that bridge. A silent port is rejected even if it belongs to the same AICE enclosure.

## Inspect The ADX Before Loading

Use the matching Andes toolchain with its Cygwin runtime added only to the current process:

```powershell
$toolBin = '<andes-root>\toolchains\<toolchain>\bin'
$env:PATH = "$toolBin;<andes-root>\cygwin\bin;$env:PATH"

& "$toolBin\riscv32-elf-readelf.exe" -h -S -l '<image>.adx'
& "$toolBin\riscv32-elf-gdb.exe" -q -nx -batch '<image>.adx' `
  -ex 'set pagination off' -ex 'info files'
```

Record the entry point, section VMAs, program-header physical addresses, and expected SRAM ranges before connecting to ICEman.

### Packed-image warning

GDB `load` writes ELF segments to their physical addresses (`p_paddr`, normally the section LMA). A bootable packed image can deliberately assign different addresses:

- VMA: where the section executes;
- LMA/`PhysAddr`: where a bootloader expects the packed bytes to be stored before relocation.

If `PhysAddr != VirtAddr`, loading the packed image and then setting PC directly to the VMA entry can execute overwritten or unrelated bytes. A common signature is a correct entry immediately after `load`, followed by PC dropping to a low address and `mcause=2` (`Illegal instruction`).

Do not change the project linker script to work around this. Create a temporary SRAM-debug ELF whose load addresses equal the runtime addresses:

```powershell
& "$toolBin\riscv32-elf-objcopy.exe" `
  --change-section-lma '.nds_vector=<its-vma>' `
  --change-section-lma '.vector_table=<its-vma>' `
  --change-section-lma '.text=<its-vma>' `
  --change-section-lma '.rodata=<its-vma>' `
  --change-section-lma '.data=<its-vma>' `
  '<original>.adx' '<temp>\image-sram-debug.adx'
```

Include every allocated, nonempty section needed at runtime, including target-specific init tables, small data, stacks, vectors, loaders, or compute regions. Copy each VMA from `readelf`; never infer it from neighboring sections. NOBITS sections normally need no file payload because startup code clears them.

Run `readelf -l` on the temporary ELF and require `PhysAddr == VirtAddr` for every LOAD segment that will execute or supply runtime data. Also require the entry point and symbols to remain unchanged. Only then use it for SRAM download.

## Download And Run Through Existing ICEman

Prefer an already-running, matching ICEman instance and verify its command line, listener, and absence of another GDB client. Andes ICEman may recommend extended-remote:

```powershell
Get-CimInstance Win32_Process -Filter "Name='ICEman.exe'" |
  Select-Object ProcessId,CommandLine

Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -in 9900,9901,9902
```

After explicit SRAM/run authorization, announce the address ranges and run:

```powershell
& "$toolBin\riscv32-elf-gdb.exe" -q -nx -batch '<temp>\image-sram-debug.adx' `
  -ex 'set pagination off' `
  -ex 'set confirm off' `
  -ex 'target extended-remote localhost:9902' `
  -ex 'load' `
  -ex 'set $pc = <elf-entry>' `
  -ex 'info registers pc' `
  -ex 'x/4i $pc' `
  -ex 'detach'
```

Require all of the following before calling the download successful:

- GDB exits zero.
- `load` reports the expected section addresses and transfer size.
- PC equals the ELF entry.
- Instructions at PC match the ELF disassembly.
- Detach succeeds so the target resumes.

Do not add reset commands merely because they are common in IDE launch sequences. Use reset only when the target requires it and the user authorized that state change.

## Diagnose A Silent UART After Resume

First rerun the serial feedback command. If it stays red, briefly attach GDB, inspect, then detach so the target resumes:

```gdb
info registers pc ra sp gp mstatus mcause mepc mtval
x/8i $pc-8
bt
```

Interpret the evidence before changing another variable:

- PC in an exception path, low unmapped address, or `mcause=2`: recheck loaded bytes, LMA/VMA, entry, and disassembly.
- PC in early initialization or a polling loop: inspect that boundary before testing another COM port.
- Backtrace reaches `main -> shell_task -> ... -> uart_getc(UART_BASE)`: firmware and UART initialization are alive; a silent `help` points to the wrong host COM mapping, cabling, or RX/TX path.
- Shell responds but text is garbled: recheck baud, parity, stop bits, clock, and line ending.

Change one variable at a time. For COM candidates, preserve the running target and use a distinct bridge endpoint. For image-layout diagnosis, preserve the confirmed serial bridge.

## Completion And Reporting

The workflow is complete only when the original `help` round trip is green through the shared bridge and the next prompt is visible to both human and agent. Report:

- physical COM port, baud, framing, line ending, and shared TCP endpoint;
- bridge PID and log path;
- ICEman endpoint and GDB exit status;
- original versus temporary debug image paths;
- entry point, loaded ranges, and transfer size;
- relevant PC/backtrace evidence;
- exact command response and next prompt;
- confirmation that external Flash and persistent configuration were untouched.

Stop rejected temporary bridges and leave the confirmed shared bridge running when continued interactive debugging is desired.
