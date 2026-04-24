#!/usr/bin/env python3
"""
ikarus_upload.py - Upload binary to Pegasos II via IKARUS 'z' protocol

Workflow:
  1. Power on Pegasos II, press ESC to enter IKARUS
  2. Close PuTTY (release COM port)
  3. Run: python ikarus_upload.py smartfirmware.bin
  4. Open PuTTY again, type: >a01000100 >g

  Or to jump automatically (no PuTTY needed):
  3. Run: python ikarus_upload.py smartfirmware.bin --jump 01000100
     Script uploads, jumps, and shows serial output. Ctrl+C to quit.

Requires: pip install pyserial
"""

import sys
import time
import struct
import argparse
import serial


def drain(ser):
    """Read and discard any pending serial data."""
    time.sleep(0.05)
    while ser.in_waiting:
        ser.read(ser.in_waiting)
        time.sleep(0.01)


def send_ikarus_cmd(ser, char):
    """Send a single-char IKARUS command."""
    ser.write(char.encode('ascii'))
    time.sleep(0.05)
    drain(ser)


def send_hex_value(ser, hex_str):
    """Send hex digits followed by CR to terminate input."""
    for ch in hex_str:
        ser.write(ch.encode('ascii'))
        time.sleep(0.01)
    ser.write(b'\r')
    time.sleep(0.05)
    drain(ser)


def send_block(ser, block, checksum):
    """Send one 64-byte block. Returns True on ACK, False on NAK/error."""
    # Send '@' + 64 data bytes + checksum as one chunk.
    # IKARUS echoes '@' then reads 64+1 bytes, then sends ACK/NAK.
    # So we expect 2 bytes back: echo '@' (0x40) + ACK (0x06) or NAK (0x15).
    packet = b'@' + block + bytes([checksum])
    ser.write(packet)
    ser.flush()

    # Read 2 bytes: '@' echo + ACK/NAK
    resp = ser.read(2)
    if len(resp) < 2:
        return None  # timeout
    # resp[0] should be '@' echo, resp[1] should be ACK or NAK
    return resp[1] == 0x06


def passthrough(ser):
    """Pass serial output to stdout until Ctrl+C."""
    print("--- Serial output (Ctrl+C to quit) ---")
    try:
        while True:
            n = ser.in_waiting
            if n > 0:
                data = ser.read(n)
                for b in data:
                    if b == 0x0D:
                        sys.stdout.write('\r')
                    elif b == 0x0A:
                        sys.stdout.write('\n')
                    elif b == 0x09:
                        sys.stdout.write('\t')
                    elif 0x20 <= b < 0x7F:
                        sys.stdout.write(chr(b))
                sys.stdout.flush()
            else:
                time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n--- Disconnected ---")


