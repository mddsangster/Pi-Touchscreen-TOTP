import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
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
ACCOUNTS_KEY = "accounts"
MAX_CODES = 4
DEFAULT_DIGITS = 6
DEFAULT_STEP = 30
DEFAULT_COLOURS = ["#E74C3C", "#3498DB", "#2ECC71", "#F1C40F"]

MAIN_MENU_WIDTH = 360
MAIN_MENU_MARGIN = 30
MAIN_MENU_HEIGHT = 258
MAIN_MENU_ADD_TOP = 67
MAIN_MENU_ROTATE_TOP = 115
MAIN_MENU_DISMISS_TOP = 163
MAIN_MENU_EXIT_TOP = 211

SECONDARY_MENU_WIDTH = 390
SECONDARY_MENU_MARGIN = 30
SECRET_MENU_HEIGHT = 238
CONFIRM_MENU_HEIGHT = 232
KEYPAD_ROWS: list[list[str]] = [
    ["A", "B", "C", "D", "E", "F", "G", "H"],
    ["I", "J", "K", "L", "M", "N", "O", "P"],
    ["Q", "R", "S", "T", "U", "V", "W", "X"],
    ["Y", "Z", "2", "3", "4", "5", "6", "7"],
    ["=", "SPACE", "BKSP", "CLEAR"],
]
SYSTEM_KEYBOARD_COMMANDS: list[list[str]] = [
    ["matchbox-keyboard"],
    ["wvkbd-mobintl"],
    ["wvkbd"],
    ["onboard"],
]

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

    safe_text = str(text)
    size = max(min_size, preferred_size)
    while size > min_size:
        font = pygame.font.Font(None, size)
        if font.size(safe_text)[0] <= max_width:
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


def _draw_wrapped_text(
    surface,
    text: str,
    x: int,
    y: int,
    max_width: int,
    preferred_size: int,
    color: tuple[int, int, int],
    line_spacing: int = 4,
) -> int:
    if pygame is None:
        return y

    if not text:
        return y

    font_size = max(12, preferred_size)
    font = pygame.font.Font(None, font_size)
    words = str(text).split()
    if not words:
        return y

    wrapped_lines: list[str] = []
    current_line = words[0]
    for word in words[1:]:
        candidate = f"{current_line} {word}"
        if font.size(candidate)[0] <= max_width:
            current_line = candidate
        else:
            wrapped_lines.append(current_line)
            current_line = word
    wrapped_lines.append(current_line)

    for line in wrapped_lines:
        rendered = font.render(line, True, color)
        surface.blit(rendered, (x, y))
        y += rendered.get_height() + line_spacing
    return y


def _draw_button(surface, rect, label: str, fill: tuple[int, int, int], enabled: bool = True) -> None:
    if pygame is None:
        return

    actual_fill = fill if enabled else (80, 80, 80)
    pygame.draw.rect(surface, actual_fill, rect, border_radius=8)
    font = pygame.font.Font(None, 30)
    text_surface = font.render(label, True, (255, 255, 255) if enabled else (180, 180, 180))
    surface.blit(
        text_surface,
        (
            rect.centerx - text_surface.get_width() // 2,
            rect.centery - text_surface.get_height() // 2,
        ),
    )


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


