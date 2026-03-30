#!/usr/bin/env python3
"""Test script to verify display rotation in pygame"""

import os
import sys

import pygame


BASE_WIDTH = 480
BASE_HEIGHT = 320
MARKER_SIZE = 40


def test_rotation(rotation: int = 0, driver: str = "auto"):
    """Test if pygame rotation is applied to display"""

    print(f"\n{'='*70}")
    print("DISPLAY ROTATION TEST")
    print(f"{'='*70}")
    print(f"Rotation: {rotation}°")
    print(f"Driver: {driver}")
    print(f"{'='*70}\n")

    # Set SDL video driver
    if driver != "auto":
        os.environ["SDL_VIDEODRIVER"] = driver

    # Initialize pygame
    try:
        pygame.init()
        print("Pygame initialized")
    except Exception as e:
        print(f"Failed to initialize pygame: {e}")
        return False

    # Create display surface
    try:
        screen = pygame.display.set_mode((BASE_WIDTH, BASE_HEIGHT), flags=pygame.NOFRAME)
        print(f"Display created: {BASE_WIDTH}x{BASE_HEIGHT}")
    except Exception as e:
        print(f"Failed to create display: {e}")
        return False

    rotated_width = BASE_WIDTH
    rotated_height = BASE_HEIGHT
    if rotation in (90, 270):
        rotated_width, rotated_height = rotated_height, rotated_width

    print(f"  Expected size after rotation: {rotated_width}x{rotated_height}")
    print(f"  Actual surface size: {screen.get_width()}x{screen.get_height()}")

    if rotation != 0:
        if screen.get_width() == rotated_width and screen.get_height() == rotated_height:
            print("  Rotation applied (dimensions swapped correctly)")
        else:
            print("  Rotation not applied (dimensions unchanged)")
            print("\n  NOTE: Pygame rotation on Raspberry Pi typically requires:")
            print("    1. Hardware driver support (device tree overlay)")
            print("    2. Or manual surface rotation using pygame.transform.rotate()")
            print("    3. Or framebuffer rotation via /boot/config.txt")
    else:
        print("  No rotation (0°)")

    # Draw test pattern: colored corners to verify orientation
    screen.fill((0, 0, 0))

    # Top-left (Red)
    pygame.draw.rect(screen, (255, 0, 0), pygame.Rect(0, 0, MARKER_SIZE, MARKER_SIZE))
    # Top-right (Green)
    pygame.draw.rect(screen, (0, 255, 0), pygame.Rect(rotated_width - MARKER_SIZE, 0, MARKER_SIZE, MARKER_SIZE))
    # Bottom-left (Blue)
    pygame.draw.rect(screen, (0, 0, 255), pygame.Rect(0, rotated_height - MARKER_SIZE, MARKER_SIZE, MARKER_SIZE))
    # Bottom-right (Yellow)
    pygame.draw.rect(
        screen,
        (255, 255, 0),
        pygame.Rect(rotated_width - MARKER_SIZE, rotated_height - MARKER_SIZE, MARKER_SIZE, MARKER_SIZE),
    )

    # Draw center crosshair
    center_x, center_y = rotated_width // 2, rotated_height // 2
    pygame.draw.line(screen, (255, 255, 255), (center_x - 20, center_y), (center_x + 20, center_y), 2)
    pygame.draw.line(screen, (255, 255, 255), (center_x, center_y - 20), (center_x, center_y + 20), 2)

    # Write rotation angle in corner
    font = pygame.font.Font(None, 48)
    text = font.render(f"{rotation}°", True, (200, 200, 200))
    screen.blit(text, (10, 10))

    pygame.display.flip()
    print("\nTest pattern displayed:")
    print("  • Red square: top-left")
    print("  • Green square: top-right")
    print("  • Blue square: bottom-left")
    print("  • Yellow square: bottom-right")
    print("  • White crosshair: center")
    print("\nIf rotation is working, these should match the expected orientation.")

    # Wait for user input
    print("\nPress SPACE to continue, Q to quit...")
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                waiting = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    waiting = False
                elif event.key == pygame.K_SPACE:
                    waiting = False

    pygame.quit()
    print("\nTest complete\n")
    return True


if __name__ == "__main__":
    rotation = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    driver = sys.argv[2] if len(sys.argv) > 2 else "auto"
    
    if rotation not in (0, 90, 180, 270):
        print(f"Invalid rotation: {rotation}. Must be 0, 90, 180, or 270.")
        sys.exit(1)
    
    test_rotation(rotation, driver)