def main():
    parser = argparse.ArgumentParser(
        description='Upload binary to Pegasos II via IKARUS z protocol')
    parser.add_argument('file', help='Binary file to upload')
    parser.add_argument('--port', default='COM3',
                        help='Serial port (default: COM3)')
    parser.add_argument('--baud', type=int, default=115200,
                        help='Baud rate (default: 115200)')
    parser.add_argument('--addr', default='01000000',
                        help='Destination address in hex (default: 01000000)')
    parser.add_argument('--jump', default=None, metavar='ADDR',
                        help='Jump to ADDR after upload and show serial output '
                             '(hex, e.g. 01000100)')
    args = parser.parse_args()

    # Read file
    try:
        with open(args.file, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}")
        sys.exit(1)

    file_size = len(data)

    # Pad to 64-byte boundary
    if len(data) % 64 != 0:
        data += b'\x00' * (64 - len(data) % 64)

    total_blocks = len(data) // 64

    # Read first 4 bytes for verification hint
    first_dword = struct.unpack('>I', data[0:4])[0]

    print(f"File:        {args.file}")
    print(f"Size:        {file_size} bytes ({total_blocks} blocks)")
    print(f"Destination: 0x{args.addr.upper()}")
    if args.jump:
        print(f"Jump to:     0x{args.jump.upper()}")
    print()

    # Open serial
    print(f"Opening {args.port} at {args.baud} baud...")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=5)
    except serial.SerialException as e:
        print(f"Error: {e}")
        print("Close PuTTY first to release the COM port.")
        sys.exit(1)

    time.sleep(0.2)

    # Check IKARUS is alive (echo test)
    while True:
        print("Checking IKARUS (~ echo test)...")
        drain(ser)
        ser.write(b'~')
        time.sleep(0.2)
        n = ser.in_waiting
        if n > 0:
            resp = ser.read(n)
            if b'~' in resp:
                print("IKARUS responding OK")
                break
            else:
                print("WARNING: Got response but no '~' echo")
                break
        print("WARNING: No response. IKARUS might not be active.")
        print("Try again? (y/n) ", end='', flush=True)
        if sys.platform == 'win32':
            import msvcrt
            ch = msvcrt.getch().decode('ascii', errors='ignore').lower()
        else:
            import tty, termios
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1).lower()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print(ch)
        if ch != 'y':
            print("Aborted.")
            ser.close()
            sys.exit(1)

    # Set long mode and destination address
    print(f"Setting long mode, address 0x{args.addr.upper()}...")
    send_ikarus_cmd(ser, 'l')
    send_ikarus_cmd(ser, 'a')
    send_hex_value(ser, args.addr)

    # Enter upload mode
    print("Entering upload mode (z)...")
    send_ikarus_cmd(ser, 'z')
    time.sleep(0.1)
    drain(ser)

    # Upload blocks
    print(f"Uploading {file_size} bytes...")
    retries = 0
    start_time = time.time()

    for i in range(total_blocks):
        block = data[i * 64 : (i + 1) * 64]
        checksum = sum(block) & 0xFF

        ok = False
        for attempt in range(10):
            result = send_block(ser, block, checksum)
            if result is True:
                ok = True
                break
            elif result is False:
                # NAK - retry
                retries += 1
                time.sleep(0.01)
                continue
            else:
                # Timeout
                print(f"\nFATAL: Timeout at block {i} (attempt {attempt+1})")
                ser.close()
                sys.exit(1)

        if not ok:
            print(f"\nFATAL: Block {i} failed after 10 attempts")
            ser.close()
            sys.exit(1)

        if (i + 1) % 100 == 0 or i == total_blocks - 1:
            pct = (i + 1) * 100 // total_blocks
            elapsed = time.time() - start_time
            bps = ((i + 1) * 64) / elapsed if elapsed > 0 else 0
            eta = (total_blocks - i - 1) * 64 / bps if bps > 0 else 0
            print(f"\r  {i+1}/{total_blocks} ({pct}%)"
                  f"  {bps:.0f} B/s  ETA {eta:.0f}s   ", end='', flush=True)

    elapsed = time.time() - start_time
    print(f"\n  Done in {elapsed:.1f}s, {retries} retries")

    # Exit upload mode
    ser.write(b'\n')
    time.sleep(0.1)
    drain(ser)

    if args.jump:
        # Set jump address and go
        print(f"\nJumping to 0x{args.jump.upper()}...")
        send_ikarus_cmd(ser, 'a')
        send_hex_value(ser, args.jump)
        ser.write(b'g')
        ser.flush()
        time.sleep(0.3)

        # Show serial output from booting firmware
        passthrough(ser)
        ser.close()
    else:
        ser.close()
        print()
        print("=" * 60)
        print("Upload complete! Now open PuTTY and do:")
        print()
        print(f"  Verify:  >l  >a{args.addr.upper()}  >r  -- should show ={first_dword:08X};")
        print(f"  Run:     >a<entry_point>  >g")
        print("=" * 60)


if __name__ == '__main__':
    main()
