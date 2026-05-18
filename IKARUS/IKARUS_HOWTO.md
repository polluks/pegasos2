# BPlan Bootstrap's IKARUS Low-Level Monitor/Debugger

## Introduction

Over the years it was discovered that the Pegasos II firmware has a hidden IKARUS console. You can enter it during the early init stage (while the bootstrap is running) by pressing `ESC`, which drops you into:

```text
Entering IKARUS low level console
>?
```

Through manual experimentation, a handful of commands were identified (there is no built-in help — typing `?` just prints `#RTFM`).

A partial list was documented on the Pegasos II wiki page, but most commands remained unknown. By disassembling the bootstrap code in Ghidra, all the commands have now been fully reverse-engineered.

The actual ROM (512KB) is mapped at `0xFFF00000` as per PowerPC specs.

---

## The Basics

Most commands execute immediately on single keypress.

No Enter key is needed for:

```text
b, s, l, r, +, -, g, x, q, c, m, V, v, space, ~, z
```

Only commands that accept hex number input wait for digits:

```text
a, w, i, o
```

All letter commands are case-insensitive except `V` / `v`.

---

## State Variables

| Variable | Register | Description |
|---|---|---|
| A | r18 | Memory address for r/w/+/-/g operations |
| I | r16 | Input/data register |
| O | r11 | Output/write register |
| Mode | r17 | Access size: 0=byte, 1=short, 2=long |
| Verbose | r15 | 1=verbose, 0=quiet |
| RAM size | r20 | Total detected RAM |
| Return addr | r19 | Saved caller LR |

---

## Command Reference

### `a` — Set Address

Prompts for a hex address.

Example:

```text
>aFFF00100
```

---

### `b` — Byte Mode

Sets access size to byte (8-bit).

---

### `s` — Short Mode

Sets access size to short/word (16-bit).

---

### `l` — Long Mode

Sets access size to long/dword (32-bit).

---

### `r` — Read Memory

Reads memory at the current address.

Example:

```text
>aFFF00100
>l
>r
=4C00012C;
```

---

### `w` — Write Memory

Writes a value to memory at the current address.

Example:

```text
>aFFF00200
>b
>wAB
```

---

### `+` / `-` — Step Address

Advance or decrease the address by the current mode size.

---

### `i` — Set I Register

Sets the input/data register.

---

### `o` — Set O Register

Sets the output/write register.

---

### `g` — Go / Jump

Immediately jumps to the current address.

Example reboot jump:

```text
>aFFF00100
>g
```

---

### `x` — Exit / Reboot

Hard reboot via reset vector `0xFFF00100`.

---

### `q` — Quit

Returns to bootstrap caller and hangs.

---

### `c` — CPU Info

Displays the PowerPC PVR.

Example:

```text
=80020101;
```

---

### `m` — Memory Size

Displays detected RAM size.

Examples:

```text
=40000000;  # 1 GB
=20000000;  # 512 MB
```

---

### `V` / `v` — Verbose Mode

- `V` = verbose ON
- `v` = verbose OFF

---

### `SPACE` — Show Status

Displays current IKARUS state.

Example:

```text
=B00000000,I00,O00;
```

---

### `~` — Echo Test

Echoes the `~` character back over serial.

---

### `z` — Binary Upload Protocol

Serial upload mode.

Workflow:

1. Press `z`
2. Send `@`
3. Send 64 bytes of data
4. Send checksum byte
5. Receive ACK (`0x06`) or NAK (`0x15`)

Checksum:

```text
sum(all 64 bytes) & 0xFF
```

---

## Upload Script

Example:

```bash
python ikarus_upload.py smartfirmware.bin
```

Upload + auto-jump:

```bash
python ikarus_upload.py --addr 01000000 smartfirmware.bin --jump 01000100
```

---

## Practical Examples

### Reading Memory

```text
>aFFF00100
>l
>r
=4C00012C;
```

### Writing a Byte

```text
>a00100000
>b
>w41
>r
=41;
```

### Upload Binary

```text
>a00200000
>z
```

### Jump to Uploaded Code

```text
>a00200000
>i00000001
>o00000000
>g
```

### Resume Boot

```text
>l
>aFFF045E0
>r
=480000A1;
>g
```

---

## Notes

IKARUS runs before SmartFirmware is decompressed. The gzipped firmware remains in flash ROM (`0xFFF20040+`) until decompression to RAM at `0x01000000`.

---

## Source

Original file:

https://raw.githubusercontent.com/kas1e/pegasos2/main/IKARUS/IKARUS_HOWTO.txt
