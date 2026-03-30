import socket
import struct
import time
from typing import Callable

NTP_TIMESTAMP_DELTA = 2208988800
DEFAULT_NTP_SERVERS = (
    "pool.ntp.org",
    "time.google.com",
    "time.windows.com",
)


class TimeSyncError(RuntimeError):
    pass


def _to_ntp_timestamp(timestamp: float) -> bytes:
    seconds = int(timestamp) + NTP_TIMESTAMP_DELTA
    fraction = int((timestamp - int(timestamp)) * (1 << 32)) & 0xFFFFFFFF
    return struct.pack("!II", seconds, fraction)


def _from_ntp_timestamp(data: bytes) -> float:
    seconds, fraction = struct.unpack("!II", data)
    return (seconds - NTP_TIMESTAMP_DELTA) + float(fraction) / (1 << 32)


def _build_ntp_request(timestamp: float) -> bytes:
    packet = bytearray(48)
    packet[0] = 0x1B  # LI = 0, VN = 3, Mode = 3 (client)
    packet[40:48] = _to_ntp_timestamp(timestamp)
    return bytes(packet)


def _create_udp_socket(server: str, port: int, timeout: float) -> socket.socket:
    last_error = None
    for family, socktype, proto, _, address in socket.getaddrinfo(
        server,
        port,
        type=socket.SOCK_DGRAM,
    ):
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(address)
            return sock
        except OSError as exc:
            last_error = exc
    raise TimeSyncError(f"Unable to create UDP socket for {server}:{port}") from last_error


def get_ntp_time(server: str = "pool.ntp.org", timeout: float = 5.0, port: int = 123) -> float:
    """Return current UTC time from an NTP server as a Unix timestamp."""
    request_timestamp = time.time()
    request = _build_ntp_request(request_timestamp)

    with _create_udp_socket(server, port, timeout) as sock:
        sock.send(request)
        data = sock.recv(512)

    if len(data) < 48:
        raise TimeSyncError("Invalid NTP response received")

    transmit_timestamp = _from_ntp_timestamp(data[40:48])
    return transmit_timestamp


def get_time_offset(server: str = "pool.ntp.org", timeout: float = 5.0, port: int = 123) -> float:
    """Return clock offset between local system time and NTP time."""
    request_timestamp = time.time()
    request = _build_ntp_request(request_timestamp)

    with _create_udp_socket(server, port, timeout) as sock:
        sock.send(request)
        response = sock.recv(512)
        receipt_timestamp = time.time()

    if len(response) < 48:
        raise TimeSyncError("Invalid NTP response received")

    originate = _from_ntp_timestamp(response[24:32])
    receive = _from_ntp_timestamp(response[32:40])
    transmit = _from_ntp_timestamp(response[40:48])

    t1 = request_timestamp + NTP_TIMESTAMP_DELTA
    t4 = receipt_timestamp + NTP_TIMESTAMP_DELTA

    offset = ((receive - t1) + (transmit - t4)) / 2
    return offset


def get_synchronised_time(server: str = "pool.ntp.org", timeout: float = 5.0) -> int:
    """Return the current synchronized Unix time using an NTP server."""
    return int(get_ntp_time(server, timeout))


def get_synchronised_clock(
    server: str = "pool.ntp.org",
    timeout: float = 5.0,
) -> Callable[[], int]:
    """Return a callable clock that uses the local clock adjusted to NTP."""
    offset = get_time_offset(server, timeout)

    def clock() -> int:
        return int(time.time() + offset)

    return clock


def create_synchronised_time(display):
    datetime = [2021, 1, 1, 1, 1, 0]
    selected_idx = 0

    display_width = display.get_width()
    display_height = display.get_height()

    while True:
        if display.is_pressed(display.BUTTON_A):
            selected_idx = (selected_idx + 1) % len(datetime)
        if display.is_pressed(display.BUTTON_X):
            datetime[selected_idx] += 1
        if display.is_pressed(display.BUTTON_Y):
            datetime[selected_idx] = max(datetime[selected_idx] - 1, 1)
        if display.is_pressed(display.BUTTON_B):
            break

        display.set_pen(0, 0, 0)
        display.clear()

        display.set_pen(255, 255, 255)
        display.text("Next", 10, 10, 30, 2)
        display.text("Inc", display_width - 40, 10, 30, 2)
        display.text("Dec", display_width - 40, display_height - 20, 30, 2)
        display.text("Confirm", 10, display_height - 20, 30, 2)

        display.text(
            "YYYY MM DD HH MM SS", 30,
            display_height // 2 - 10, display_width - 30, 2,
        )
        display.text(
            " ".join(
                "%s%02d" % (">" if idx == selected_idx else "", sep)
                for idx, sep in enumerate(datetime)
            ),
            30,
            display_height // 2 + 10,
            display_width - 30,
            2,
        )

        display.update()
        time.sleep(0.3)

    delta = time.mktime(datetime + [0, 0]) - time.time()

    def synchronised_time() -> int:
        return int(time.time() + delta)

    return synchronised_time
