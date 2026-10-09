import ctypes
import math
import sys
import time

import cv2
import mediapipe as mp
import pyautogui


CAMERA_INDEX = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30
CURSOR_MARGIN = 0.025
MIN_SMOOTHING = 0.10
MAX_SMOOTHING = 0.60
CURSOR_X_SPEED_MULTIPLIER = 1.0
CURSOR_Y_SPEED_MULTIPLIER = 1.0
PINCH_PALM_RATIO = 0.35
CLICK_COOLDOWN = 0.45
SCROLL_DEAD_ZONE = 0.012
SCROLL_MULTIPLIER = 250
APP_NAMES = ("NOTES", "BROWSER", "FILES")
COLOR_PALETTE = (
    ("RED", (62, 72, 224)),
    ("ORANGE", (45, 151, 238)),
    ("YELLOW", (57, 222, 246)),
    ("GREEN", (76, 187, 111)),
    ("BLUE", (221, 142, 72)),
    ("PURPLE", (191, 94, 185)),
    ("WHITE", (232, 235, 229)),
    ("BLACK", (36, 40, 39)),
)
PALM_CENTER_INDICES = (0, 5, 9, 13, 17)


def palm_center(points):
    center_x = sum(points[index].x for index in PALM_CENTER_INDICES) / len(
        PALM_CENTER_INDICES
    )
    center_y = sum(points[index].y for index in PALM_CENTER_INDICES) / len(
        PALM_CENTER_INDICES
    )
    return center_x, center_y


def detect_finger_taps(
    index_up,
    middle_up,
    ring_up,
    pinky_up,
    previous_index_up,
    previous_middle_up,
):
    index_tap = (
        previous_index_up
        and not index_up
        and middle_up
        and ring_up
        and pinky_up
    )
    middle_tap = (
        previous_middle_up
        and not middle_up
        and index_up
        and ring_up
        and pinky_up
    )
    return index_tap, middle_tap


def landmark_distance(points, first_index, second_index, frame_width, frame_height):
    delta_x = (points[first_index].x - points[second_index].x) * frame_width
    delta_y = (points[first_index].y - points[second_index].y) * frame_height
    return math.hypot(delta_x, delta_y)


def map_cursor_position(x, y, screen_width, screen_height):
    margin = max(0.015, CURSOR_MARGIN)
    usable_range = max(0.001, 1.0 - (2 * margin))
    bounded_x = min(1.0 - margin, max(margin, x))
    bounded_y = min(1.0 - margin, max(margin, y))
    target_x = ((bounded_x - margin) / usable_range) * (screen_width - 1)
    target_y = ((bounded_y - margin) / usable_range) * (screen_height - 1)
    center_x = (screen_width - 1) / 2
    center_y = (screen_height - 1) / 2
    target_x = center_x + (target_x - center_x) * CURSOR_X_SPEED_MULTIPLIER
    target_y = center_y + (target_y - center_y) * CURSOR_Y_SPEED_MULTIPLIER
    target_x = min(screen_width - 1, max(1, target_x))
    target_y = min(screen_height - 1, max(1, target_y))
    return int(round(target_x)), int(round(target_y))


def configure_camera(camera):
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    camera.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
    camera.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    camera.set(cv2.CAP_PROP_BRIGHTNESS, 150)
    camera.set(cv2.CAP_PROP_CONTRAST, 80)
    camera.set(cv2.CAP_PROP_SATURATION, 80)
    camera.set(cv2.CAP_PROP_SHARPNESS, 100)
    if camera.get(cv2.CAP_PROP_AUTOFOCUS) >= 0:
        camera.set(cv2.CAP_PROP_AUTOFOCUS, 1)


