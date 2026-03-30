import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import onetimepass as otp
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install onetimepass` before running this script."
    ) from exc

try:
    import pygame as pygame_module
except ImportError:
    pygame_module = None

pygame: Any = pygame_module

try:
    from synchronized_time import get_ntp_time
except ImportError:
    get_ntp_time = None

SECRETS_FILE = Path("secrets.json")
OUTPUT_FILE = Path("codes.json")
CONFIG_FILE = Path("args.json")
MENU_WIDTH = 360
MENU_MARGIN = 30
MENU_HEIGHT = 214
MENU_ROTATE_TOP = 67
MENU_DISMISS_TOP = 115
MENU_EXIT_TOP = 163

_current_clock = time.time


def current_time() -> float:
    return _current_clock()


def is_time_synced() -> bool:
    return _current_clock is not time.time


def sync_time(server: str = "pool.ntp.org", timeout: float = 5.0) -> bool:
    global _current_clock
    if get_ntp_time is None:
        print("synchronized_time module not available; falling back to local time")
        _current_clock = time.time
        return False

    try:
        ntp_timestamp = get_ntp_time(server, timeout)
        offset = ntp_timestamp - time.time()

        def synced_clock() -> float:
            return time.time() + offset

        _current_clock = synced_clock
        print(f"Time synchronized using NTP server {server}")
        return True
    except Exception as exc:
        print(f"Time sync failed: {exc}")
        _current_clock = time.time
        return False


class PygameDisplay:
    def __init__(self, width: int, height: int, surface: Any, rotation: int = 0):
        self._screen = surface
        self._base_width = width
        self._base_height = height
        self._rotation = 0
        self._width = width
        self._height = height
        self._surface = surface
        self._color = (255, 255, 255)
        self._bg_color = (0, 0, 0)
        self.set_rotation(rotation)

    def get_width(self) -> int:
        return self._width

    def get_height(self) -> int:
        return self._height

    def set_pen(self, r: int, g: int, b: int) -> None:
        self._color = (r, g, b)

    def clear(self) -> None:
        self._surface.fill(self._bg_color)

    def update(self) -> None:
        if self._rotation == 0:
            pygame.display.flip()
            return

        rotated = pygame.transform.rotate(self._surface, self._rotation)
        screen_width, screen_height = self._screen.get_size()
        if rotated.get_size() != (screen_width, screen_height):
            rotated = pygame.transform.scale(rotated, (screen_width, screen_height))
        self._screen.blit(rotated, (0, 0))
        pygame.display.flip()

    def get_surface(self) -> Any:
        return self._surface

    def get_screen_size(self) -> tuple[int, int]:
        return self._screen.get_size()

    def get_rotation(self) -> int:
        return self._rotation

    def set_rotation(self, rotation: int) -> None:
        self._rotation = rotation % 360
        if self._rotation in (90, 270):
            self._width = self._base_height
            self._height = self._base_width
        else:
            self._width = self._base_width
            self._height = self._base_height

        if self._rotation == 0:
            self._surface = self._screen
        else:
            self._surface = pygame.Surface((self._width, self._height)).convert()
        self.clear()


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _parse_hex_color(value: str, fallback: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    if not isinstance(value, str):
        return fallback
    raw = value.strip().lstrip("#")
    if len(raw) != 6:
        return fallback
    try:
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        return fallback


def _fit_font_size(text: str, max_width: int, preferred_size: int, min_size: int = 12) -> int:
    if pygame is None:
        return preferred_size

    text = str(text)
    size = max(min_size, preferred_size)
    while size > min_size:
        font = pygame.font.Font(None, size)
        if font.size(text)[0] <= max_width:
            break
        size -= 1
    return max(min_size, size)


def _draw_single_line_text(
    surface,
    text: str,
    x: int,
    y: int,
    max_width: int,
    preferred_size: int,
    color: tuple[int, int, int],
) -> int:
    if pygame is None:
        return y

    safe_text = str(text)
    font_size = _fit_font_size(safe_text, max_width, preferred_size)
    font = pygame.font.Font(None, font_size)
    rendered = font.render(safe_text, True, color)
    surface.blit(rendered, (x, y))
    return y + rendered.get_height()


def _try_pygame_display(width: int, height: int):
    pygame.quit()
    pygame.init()
    screen = pygame.display.set_mode((width, height))
    pygame.mouse.set_visible(False)
    return screen


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        config = json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: Could not load {CONFIG_FILE}: {exc}")
        return {}
    if not isinstance(config, dict):
        print(f"Warning: Expected {CONFIG_FILE} to contain a JSON object")
        return {}
    return config


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def save_display_rotation(rotation: int) -> None:
    config = load_config()
    config["display_rotation"] = rotation % 360
    save_config(config)
    print(f"Saved display_rotation={rotation % 360} to {CONFIG_FILE.resolve()}")


def init_pygame_display(width: int = 480, height: int = 320, desktop: bool = False, rotation: int = 0):
    if pygame is None:
        raise RuntimeError("pygame is not installed")

    env_driver = os.environ.get("SDL_VIDEODRIVER")
    drivers: list[str] = []
    if env_driver:
        drivers.append(env_driver)

    if not desktop:
        if os.path.exists("/dev/dri/card0"):
            drivers.append("kmsdrm")
        if os.path.exists("/dev/fb0"):
            drivers.append("fbcon")

    if sys.platform.startswith("win"):
        drivers.append("windows")
    if os.environ.get("DISPLAY"):
        drivers.append("x11")
    if os.environ.get("WAYLAND_DISPLAY"):
        drivers.append("wayland")

    drivers.extend(["auto", "dummy"])
    drivers = list(dict.fromkeys(drivers))

    print(f"SDL_VIDEODRIVER={env_driver!r} detected, probing drivers: {drivers}")
    last_exc = None
    for driver in drivers:
        try:
            if driver == "auto":
                os.environ.pop("SDL_VIDEODRIVER", None)
                os.environ.pop("SDL_FBDEV", None)
                os.environ.pop("SDL_KMSDRM_DEVICE", None)
            else:
                os.environ["SDL_VIDEODRIVER"] = driver
                if driver == "fbcon":
                    os.environ["SDL_FBDEV"] = "/dev/fb0"
                    os.environ.pop("SDL_KMSDRM_DEVICE", None)
                elif driver == "kmsdrm":
                    os.environ.pop("SDL_FBDEV", None)
                    if os.path.exists("/dev/dri/card0"):
                        os.environ["SDL_KMSDRM_DEVICE"] = "/dev/dri/card0"
                    else:
                        os.environ.pop("SDL_KMSDRM_DEVICE", None)
                else:
                    os.environ.pop("SDL_FBDEV", None)
                    os.environ.pop("SDL_KMSDRM_DEVICE", None)

            print(f"Attempting pygame display init with SDL_VIDEODRIVER={driver}")
            screen = _try_pygame_display(width, height)
            print(f"Pygame display initialized with driver {driver}")
            return PygameDisplay(width, height, screen, rotation=rotation)
        except Exception as exc:
            last_exc = exc
            print(f"Pygame driver {driver} failed: {exc}")
            continue

    raise RuntimeError(
        f"Unable to initialize pygame display with drivers {drivers}: {last_exc}"
    )

ACCOUNTS_KEY = "accounts"


def load_secrets(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"Missing secrets file: {path.resolve()}\n"
            "Create a secrets.json file based on secrets.json.example."
        )

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Invalid JSON in {path.resolve()}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise SystemExit(
            f"Expected {path.resolve()} to contain a JSON object."
        )

    return data


def get_secret(secrets: dict, secret_name: str) -> str | None:
    value = secrets.get(secret_name)
    if not value or value.startswith("YOUR_"):
        return None
    return value


def build_codes() -> list[dict]:
    secrets = load_secrets(SECRETS_FILE)
    accounts = secrets.get(ACCOUNTS_KEY)
    if not accounts or not isinstance(accounts, list):
        raise SystemExit(
            f"No 'accounts' list found in {SECRETS_FILE.resolve()}.\n"
            "See secrets.json.example for the expected format."
        )
    codes = []
    for account in accounts:
        secret = get_secret(secrets, account["secret_name"])
        if secret is None:
            print(f"SKIP: {account['name']} (no secret configured)")
            continue
        codes.append(
            {
                "name": account["name"],
                "key": secret,
                "digits": account.get("digits", 6),
                "step": account.get("step", 30),
                "colour": account.get("colour", "#FFFFFF"),
            }
        )
    return codes


def write_codes_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {path.resolve()}")


def _get_menu_layout(width: int, height: int) -> tuple[Any, Any, Any, Any]:
    menu_width = min(MENU_WIDTH, width - MENU_MARGIN)
    menu_x = (width - menu_width) // 2
    menu_y = (height - MENU_HEIGHT) // 2
    menu_rect = pygame.Rect(menu_x, menu_y, menu_width, MENU_HEIGHT)
    rotate_rect = pygame.Rect(menu_x + 20, menu_y + MENU_ROTATE_TOP, menu_width - 40, 40)
    dismiss_rect = pygame.Rect(menu_x + 20, menu_y + MENU_DISMISS_TOP, menu_width - 40, 40)
    exit_rect = pygame.Rect(menu_x + 20, menu_y + MENU_EXIT_TOP, menu_width - 40, 34)
    return menu_rect, rotate_rect, dismiss_rect, exit_rect


def _draw_touch_menu_overlay(display) -> None:
    if pygame is None:
        return

    surface = display.get_surface()
    width = display.get_width()
    height = display.get_height()

    # Dim the background and draw a centered menu card.
    dim = pygame.Surface((width, height), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    surface.blit(dim, (0, 0))

    menu_rect, rotate_rect, dismiss_rect, exit_rect = _get_menu_layout(width, height)
    menu_x = menu_rect.x
    menu_y = menu_rect.y

    pygame.draw.rect(surface, (30, 30, 30), menu_rect, border_radius=10)
    pygame.draw.rect(surface, (220, 220, 220), menu_rect, width=2, border_radius=10)

    font_title = pygame.font.Font(None, 34)
    font_button = pygame.font.Font(None, 30)

    title_surface = font_title.render("Menu", True, (255, 255, 255))
    surface.blit(title_surface, (menu_x + 20, menu_y + 15))

    pygame.draw.rect(surface, (60, 90, 180), rotate_rect, border_radius=8)
    pygame.draw.rect(surface, (50, 120, 60), dismiss_rect, border_radius=8)
    pygame.draw.rect(surface, (170, 40, 40), exit_rect, border_radius=8)

    rotate_text = font_button.render("Rotate Screen", True, (255, 255, 255))
    exit_text = font_button.render("Exit Program", True, (255, 255, 255))
    dismiss_text = font_button.render("Dismiss", True, (255, 255, 255))

    surface.blit(
        rotate_text,
        (
            rotate_rect.centerx - rotate_text.get_width() // 2,
            rotate_rect.centery - rotate_text.get_height() // 2,
        ),
    )
    surface.blit(
        dismiss_text,
        (
            dismiss_rect.centerx - dismiss_text.get_width() // 2,
            dismiss_rect.centery - dismiss_text.get_height() // 2,
        ),
    )
    surface.blit(
        exit_text,
        (
            exit_rect.centerx - exit_text.get_width() // 2,
            exit_rect.centery - exit_text.get_height() // 2,
        ),
    )


def _map_physical_to_logical(display, x: int, y: int) -> tuple[int, int]:
    rotation = display.get_rotation()
    logical_width = display.get_width()
    logical_height = display.get_height()
    screen_width, screen_height = display.get_screen_size()

    x = max(0, min(screen_width - 1, x))
    y = max(0, min(screen_height - 1, y))

    if rotation == 90:
        return logical_width - 1 - y, x
    if rotation == 180:
        return logical_width - 1 - x, logical_height - 1 - y
    if rotation == 270:
        return y, logical_height - 1 - x
    return x, y


def _event_to_pixel_pos(display, event) -> tuple[int, int] | None:
    if pygame is None:
        return None

    if event.type == pygame.MOUSEBUTTONDOWN:
        return _map_physical_to_logical(display, int(event.pos[0]), int(event.pos[1]))

    if hasattr(pygame, "FINGERDOWN") and event.type == pygame.FINGERDOWN:
        screen_width, screen_height = display.get_screen_size()
        x = int(max(0.0, min(1.0, float(event.x))) * screen_width)
        y = int(max(0.0, min(1.0, float(event.y))) * screen_height)
        return _map_physical_to_logical(display, x, y)

    return None


def _handle_touch_menu_events(display, menu_visible: bool):
    if pygame is None or display is None:
        return menu_visible, False, None

    width = display.get_width()
    height = display.get_height()
    menu_rect, rotate_rect, dismiss_rect, exit_rect = _get_menu_layout(width, height)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            raise SystemExit("Pygame quit event received")

        if event.type == pygame.MOUSEBUTTONDOWN or (
            hasattr(pygame, "FINGERDOWN") and event.type == pygame.FINGERDOWN
        ):
            point = _event_to_pixel_pos(display, event)
            if point is None:
                continue

            if not menu_visible:
                # First touch opens the menu.
                return True, True, None

            # Touch while menu is open: button actions or tap-away dismissal.
            if rotate_rect.collidepoint(point):
                return False, True, "rotate"
            if exit_rect.collidepoint(point):
                raise SystemExit("Exit requested from touch menu")
            if dismiss_rect.collidepoint(point):
                return False, True, None
            if not menu_rect.collidepoint(point):
                return False, True, None

    return menu_visible, False, None


def render_codes(
    display,
    codes,
    menu_visible: bool = False,
    seconds_to_refresh: int | None = None,
    refresh_interval: int | None = None,
    synced: bool = False,
):
    """Render the codes and labels onto the integrated display."""
    if display is None:
        return

    surface = display.get_surface()
    width = display.get_width()
    height = display.get_height()

    status_bar_height = _clamp(int(height * 0.12), 24, 56)
    content_bottom = height - status_bar_height
    padding_x = _clamp(int(width * 0.03), 6, 20)
    padding_top = _clamp(int(height * 0.03), 6, 16)

    display.set_pen(0, 0, 0)
    display.clear()

    visible_count = max(1, len(codes))
    item_height = max(48, (content_bottom - padding_top - 6) // visible_count)

    y = padding_top
    for item in codes:
        if y + item_height > content_bottom:
            break

        label = item["name"]
        code = str(item.get("code", "------"))
        code_color = _parse_hex_color(item.get("colour", "#FFFFFF"), fallback=(255, 255, 255))

        label_size = _clamp(int(item_height * 0.36), 28, 72)
        code_size = _clamp(int(item_height * 0.62), 48, 132)

        label_y = y
        code_y = y + _clamp(int(item_height * 0.46), 28, 56)

        _draw_single_line_text(
            surface,
            label,
            padding_x,
            label_y,
            width - (padding_x * 2),
            label_size,
            (220, 220, 220),
        )
        _draw_single_line_text(
            surface,
            code,
            padding_x,
            code_y,
            width - (padding_x * 2),
            code_size,
            code_color,
        )

        y += item_height

    # Bottom status bar with countdown to next OTP refresh.
    pygame.draw.rect(surface, (25, 25, 25), pygame.Rect(0, content_bottom, width, status_bar_height))
    pygame.draw.line(surface, (70, 70, 70), (0, content_bottom), (width, content_bottom), 1)

    if seconds_to_refresh is None:
        status_text = "Status: waiting for next update"
    else:
        status_text = f"Next update in {int(seconds_to_refresh)}s"
    status_size = _clamp(int(status_bar_height * 0.72), 14, 30)
    status_y = content_bottom + max(2, (status_bar_height - status_size) // 2)
    _draw_single_line_text(
        surface,
        status_text,
        padding_x,
        status_y,
        width - (padding_x * 2),
        status_size,
        (210, 210, 210),
    )

    if synced:
        tag_text = "(time synced)"
        tag_size = _clamp(int(status_size * 0.65), 12, 22)
        tag_font = pygame.font.Font(None, tag_size)
        tag_surface = tag_font.render(tag_text, True, (140, 220, 160))
        tag_x = width - padding_x - tag_surface.get_width()
        tag_y = status_y
        surface.blit(tag_surface, (tag_x, tag_y))

    # Thin progress bar that fills as countdown approaches zero.
    if seconds_to_refresh is not None and refresh_interval and refresh_interval > 0:
        progress = (refresh_interval - int(seconds_to_refresh)) / float(refresh_interval)
        progress = max(0.0, min(1.0, progress))

        bar_margin = padding_x
        bar_height = max(3, status_bar_height // 8)
        bar_width = max(40, width - (bar_margin * 2))
        bar_x = bar_margin
        bar_y = height - bar_height - 2
        fill_width = int(bar_width * progress)

        pygame.draw.rect(
            surface,
            (60, 60, 60),
            pygame.Rect(bar_x, bar_y, bar_width, bar_height),
            border_radius=2,
        )
        if fill_width > 0:
            pygame.draw.rect(
                surface,
                (80, 190, 110),
                pygame.Rect(bar_x, bar_y, fill_width, bar_height),
                border_radius=2,
            )

    if menu_visible:
        _draw_touch_menu_overlay(display)

    display.update()


def pad_base32_secret(secret: str) -> str:
    """Normalize and pad base32 secret to proper length for decoding."""
    secret = secret.strip().replace(" ", "").upper()
    padding_needed = (8 - len(secret) % 8) % 8
    return secret + ("=" * padding_needed)


def seconds_until_next_step(interval: int, now: float | None = None) -> int:
    if now is None:
        now = current_time()
    remainder = int(now) % interval
    return interval - remainder if remainder else interval


def generate_totps(data, now: float | None = None):
    if now is None:
        now = current_time()

    return [
        {
            **item,
            "code": str(
                otp.get_totp(
                    pad_base32_secret(item["key"]),
                    token_length=item["digits"],
                    interval_length=item["step"],
                    clock=int(now),
                )
            ).zfill(int(item["digits"])),
        }
        for item in data
    ]


def _rotate_display(display) -> None:
    next_rotation = (display.get_rotation() + 90) % 360
    display.set_rotation(next_rotation)
    save_display_rotation(next_rotation)


def watch_codes(poll_interval: float = 1.0, display=None) -> None:
    codes = build_codes()
    if not codes:
        raise SystemExit("No configured OTP accounts found in secrets.json.")

    last_codes = None
    current_codes = None
    synced_time = False
    menu_visible = False
    last_next_refresh = None
    refresh_interval = min(item["step"] for item in codes)
    print("Watching TOTP codes. Press Ctrl+C to stop.")
    while True:
        menu_visible, menu_changed, menu_action = _handle_touch_menu_events(display, menu_visible)

        if menu_action == "rotate" and display is not None:
            _rotate_display(display)
            menu_changed = True

        now = current_time()
        next_refresh = min(seconds_until_next_step(item["step"], now) for item in codes)

        should_render = menu_changed
        if next_refresh != last_next_refresh:
            should_render = True
            last_next_refresh = next_refresh

        if last_codes is None or next_refresh <= 10 or next_refresh >= 28:
            if not synced_time:
                sync_time()
                synced_time = True
                now = current_time()
            current_codes = generate_totps(codes, now=now)
            if current_codes != last_codes:
                write_codes_json(OUTPUT_FILE, current_codes)
                last_codes = current_codes
                should_render = True
        else:
            synced_time = False  # Mark time as unsynced if we're not close to a refresh

        if should_render and current_codes is not None:
            render_codes(
                display,
                current_codes,
                menu_visible=menu_visible,
                seconds_to_refresh=next_refresh,
                refresh_interval=refresh_interval,
                synced=is_time_synced(),
            )
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"{len(codes)} accounts active, next refresh in {next_refresh}s"
        )

        try:
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("Stopped watching OTP codes.")
            break


def main(display=None) -> None:
    codes = build_codes()
    if not codes:
        raise SystemExit("No configured OTP accounts found in secrets.json.")

    current_codes = generate_totps(codes)
    next_refresh = min(seconds_until_next_step(item["step"]) for item in codes)
    refresh_interval = min(item["step"] for item in codes)
    write_codes_json(OUTPUT_FILE, current_codes)
    render_codes(
        display,
        current_codes,
        seconds_to_refresh=next_refresh,
        refresh_interval=refresh_interval,
        synced=is_time_synced(),
    )
    print("Current TOTP codes:")
    for item in current_codes:
        print(f"{item['name']}: {item['code']}")


if __name__ == "__main__":
    config = load_config()
    print(f"Loaded config from {CONFIG_FILE}")

    parser = argparse.ArgumentParser(description="Generate and optionally watch TOTP codes for configured accounts.")
    parser.add_argument(
        "--watch",
        action="store_true",
        default=config.get("watch", False),
        help="Run continuously and refresh codes every second.",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=config.get("poll_interval", 1.0),
        help="Polling interval in seconds when watching (default: 1.0).",
    )
    parser.add_argument(
        "--pygame",
        action="store_true",
        default=config.get("pygame_enabled", False),
        help="Render codes to the Pygame display instead of console only.",
    )
    parser.add_argument(
        "--desktop",
        action="store_true",
        default=config.get("desktop_mode", False),
        help="Prefer a desktop window fallback when running outside the Pi framebuffer.",
    )
    parser.add_argument(
        "--rotation",
        type=int,
        default=config.get("display_rotation", 0),
        choices=[0, 90, 180, 270],
        help="Display rotation in degrees (0, 90, 180, 270). Default: 0.",
    )
    args = parser.parse_args()

    display = None
    if args.pygame:
        if pygame is None:
            raise SystemExit("pygame is not installed. Install pygame to use display rendering.")
        display = init_pygame_display(desktop=args.desktop, rotation=args.rotation)

    if args.watch:
        watch_codes(args.poll, display=display)
    else:
        main(display=display)
