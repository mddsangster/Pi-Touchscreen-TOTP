# OTP Display Project

A Raspberry Pi Zero project that generates TOTP codes for configured accounts and displays them on a GPIO-connected 3.5" touchscreen using pygame.

## Features

- Live TOTP code display with configurable NTP time sync
- Touch-driven in-app menu (tap anywhere to open)
- **Add Secret** — enter a new TOTP secret via the built-in on-screen keypad; up to 4 accounts supported
- **Rotate Screen** — cycle between 0 / 90 / 180 / 270° and save to config
- **Battery Saver Mode** — turns off the backlight and pauses NTP sync to reduce power draw; can be toggled manually or set to activate automatically on a schedule (6 PM – 6 AM Mon–Fri, all day Sat–Sun)
- **Landscape 2-column layout** — when rotation is 0° or 180° and more than 2 accounts are active, codes are arranged in two columns with large, easy-to-read digits

## Files

- `generate_codes.py` - main script that loads secrets, generates TOTP codes, and optionally renders them to the display.
- `synchronized_time.py` - optional NTP time sync helper plus manual fallback UI.
- `secrets.json.example` - template for storing the base32 shared secrets.
- `scripts/install_python_packages.sh` - installs required Python packages from apt.
- `install_startup.sh` - installs the systemd service and runs package installation once.
- `scripts/pull_latest.sh` - safely pulls latest git changes and restarts the OTP service when updated.
- `scripts/install_autopull.sh` - installs a systemd timer for hands-off Pi auto-pull.
- `scripts/autosync.ps1` - Windows helper that commits and pushes local changes.
- `scripts/test_rotation.py` - manual pygame rotation test utility.
- `debug/` - local-only folder (gitignored) for diagnostic scripts and output files.

## Setup

1. Copy `secrets.json.example` to `secrets.json`.
2. Replace the placeholder secrets with real base32 values.
3. Create a local Python virtual environment for development:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Make the install scripts executable:

```bash
chmod +x install_startup.sh scripts/install_python_packages.sh scripts/pull_latest.sh scripts/install_autopull.sh
```

5. Run the startup installer as root:

```bash
sudo ./install_startup.sh
```

This will:
- install required Python packages
- create a systemd service for `generate_codes.py --watch --pygame`
- enable the service at boot

## Hands-Off Pi Auto-Pull

Install the auto-pull timer so the Pi fetches from GitHub automatically:

```bash
sudo ./scripts/install_autopull.sh main origin 1min
```

This creates:
- `otp-autopull.service` (one-shot pull task)
- `otp-autopull.timer` (runs every minute by default)

Useful commands:

```bash
sudo systemctl status otp-autopull.timer --no-pager
sudo systemctl start otp-autopull.service
sudo journalctl -u otp-autopull.service -n 100 --no-pager
```

Notes:
- If the Pi has local uncommitted changes, auto-pull skips safely.
- When new commits are pulled, `otp-codes.service` is restarted automatically.

## Configuration

Settings can be controlled either through `args.json` or command-line flags. The config file is simpler for persistent settings on the Pi.

### args.json

Create or edit `args.json` with:

```json
{
  "watch": true,
  "poll_interval": 1.0,
  "pygame_enabled": true,
  "desktop_mode": false,
  "display_rotation": 0,
  "ntp_server": "pool.ntp.org",
  "ntp_timeout": 5.0,
  "battery_saver_scheduled": false
}
```

**Options:**
- `watch` (bool): Run continuously (true) or once (false)
- `poll_interval` (float): Seconds between polls when watching
- `pygame_enabled` (bool): Display codes on screen
- `desktop_mode` (bool): Prefer desktop window over Pi framebuffer
- `display_rotation` (int): Rotate display: 0, 90, 180, or 270 degrees
- `ntp_server` (string): NTP server for time sync
- `ntp_timeout` (float): Timeout for NTP requests
- `battery_saver_scheduled` (bool): Enable the automatic battery-saver schedule (6 PM – 6 AM Mon–Fri, all day Sat–Sun). Can also be toggled from the on-screen menu; changes save immediately.

Command-line flags override config file values.

## Running manually

To run once without the display:

```bash
python3 generate_codes.py
```

To run with the touchscreen using pygame (required for display output):

```bash
python3 generate_codes.py --pygame
```

To run with 180-degree display rotation (for upside-down mounting):

```bash
python3 generate_codes.py --pygame --rotation 180
```

To run continuously with the touchscreen:

```bash
python3 generate_codes.py --watch --pygame
```

If you are developing on a desktop or Windows machine, use the desktop fallback:

```bash
python3 generate_codes.py --watch --pygame --desktop
```

### Changing Settings Without Redeployment

On the Raspberry Pi, simply edit `args.json` and restart the service:

```bash
nano args.json
sudo systemctl restart otp-codes.service
```

For example, to flip the display upside down, change `"display_rotation": 0` to `"display_rotation": 180`.

## Touch Menu

Tap anywhere on the display to open the menu. Available actions:

| Button | Action |
|---|---|
| **Add Secret** | Enter a new TOTP secret using the built-in keypad or system keyboard |
| **Rotate Screen** | Cycle through 0 / 90 / 180 / 270° and save to `args.json` |
| **Battery Saver: OFF / ON** | Toggle battery saver immediately; turns off backlight and pauses NTP sync |
| ☐ (checkbox next to Battery Saver) | Enable/disable the automatic schedule for battery saver |
| **Dismiss** | Close the menu |
| **Exit Program** | Quit the application |

### Adding a Secret

1. Tap **Add Secret** in the menu.
2. Tap the input field and type using your keyboard, or use the built-in on-screen keypad.
3. Tap **Submit** to preview the generated code.
4. If the code looks correct, tap **Confirm** to save. The new account appears immediately.
5. A maximum of 4 accounts is supported.

### Battery Saver Mode

When active, battery saver:
- Turns off the display backlight via `vcgencmd lcd_power`
- Pauses NTP time sync
- Stops regenerating codes (last known codes remain in memory)

The backlight is always restored when the application exits.

**Scheduled battery saver** activates automatically during:
- Monday – Friday: 6:00 PM to 6:00 AM
- Saturday and Sunday: all day

Enable it by ticking the checkbox next to the Battery Saver button in the menu, or set `"battery_saver_scheduled": true` in `args.json`.

## Display Layout

| Rotation | Layout |
|---|---|
| 90° / 270° (portrait) | Single column, codes stacked vertically |
| 0° / 180° (landscape), 1–2 accounts | Single column |
| 0° / 180° (landscape), 3–4 accounts | Two-column grid with enlarged digits (~2/5 of column width) |

## Notes

- `secrets.json` should contain only the real base32 secrets.
- `codes.json` is generated by the script and should not be stored in version control.
- The display is configured by Raspberry Pi DT overlays, so `pygame` is used for rendering to the framebuffer.
- If the Pi has internet access, the script will attempt to synchronize time via NTP before generating codes.

## User

The systemd service created by `install_startup.sh` runs as the default system user for services. If you want it to run under a specific account, update the `User=` field in `/etc/systemd/system/otp-codes.service`.

## Cleanup

Remove generated files if needed:

```bash
rm -f codes.json
rm -rf __pycache__
```
