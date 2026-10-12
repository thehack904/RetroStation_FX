from __future__ import annotations

import struct


# ErsatzTV Legacy Script Graphics Packet v1
#
# Header, exactly 11 bytes:
#
#   uint32 magic       big-endian
#   uint16 version     big-endian
#   uint8  type
#   uint32 payload_len big-endian
#
# ErsatzTV source constant:
#   EtvGraphicsMagic = 0x47565445
#
# ScriptPayloadType:
#   0 = Full
#   1 = Repeat
#   2 = Rectangles
#
# RSFX uses Rectangles because its renderer naturally produces a
# positioned BGRA region instead of an entire output-sized frame.

MAGIC = 0x47565445
VERSION = 1

FULL = 0
REPEAT = 1
CLEAR = 2
RECTANGLES = 3

HEADER = struct.Struct(">IHBI")


def _packet(packet_type: int, payload: bytes = b"") -> bytes:
    return HEADER.pack(
        MAGIC,
        VERSION,
        int(packet_type),
        len(payload),
    ) + payload


def full_packet(x, y, width, height, bgra):
    """
    Preserve the existing RSFX renderer API while encoding the image
    using ErsatzTV's Rectangles payload.

    Rectangle payload:
        uint16 rectangle_count
        uint16 x
        uint16 y
        uint16 width
        uint16 height
        BGRA pixel bytes
    """

    x = int(x)
    y = int(y)
    width = int(width)
    height = int(height)

    if not 0 <= x <= 0xFFFF:
        raise ValueError(f"x is outside uint16 range: {x}")

    if not 0 <= y <= 0xFFFF:
        raise ValueError(f"y is outside uint16 range: {y}")

    if not 0 <= width <= 0xFFFF:
        raise ValueError(f"width is outside uint16 range: {width}")

    if not 0 <= height <= 0xFFFF:
        raise ValueError(f"height is outside uint16 range: {height}")

    expected = width * height * 4

    if len(bgra) != expected:
        raise ValueError(
            f"BGRA payload is {len(bgra)} bytes; expected {expected}"
        )

    payload = (
        struct.pack(
            ">HHHHH",
            1,
            x,
            y,
            width,
            height,
        )
        + bgra
    )

    return _packet(RECTANGLES, payload)


def repeat_packet(frames=1):
    """
    Repeat the current ErsatzTV graphics canvas for N additional frames.
    """

    frames = max(1, int(frames))

    if frames > 0xFFFFFFFF:
        raise ValueError(f"repeat count is outside uint32 range: {frames}")

    payload = struct.pack(">I", frames)

    return _packet(REPEAT, payload)


def clear_packet():
    """
    Clear the ErsatzTV graphics canvas.
    """

    return _packet(CLEAR, b"")


def inspect_header(data):
    if len(data) < HEADER.size:
        raise ValueError(
            f"packet is only {len(data)} bytes; header requires {HEADER.size}"
        )

    magic, version, packet_type, payload_length = HEADER.unpack_from(data)

    return {
        "magic": magic,
        "version": version,
        "type": packet_type,
        "payload_length": payload_length,
    }