def preprocess_frame(frame):
    if frame is None or frame.size == 0:
        return frame
    adjusted = cv2.convertScaleAbs(frame, alpha=1.10, beta=8)
    hsv = cv2.cvtColor(adjusted, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    s = cv2.equalizeHist(s)
    hsv = cv2.merge((h, s, v))
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def demo_app_regions(width):
    return {
        name: (32 + index * 104, 158, 120 + index * 104, 232)
        for index, name in enumerate(APP_NAMES)
    }


def point_inside(point_x, point_y, bounds):
    left, top, right, bottom = bounds
    return left <= point_x <= right and top <= point_y <= bottom


def color_swatch_regions():
    return [
        (32 + index * 72, 74, 84 + index * 72, 132)
        for index in range(len(COLOR_PALETTE))
    ]


def selected_color_at(x, y):
    for index, bounds in enumerate(color_swatch_regions()):
        if point_inside(x, y, bounds):
            return index
    return None


def draw_hand_preview(desktop, landmarks, camera_frame):
    height, width = desktop.shape[:2]
    left, top, right, bottom = width - 336, 48, width - 16, 300
    cv2.rectangle(desktop, (left, top), (right, bottom), (32, 42, 44), -1)
    label = "HAND DETECTED" if landmarks is not None else "SEARCHING"
    color = (138, 224, 182) if landmarks is not None else (175, 184, 178)
    cv2.putText(
        desktop,
        label,
        (left + 9, top + 19),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        color,
        1,
        cv2.LINE_AA,
    )
    if camera_frame is None:
        cv2.putText(
            desktop,
            "Camera preview unavailable",
            (left + 12, top + 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (224, 229, 224),
            1,
            cv2.LINE_AA,
        )
        return

    preview_width, preview_height = right - left - 20, bottom - top - 42
    preview = cv2.resize(camera_frame, (preview_width, preview_height))
    desktop[top + 30 : top + 30 + preview_height, left + 10 : right - 10] = preview


def handle_demo_click(x, y, active_app, width):
    if active_app is not None:
        if point_inside(x, y, (width - 390, 158, width - 366, 186)):
            return None, "Closed demo window"
        return active_app, f"Demo click in {active_app}"

    for name, bounds in demo_app_regions(width).items():
        if point_inside(x, y, bounds):
            return name, f"Opened demo {name.title()}"
    return active_app, "Demo click"


def render_demo_desktop(
    desktop,
    cursor_x,
    cursor_y,
    active_app,
    status,
    scroll_offset,
    show_context_menu,
    hand_landmarks,
    camera_frame,
    selected_color_index,
):
    height, width = desktop.shape[:2]
    desktop[:] = (43, 60, 54)
    cv2.rectangle(desktop, (0, 0), (width, 40), (30, 38, 41), -1)
    cv2.putText(
        desktop,
        "HAND GESTURE PROJECT  |  VIRTUAL COLOR DESK",
        (12, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (238, 241, 237),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        desktop,
        "PINCH A COLOR TO SELECT",
        (32, 62),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (223, 231, 223),
        1,
        cv2.LINE_AA,
    )
    for index, ((name, color), bounds) in enumerate(
        zip(COLOR_PALETTE, color_swatch_regions())
    ):
        left, top, right, bottom = bounds
        border = (246, 246, 238) if index == selected_color_index else (92, 107, 101)
        cv2.rectangle(desktop, (left - 3, top - 3), (right + 3, bottom + 3), border, 2)
        cv2.rectangle(desktop, (left, top), (right, bottom), color, -1)
        cv2.putText(
            desktop,
            name,
            (left, bottom + 19),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.31,
            (235, 239, 233),
            1,
            cv2.LINE_AA,
        )
    selected_name, selected_color = COLOR_PALETTE[selected_color_index]

    if active_app is None:
        colors = {"NOTES": (92, 185, 226), "BROWSER": (93, 194, 151), "FILES": (214, 161, 89)}
        for name, bounds in demo_app_regions(width).items():
            left, top, right, bottom = bounds
            cv2.rectangle(desktop, (left, top), (right, top + 58), (54, 68, 65), -1)
            cv2.rectangle(desktop, (left + 12, top + 9), (right - 12, top + 48), colors[name], -1)
            cv2.putText(
                desktop,
                name.title(),
                (left + 4, bottom - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (240, 241, 234),
                1,
                cv2.LINE_AA,
            )
        cv2.putText(
            desktop,
            "Pinch an icon to open its in-project demo",
            (32, 264),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (222, 229, 220),
            1,
            cv2.LINE_AA,
        )
        preview_left = max(360, width // 3)
        preview_right = max(preview_left + 180, width - 360)
        preview_top, preview_bottom = 158, height - 48
        cv2.rectangle(
            desktop,
            (preview_left, preview_top),
            (preview_right, preview_bottom),
            (224, 229, 222),
            -1,
        )
        cv2.putText(
            desktop,
            f"Selected color: {selected_name}",
            (preview_left + 22, preview_top + 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (48, 61, 56),
            1,
            cv2.LINE_AA,
        )
        swatch_left, swatch_top = preview_left + 22, preview_top + 58
        cv2.rectangle(
            desktop,
            (swatch_left, swatch_top),
            (preview_right - 22, preview_bottom - 24),
            selected_color,
            -1,
        )
    else:
        left, top, right, bottom = 22, 158, width - 360, height - 36
        cv2.rectangle(desktop, (left, top), (right, bottom), (231, 234, 228), -1)
        cv2.rectangle(desktop, (left, top), (right, top + 34), (44, 56, 58), -1)
        cv2.putText(
            desktop,
            f"{active_app.title()}  |  DEMO",
            (left + 12, top + 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (244, 245, 241),
            1,
            cv2.LINE_AA,
        )
        cv2.rectangle(desktop, (right - 30, top + 5), (right - 7, top + 28), (178, 72, 68), -1)
        cv2.putText(desktop, "X", (right - 23, top + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)

        content = {
            "NOTES": [
                "Gesture-controlled project notes",
                "This Notes app is simulated in this window.",
                "No text is entered into Windows or other apps.",
                "Use two raised fingers to scroll this demo.",
                "All gestures stay inside this project preview.",
            ],
            "BROWSER": [
                "demo://hand-controller/project",
                "This sample page is drawn locally.",
                "No browser is launched and no network is used.",
                "Use two raised fingers to scroll this demo.",
                "All gestures stay inside this project preview.",
            ],
            "FILES": [
                "Project files (simulation)",
                "hand_pc_controller.py",
                "requirements.txt",
                "README.md",
                "These labels do not open real files.",
            ],
        }[active_app]
        for index, line in enumerate(content):
            line_y = top + 68 + (index - scroll_offset) * 34
            if top + 52 < line_y < bottom - 12:
                cv2.putText(
                    desktop,
                    line,
                    (left + 14, line_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.43,
                    (53, 64, 59),
                    1,
                    cv2.LINE_AA,
                )

    draw_hand_preview(desktop, hand_landmarks, camera_frame)
    cv2.rectangle(desktop, (0, height - 28), (width, height), (28, 34, 37), -1)
    cv2.putText(
        desktop,
        status[:58],
        (10, height - 9),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.37,
        (232, 235, 231),
        1,
        cv2.LINE_AA,
    )
    if show_context_menu:
        menu_x = min(cursor_x + 12, width - 165)
        menu_y = min(cursor_y + 12, height - 80)
        cv2.rectangle(desktop, (menu_x, menu_y), (menu_x + 152, menu_y + 54), (35, 42, 44), -1)
        cv2.putText(desktop, "Demo context menu", (menu_x + 7, menu_y + 21), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (245, 245, 240), 1, cv2.LINE_AA)
        cv2.putText(desktop, "No system action", (menu_x + 7, menu_y + 43), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (154, 222, 184), 1, cv2.LINE_AA)

    cv2.circle(desktop, (cursor_x, cursor_y), 12, (22, 28, 29), -1)
    cv2.circle(desktop, (cursor_x, cursor_y), 8, selected_color, -1)


def main():
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.01

    camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not camera.isOpened():
        camera.release()
        camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        print("Camera open nahi hua.")
        print(
            "Windows Settings > Privacy & security > Camera mein Camera access "
            "aur Let desktop apps access your camera ON karein."
        )
        print("Doosri camera apps band karke dobara try karein.")
        return 1

    configure_camera(camera)

    hands_module = mp.solutions.hands
    drawing = mp.solutions.drawing_utils
    screen_width, screen_height = pyautogui.size()
    smoothed_x = None
    smoothed_y = None
    last_click_time = 0.0
    clicks_armed = False
    previous_left_click = False
    previous_right_click = False
    previous_index_up = False
    previous_middle_up = False
    previous_scroll_y = None
    status = "Palm: move cursor | Index tap: left click | Middle tap: right click"
    window_name = "Hand Camera | System Mouse Control | Esc: Exit"
    window_width = 480
    window_height = 360
    window_screen_width = ctypes.windll.user32.GetSystemMetrics(0)
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, window_width, window_height)
    cv2.moveWindow(
        window_name,
        max(0, window_screen_width - window_width - 24),
        32,
    )
    cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

    try:
        with hands_module.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.65,
            min_tracking_confidence=0.60,
        ) as hands:
            while True:
                success, frame = camera.read()
                if not success:
                    print("Camera se frame nahi mila.")
                    break

                frame = cv2.flip(frame, 1)
                frame = preprocess_frame(frame)
                frame_height, frame_width = frame.shape[:2]
                result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                status = "Hand dikhaiye - Esc se band karein"
                hand_points = None

                if result.multi_hand_landmarks:
                    hand = result.multi_hand_landmarks[0]
                    points = hand.landmark
                    hand_points = points

                    index_up = points[8].y < points[6].y
                    middle_up = points[12].y < points[10].y
                    ring_up = points[16].y < points[14].y
                    pinky_up = points[20].y < points[18].y

                    palm_width = landmark_distance(
                        points, 5, 17, frame_width, frame_height
                    )
                    pinch_threshold = palm_width * PINCH_PALM_RATIO
                    thumb_index_distance = landmark_distance(
                        points, 4, 8, frame_width, frame_height
                    )
                    thumb_middle_distance = landmark_distance(
                        points, 4, 12, frame_width, frame_height
                    )
                    right_pinch = (
                        index_up
                        and not middle_up
                        and thumb_middle_distance < pinch_threshold
                    )
                    left_pinch = (
                        not right_pinch
                        and thumb_index_distance < pinch_threshold
                    )
                    index_tap, middle_tap = detect_finger_taps(
                        index_up,
                        middle_up,
                        ring_up,
                        pinky_up,
                        previous_index_up,
                        previous_middle_up,
                    )
                    left_click_gesture = left_pinch or index_tap
                    right_click_gesture = right_pinch or middle_tap
                    now = time.monotonic()
                    if not left_pinch and not right_pinch:
                        clicks_armed = True

                    palm_x, palm_y = palm_center(points)
                    target_x, target_y = map_cursor_position(
                        palm_x,
                        palm_y,
                        screen_width,
                        screen_height,
                    )
                    if smoothed_x is None:
                        smoothed_x, smoothed_y = target_x, target_y
                    else:
                        movement = math.hypot(
                            target_x - smoothed_x, target_y - smoothed_y
                        )
                        smoothing = min(
                            MAX_SMOOTHING,
                            max(
                                MIN_SMOOTHING,
                                2 * movement / max(screen_width, screen_height),
                            ),
                        )
                        smoothed_x += (target_x - smoothed_x) * smoothing
                        smoothed_y += (target_y - smoothed_y) * smoothing
                    pyautogui.moveTo(int(smoothed_x), int(smoothed_y))
                    status = "Real cursor: palm center"

                    if clicks_armed and left_click_gesture and not previous_left_click:
                        if now - last_click_time >= CLICK_COOLDOWN:
                            pyautogui.click()
                            status = "Left click: real desktop"
                            last_click_time = now
                    elif clicks_armed and right_click_gesture and not previous_right_click:
                        if now - last_click_time >= CLICK_COOLDOWN:
                            pyautogui.rightClick()
                            last_click_time = now
                            status = "Right click: real desktop"

                    scrolling = (
                        index_up and middle_up and not ring_up and not pinky_up
                    )
                    if scrolling:
                        current_y = (points[8].y + points[12].y) / 2
                        if previous_scroll_y is not None:
                            delta_y = previous_scroll_y - current_y
                            if abs(delta_y) > SCROLL_DEAD_ZONE:
                                pyautogui.scroll(
                                    max(-25, min(25, int(delta_y * SCROLL_MULTIPLIER)))
                                )
                        previous_scroll_y = current_y
                        status = "Scroll: real desktop"
                    else:
                        previous_scroll_y = None

                    previous_left_click = left_click_gesture
                    previous_right_click = right_click_gesture
                    previous_index_up = index_up
                    previous_middle_up = middle_up
                    drawing.draw_landmarks(
                        frame, hand, hands_module.HAND_CONNECTIONS
                    )
                else:
                    previous_left_click = False
                    previous_right_click = False
                    previous_index_up = False
                    previous_middle_up = False
                    previous_scroll_y = None

                cv2.rectangle(frame, (0, 0), (frame_width, 42), (25, 30, 35), -1)
                cv2.putText(
                    frame,
                    "REAL MOUSE CONTROL ACTIVE  |  ESC: EXIT",
                    (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.43,
                    (235, 245, 240),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow(window_name, frame)

                if cv2.waitKey(1) & 0xFF == 27:
                    break

    except pyautogui.FailSafeException:
        print("Emergency stop: mouse top-left corner par pahunch gaya.")
    except KeyboardInterrupt:
        print("Hand mouse control band kiya gaya.")
    finally:
        camera.release()
        cv2.destroyAllWindows()

    return 0

if __name__ == "__main__":
    sys.exit(main())