def save_secrets(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def get_secret(secrets: dict, secret_name: str) -> str | None:
    value = secrets.get(secret_name)
    if not value or value.startswith("YOUR_"):
        return None
    return value


def _build_code_entry(account: dict, secrets: dict) -> dict | None:
    secret = get_secret(secrets, account["secret_name"])
    if secret is None:
        print(f"SKIP: {account['name']} (no secret configured)")
        return None
    return {
        "name": account["name"],
        "key": secret,
        "digits": account.get("digits", DEFAULT_DIGITS),
        "step": account.get("step", DEFAULT_STEP),
        "colour": account.get("colour", "#FFFFFF"),
    }


def build_codes() -> list[dict]:
    secrets = load_secrets(SECRETS_FILE)
    accounts = secrets.get(ACCOUNTS_KEY)
    if not accounts or not isinstance(accounts, list):
        raise SystemExit(
            f"No 'accounts' list found in {SECRETS_FILE.resolve()}.\n"
            "See secrets.json.example for the expected format."
        )

    codes: list[dict] = []
    for account in accounts:
        code_entry = _build_code_entry(account, secrets)
        if code_entry is None:
            continue
        codes.append(code_entry)
        if len(codes) >= MAX_CODES:
            break
    return codes


def write_codes_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {path.resolve()}")


def _create_ui_state() -> dict[str, Any]:
    return {
        "mode": "codes",
        "draft_secret": "",
        "preview_code": None,
        "preview_error": None,
        "preview_name": None,
        "system_keyboard_process": None,
        "system_keyboard_status": "",
        "system_keyboard_attempted": False,
        "toast_message": "",
        "toast_level": "info",
        "toast_expires_at": 0.0,
    }


def _set_toast(ui_state: dict[str, Any], message: str, level: str = "info", seconds: float = 2.0) -> None:
    ui_state["toast_message"] = message
    ui_state["toast_level"] = level
    ui_state["toast_expires_at"] = current_time() + max(0.3, seconds)


def _clear_expired_toast(ui_state: dict[str, Any], now: float) -> None:
    if ui_state.get("toast_message") and now >= float(ui_state.get("toast_expires_at", 0.0)):
        ui_state["toast_message"] = ""
        ui_state["toast_level"] = "info"
        ui_state["toast_expires_at"] = 0.0


def _set_text_input_enabled(enabled: bool) -> None:
    if pygame is None or not hasattr(pygame, "key"):
        return
    if enabled:
        pygame.key.start_text_input()
    else:
        pygame.key.stop_text_input()


def _stop_system_keyboard(ui_state: dict[str, Any]) -> None:
    process = ui_state.get("system_keyboard_process")
    if process is None:
        return

    try:
        if process.poll() is None:
            process.terminate()
    except Exception:
        pass
    finally:
        ui_state["system_keyboard_process"] = None


def _start_system_keyboard_fallback(ui_state: dict[str, Any]) -> None:
    if ui_state.get("system_keyboard_attempted"):
        return

    ui_state["system_keyboard_attempted"] = True
    for command in SYSTEM_KEYBOARD_COMMANDS:
        if shutil.which(command[0]) is None:
            continue
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ui_state["system_keyboard_process"] = process
            ui_state["system_keyboard_status"] = f"System keyboard launched: {command[0]}"
            return
        except Exception as exc:
            ui_state["system_keyboard_status"] = f"System keyboard launch failed: {exc}"

    if not ui_state.get("system_keyboard_status"):
        ui_state["system_keyboard_status"] = "No system keyboard available. Using built-in keypad."


def _set_ui_mode(ui_state: dict[str, Any], mode: str) -> dict[str, Any]:
    ui_state["mode"] = mode
    _set_text_input_enabled(mode == "add_secret")
    if mode == "add_secret":
        _start_system_keyboard_fallback(ui_state)
    else:
        _stop_system_keyboard(ui_state)
        ui_state["system_keyboard_attempted"] = False
        ui_state["system_keyboard_status"] = ""
    return ui_state


def _clear_preview_state(ui_state: dict[str, Any]) -> None:
    ui_state["draft_secret"] = ""
    ui_state["preview_code"] = None
    ui_state["preview_error"] = None
    ui_state["preview_name"] = None


def _reset_to_main_menu(ui_state: dict[str, Any]) -> dict[str, Any]:
    ui_state["preview_code"] = None
    ui_state["preview_error"] = None
    ui_state["preview_name"] = None
    _set_ui_mode(ui_state, "menu")
    return ui_state


def _next_account_details(secrets: dict) -> tuple[str, str, str]:
    accounts = secrets.get(ACCOUNTS_KEY, [])
    index = 1
    while True:
        display_name = f"Code {index}"
        secret_name = f"code_{index}"
        if secret_name not in secrets and not any(item.get("secret_name") == secret_name for item in accounts):
            colour = DEFAULT_COLOURS[(index - 1) % len(DEFAULT_COLOURS)]
            return display_name, secret_name, colour
        index += 1


def _save_new_secret(secret_value: str) -> dict:
    secrets = load_secrets(SECRETS_FILE)
    accounts = secrets.get(ACCOUNTS_KEY)
    if not isinstance(accounts, list):
        raise ValueError("Missing accounts list in secrets.json")
    if len(accounts) >= MAX_CODES:
        raise ValueError(f"Maximum of {MAX_CODES} codes supported")

    display_name, secret_name, colour = _next_account_details(secrets)
    normalized_secret = pad_base32_secret(secret_value)
    secrets[secret_name] = normalized_secret
    accounts.append(
        {
            "name": display_name,
            "secret_name": secret_name,
            "digits": DEFAULT_DIGITS,
            "step": DEFAULT_STEP,
            "colour": colour,
        }
    )
    save_secrets(SECRETS_FILE, secrets)
    return {
        "name": display_name,
        "key": normalized_secret,
        "digits": DEFAULT_DIGITS,
        "step": DEFAULT_STEP,
        "colour": colour,
    }


def _normalize_secret_input(value: str) -> str:
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567= ")
    return "".join(char for char in value.upper() if char in allowed)[:96]


def _apply_keypad_key(ui_state: dict[str, Any], key_label: str) -> bool:
    if key_label == "BKSP":
        ui_state["draft_secret"] = ui_state["draft_secret"][:-1]
        return True
    if key_label == "CLEAR":
        ui_state["draft_secret"] = ""
        return True
    if key_label == "SPACE":
        ui_state["draft_secret"] = _normalize_secret_input(ui_state["draft_secret"] + " ")
        return True

    ui_state["draft_secret"] = _normalize_secret_input(ui_state["draft_secret"] + key_label)
    return True


def _preview_secret(ui_state: dict[str, Any], code_count: int, now: float) -> dict[str, Any]:
    ui_state["preview_code"] = None
    ui_state["preview_error"] = None
    ui_state["preview_name"] = None

    if code_count >= MAX_CODES:
        ui_state["preview_error"] = f"Maximum of {MAX_CODES} codes already configured."
        _set_toast(ui_state, ui_state["preview_error"], "error", seconds=2.8)
        return _set_ui_mode(ui_state, "confirm_secret")

    draft_secret = ui_state["draft_secret"].strip()
    if not draft_secret:
        ui_state["preview_error"] = "Enter a base32 secret before submitting."
        _set_toast(ui_state, ui_state["preview_error"], "error", seconds=2.5)
        return _set_ui_mode(ui_state, "confirm_secret")

    try:
        preview_account = {
            "name": f"Code {code_count + 1}",
            "key": draft_secret,
            "digits": DEFAULT_DIGITS,
            "step": DEFAULT_STEP,
            "colour": DEFAULT_COLOURS[code_count % len(DEFAULT_COLOURS)],
        }
        preview_code = generate_totps([preview_account], now=now)[0]["code"]
        ui_state["preview_name"] = preview_account["name"]
        ui_state["preview_code"] = preview_code
    except Exception as exc:
        ui_state["preview_error"] = f"Could not generate a code: {exc}"
        _set_toast(ui_state, ui_state["preview_error"], "error", seconds=3.0)

    return _set_ui_mode(ui_state, "confirm_secret")


def _get_main_menu_layout(width: int, height: int) -> dict[str, Any]:
    menu_width = min(MAIN_MENU_WIDTH, width - MAIN_MENU_MARGIN)
    menu_x = (width - menu_width) // 2
    menu_y = (height - MAIN_MENU_HEIGHT) // 2
    return {
        "menu": pygame.Rect(menu_x, menu_y, menu_width, MAIN_MENU_HEIGHT),
        "add": pygame.Rect(menu_x + 20, menu_y + MAIN_MENU_ADD_TOP, menu_width - 40, 40),
        "rotate": pygame.Rect(menu_x + 20, menu_y + MAIN_MENU_ROTATE_TOP, menu_width - 40, 40),
        "dismiss": pygame.Rect(menu_x + 20, menu_y + MAIN_MENU_DISMISS_TOP, menu_width - 40, 40),
        "exit": pygame.Rect(menu_x + 20, menu_y + MAIN_MENU_EXIT_TOP, menu_width - 40, 34),
    }


def _get_secret_menu_layout(width: int, height: int) -> dict[str, Any]:
    menu_width = min(SECONDARY_MENU_WIDTH, width - SECONDARY_MENU_MARGIN)
    menu_height = min(height - 8, 304)
    menu_x = (width - menu_width) // 2
    menu_y = (height - menu_height) // 2
    button_width = (menu_width - 48) // 2

    menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
    input_rect = pygame.Rect(menu_x + 20, menu_y + 88, menu_width - 40, 40)
    submit_rect = pygame.Rect(menu_x + 20, menu_y + 136, button_width, 34)
    cancel_rect = pygame.Rect(menu_x + 28 + button_width, menu_y + 136, button_width, 34)

    keypad_left = menu_x + 20
    keypad_top = cancel_rect.bottom + 8
    keypad_width = menu_width - 40
    keypad_bottom = menu_rect.bottom - 12
    vertical_gap = 4
    keypad_height = max(80, keypad_bottom - keypad_top)
    row_count = len(KEYPAD_ROWS)
    row_height = max(14, (keypad_height - vertical_gap * (row_count - 1)) // row_count)

    keys: list[tuple[str, Any]] = []
    for row_index, row in enumerate(KEYPAD_ROWS):
        row_top = keypad_top + row_index * (row_height + vertical_gap)
        col_gap = 4
        col_width = max(20, (keypad_width - col_gap * (len(row) - 1)) // len(row))
        for col_index, key in enumerate(row):
            left = keypad_left + col_index * (col_width + col_gap)
            key_rect = pygame.Rect(left, row_top, col_width, row_height)
            keys.append((key, key_rect))

    return {
        "menu": menu_rect,
        "input": input_rect,
        "submit": submit_rect,
        "cancel": cancel_rect,
        "keys": keys,
    }


def _get_confirm_menu_layout(width: int, height: int) -> dict[str, Any]:
    menu_width = min(SECONDARY_MENU_WIDTH, width - SECONDARY_MENU_MARGIN)
    menu_x = (width - menu_width) // 2
    menu_y = (height - CONFIRM_MENU_HEIGHT) // 2
    return {
        "menu": pygame.Rect(menu_x, menu_y, menu_width, CONFIRM_MENU_HEIGHT),
        "confirm": pygame.Rect(menu_x + 20, menu_y + 160, menu_width - 40, 40),
        "cancel": pygame.Rect(menu_x + 20, menu_y + 208, menu_width - 40, 24),
    }


def _draw_modal_background(surface, width: int, height: int) -> None:
    dim = pygame.Surface((width, height), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    surface.blit(dim, (0, 0))


def _draw_modal_card(surface, rect, title: str) -> None:
    pygame.draw.rect(surface, (30, 30, 30), rect, border_radius=10)
    pygame.draw.rect(surface, (220, 220, 220), rect, width=2, border_radius=10)
    font_title = pygame.font.Font(None, 34)
    title_surface = font_title.render(title, True, (255, 255, 255))
    surface.blit(title_surface, (rect.x + 20, rect.y + 15))


def _draw_main_menu_overlay(display) -> None:
    if pygame is None:
        return

    surface = display.get_surface()
    width = display.get_width()
    height = display.get_height()
    layout = _get_main_menu_layout(width, height)

    _draw_modal_background(surface, width, height)
    _draw_modal_card(surface, layout["menu"], "Menu")
    _draw_button(surface, layout["add"], "Add Secret", (90, 110, 220))
    _draw_button(surface, layout["rotate"], "Rotate Screen", (60, 90, 180))
    _draw_button(surface, layout["dismiss"], "Dismiss", (50, 120, 60))
    _draw_button(surface, layout["exit"], "Exit Program", (170, 40, 40))


def _draw_secret_entry_overlay(display, ui_state: dict[str, Any]) -> None:
    if pygame is None:
        return

    surface = display.get_surface()
    width = display.get_width()
    height = display.get_height()
    layout = _get_secret_menu_layout(width, height)
    input_rect = layout["input"]

    _draw_modal_background(surface, width, height)
    _draw_modal_card(surface, layout["menu"], "Add Secret")

    instruction_y = layout["menu"].y + 52
    _draw_single_line_text(
        surface,
        "Enter a base32 secret or use keypad below",
        layout["menu"].x + 20,
        instruction_y,
        layout["menu"].width - 40,
        20,
        (215, 215, 215),
    )

    pygame.draw.rect(surface, (18, 18, 18), input_rect, border_radius=8)
    pygame.draw.rect(surface, (120, 120, 120), input_rect, width=2, border_radius=8)
    field_value = ui_state["draft_secret"] or "Tap and type secret"
    field_color = (240, 240, 240) if ui_state["draft_secret"] else (130, 130, 130)
    _draw_single_line_text(surface, field_value, input_rect.x + 12, input_rect.y + 10, input_rect.width - 24, 28, field_color)

    _draw_button(surface, layout["submit"], "Submit", (60, 120, 180))
    _draw_button(surface, layout["cancel"], "Back", (90, 90, 90))

    keyboard_status = ui_state.get("system_keyboard_status")
    if keyboard_status:
        _draw_single_line_text(
            surface,
            keyboard_status,
            layout["menu"].x + 20,
            layout["menu"].y + 172,
            layout["menu"].width - 40,
            18,
            (170, 170, 170),
        )

    for key_label, key_rect in layout["keys"]:
        if key_label in {"BKSP", "CLEAR"}:
            fill = (120, 80, 80)
        elif key_label == "SPACE":
            fill = (80, 80, 130)
        else:
            fill = (65, 65, 65)
        _draw_button(surface, key_rect, key_label, fill)


def _draw_confirm_secret_overlay(display, ui_state: dict[str, Any]) -> None:
    if pygame is None:
        return

    surface = display.get_surface()
    width = display.get_width()
    height = display.get_height()
    layout = _get_confirm_menu_layout(width, height)
    confirm_enabled = ui_state["preview_error"] is None and ui_state["preview_code"] is not None

    _draw_modal_background(surface, width, height)
    _draw_modal_card(surface, layout["menu"], "Confirm Secret")

    body_x = layout["menu"].x + 20
    body_y = layout["menu"].y + 52
    body_width = layout["menu"].width - 40
    if confirm_enabled:
        body_y = _draw_wrapped_text(
            surface,
            f"Preview for {ui_state['preview_name']}",
            body_x,
            body_y,
            body_width,
            24,
            (210, 210, 210),
        )
        _draw_single_line_text(surface, ui_state["preview_code"], body_x, body_y + 6, body_width, 72, (255, 255, 255))
    else:
        _draw_wrapped_text(
            surface,
            ui_state["preview_error"] or "Could not generate a preview code.",
            body_x,
            body_y,
            body_width,
            22,
            (235, 120, 120),
        )

    _draw_button(surface, layout["confirm"], "Confirm", (50, 120, 60), enabled=confirm_enabled)
    _draw_button(surface, layout["cancel"], "Cancel", (90, 90, 90))


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


def _handle_ui_events(display, ui_state: dict[str, Any], code_count: int, now: float):
    if pygame is None or display is None:
        return ui_state, False, None

    width = display.get_width()
    height = display.get_height()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            raise SystemExit("Pygame quit event received")

        mode = ui_state["mode"]
        if mode == "add_secret":
            if event.type == pygame.TEXTINPUT:
                ui_state["draft_secret"] = _normalize_secret_input(ui_state["draft_secret"] + event.text)
                return ui_state, True, None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    ui_state["draft_secret"] = ui_state["draft_secret"][:-1]
                    return ui_state, True, None
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return _preview_secret(ui_state, code_count, now), True, None
                if event.key == pygame.K_ESCAPE:
                    return _reset_to_main_menu(ui_state), True, None

        if mode == "confirm_secret" and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return _reset_to_main_menu(ui_state), True, None

        if event.type != pygame.MOUSEBUTTONDOWN and not (
            hasattr(pygame, "FINGERDOWN") and event.type == pygame.FINGERDOWN
        ):
            continue

        point = _event_to_pixel_pos(display, event)
        if point is None:
            continue

        if mode == "codes":
            return _set_ui_mode(ui_state, "menu"), True, None

        if mode == "menu":
            layout = _get_main_menu_layout(width, height)
            if layout["add"].collidepoint(point):
                _clear_preview_state(ui_state)
                return _set_ui_mode(ui_state, "add_secret"), True, None
            if layout["rotate"].collidepoint(point):
                return _set_ui_mode(ui_state, "codes"), True, "rotate"
            if layout["exit"].collidepoint(point):
                raise SystemExit("Exit requested from touch menu")
            if layout["dismiss"].collidepoint(point) or not layout["menu"].collidepoint(point):
                return _set_ui_mode(ui_state, "codes"), True, None
            continue

        if mode == "add_secret":
            layout = _get_secret_menu_layout(width, height)
            if layout["submit"].collidepoint(point):
                return _preview_secret(ui_state, code_count, now), True, None
            if layout["cancel"].collidepoint(point):
                return _reset_to_main_menu(ui_state), True, None
            if layout["input"].collidepoint(point):
                _set_text_input_enabled(True)
                return ui_state, True, None
            for key_label, key_rect in layout["keys"]:
                if key_rect.collidepoint(point):
                    _apply_keypad_key(ui_state, key_label)
                    return ui_state, True, None
            continue

        if mode == "confirm_secret":
            layout = _get_confirm_menu_layout(width, height)
            if layout["cancel"].collidepoint(point):
                _set_toast(ui_state, "Secret add cancelled", "info", seconds=1.8)
                return _reset_to_main_menu(ui_state), True, None
            if layout["confirm"].collidepoint(point) and ui_state["preview_error"] is None:
                _save_new_secret(ui_state["draft_secret"])
                _clear_preview_state(ui_state)
                _set_toast(ui_state, "Secret saved", "success", seconds=2.2)
                return _set_ui_mode(ui_state, "codes"), True, "secret_saved"
            continue

    return ui_state, False, None


def _draw_code_item(surface, item: dict, x: int, y: int, width: int, height: int) -> None:
    label = item["name"]
    code = str(item.get("code", "------"))
    code_color = _parse_hex_color(item.get("colour", "#FFFFFF"), fallback=(255, 255, 255))
    label_size = _clamp(int(min(height * 0.26, width * 0.16)), 22, 54)
    code_size = _clamp(int(min(height * 0.40, width * 0.28)), 34, 116)
    label_y = y
    code_y = y + _clamp(int(height * 0.34), 24, 52)

    _draw_single_line_text(surface, label, x, label_y, width, label_size, (220, 220, 220))
    _draw_single_line_text(surface, code, x, code_y, width, code_size, code_color)


def _draw_toast_overlay(surface, width: int, content_bottom: int, ui_state: dict[str, Any]) -> None:
    message = str(ui_state.get("toast_message") or "").strip()
    if not message:
        return

    level = ui_state.get("toast_level", "info")
    if level == "success":
        fill_color = (36, 96, 54)
        border_color = (80, 180, 110)
    elif level == "error":
        fill_color = (110, 35, 35)
        border_color = (220, 110, 110)
    else:
        fill_color = (45, 55, 90)
        border_color = (100, 135, 220)

    toast_width = min(width - 12, 360)
    toast_height = 36
    toast_x = (width - toast_width) // 2
    toast_y = max(6, content_bottom - toast_height - 6)
    toast_rect = pygame.Rect(toast_x, toast_y, toast_width, toast_height)

    pygame.draw.rect(surface, fill_color, toast_rect, border_radius=9)
    pygame.draw.rect(surface, border_color, toast_rect, width=2, border_radius=9)
    _draw_single_line_text(
        surface,
        message,
        toast_rect.x + 10,
        toast_rect.y + 9,
        toast_rect.width - 20,
        24,
        (245, 245, 245),
    )


def render_codes(
    display,
    codes,
    ui_state: dict[str, Any] | None = None,
    seconds_to_refresh: int | None = None,
    refresh_interval: int | None = None,
    synced: bool = False,
):
    """Render the codes and labels onto the integrated display."""
    if display is None:
        return

    ui_state = ui_state or _create_ui_state()
    surface = display.get_surface()
    width = display.get_width()
    height = display.get_height()

    status_bar_height = _clamp(int(height * 0.12), 24, 56)
    content_bottom = height - status_bar_height
    padding_x = _clamp(int(width * 0.03), 6, 20)
    padding_top = _clamp(int(height * 0.03), 6, 16)

    display.set_pen(0, 0, 0)
    display.clear()

    visible_codes = list(codes[:MAX_CODES])
    landscape_two_column = display.get_rotation() in (0, 180) and len(visible_codes) > 2

    if landscape_two_column:
        column_gap = _clamp(int(width * 0.04), 8, 22)
        row_gap = _clamp(int(height * 0.02), 8, 18)
        column_width = max(80, (width - (padding_x * 2) - column_gap) // 2)
        rows = (len(visible_codes) + 1) // 2
        item_height = max(72, (content_bottom - padding_top - (row_gap * max(0, rows - 1))) // max(1, rows))
        for index, item in enumerate(visible_codes):
            row = index // 2
            column = index % 2
            item_x = padding_x + column * (column_width + column_gap)
            item_y = padding_top + row * (item_height + row_gap)
            _draw_code_item(surface, item, item_x, item_y, column_width, item_height)
    else:
        visible_count = max(1, len(visible_codes))
        item_height = max(48, (content_bottom - padding_top - 6) // visible_count)
        y = padding_top
        for item in visible_codes:
            if y + item_height > content_bottom:
                break
            _draw_code_item(surface, item, padding_x, y, width - (padding_x * 2), item_height)
            y += item_height

    pygame.draw.rect(surface, (25, 25, 25), pygame.Rect(0, content_bottom, width, status_bar_height))
    pygame.draw.line(surface, (70, 70, 70), (0, content_bottom), (width, content_bottom), 1)

    status_text = "Status: waiting for next update" if seconds_to_refresh is None else f"Next update in {int(seconds_to_refresh)}s"
    status_size = _clamp(int(status_bar_height * 0.72), 14, 30)
    status_y = content_bottom + max(2, (status_bar_height - status_size) // 2)
    _draw_single_line_text(surface, status_text, padding_x, status_y, width - (padding_x * 2), status_size, (210, 210, 210))

    if synced:
        tag_text = "(time synced)"
        tag_size = _clamp(int(status_size * 0.65), 12, 22)
        tag_font = pygame.font.Font(None, tag_size)
        tag_surface = tag_font.render(tag_text, True, (140, 220, 160))
        tag_x = width - padding_x - tag_surface.get_width()
        surface.blit(tag_surface, (tag_x, status_y))

    if seconds_to_refresh is not None and refresh_interval and refresh_interval > 0:
        progress = (refresh_interval - int(seconds_to_refresh)) / float(refresh_interval)
        progress = max(0.0, min(1.0, progress))
        bar_margin = padding_x
        bar_height = max(3, status_bar_height // 8)
        bar_width = max(40, width - (bar_margin * 2))
        bar_x = bar_margin
        bar_y = height - bar_height - 2
        fill_width = int(bar_width * progress)
        pygame.draw.rect(surface, (60, 60, 60), pygame.Rect(bar_x, bar_y, bar_width, bar_height), border_radius=2)
        if fill_width > 0:
            pygame.draw.rect(surface, (80, 190, 110), pygame.Rect(bar_x, bar_y, fill_width, bar_height), border_radius=2)

    mode = ui_state["mode"]
    if mode == "menu":
        _draw_main_menu_overlay(display)
    elif mode == "add_secret":
        _draw_secret_entry_overlay(display, ui_state)
    elif mode == "confirm_secret":
        _draw_confirm_secret_overlay(display, ui_state)

    _draw_toast_overlay(surface, width, content_bottom, ui_state)

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
    ui_state = _create_ui_state()
    last_next_refresh = None
    refresh_interval = min(item["step"] for item in codes)
    print("Watching TOTP codes. Press Ctrl+C to stop.")
    try:
        while True:
            now = current_time()
            _clear_expired_toast(ui_state, now)
            ui_state, ui_changed, ui_action = _handle_ui_events(display, ui_state, len(codes), now)

            if ui_action == "rotate" and display is not None:
                _rotate_display(display)
                ui_changed = True
            elif ui_action == "secret_saved":
                codes = build_codes()
                refresh_interval = min(item["step"] for item in codes)
                last_next_refresh = None
                current_codes = generate_totps(codes, now=now)
                write_codes_json(OUTPUT_FILE, current_codes)
                last_codes = current_codes
                ui_changed = True

            next_refresh = min(seconds_until_next_step(item["step"], now) for item in codes)
            should_render = ui_changed
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
                synced_time = False

            if should_render and current_codes is not None:
                render_codes(
                    display,
                    current_codes,
                    ui_state=ui_state,
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
    finally:
        _set_text_input_enabled(False)
        _stop_system_keyboard(ui_state)


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
        ui_state=_create_ui_state(),
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
