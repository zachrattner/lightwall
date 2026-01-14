import time

from hw.led.led_controller import LEDController
from hw.motor.motor_controller import MotorController
from engagement_controller import EngagementController
from hw.hw_state import HWState
from util.logger import info, warning
from util.env_utils import load_env_file

HW_STATE = HWState()

def main():
    led_controller = None
    motor_controller = None
    board_serials = None
    engagement = None
    try:
        load_env_file()

        HW_STATE.load_hw_map()
        board_serials = HW_STATE.connect_peripherals()
        led_controller = LEDController(HW_STATE.hw_map, board_serials)
        motor_controller = MotorController(HW_STATE.hw_map, board_serials)

        info(f"Updated HW_MAP: {HW_STATE.hw_map}")
        info(f"Initialized LEDController with {len(led_controller.leds)} LEDs.")
        info(f"Initialized MotorController with {len(motor_controller.motors)} motors.")

        engagement = EngagementController(HW_STATE, led_controller, motor_controller)
        engagement.start()

        info("EngagementController started. Press Ctrl+C to stop.")

        # Keep the main thread alive while idle animation runs
        while True:
            time.sleep(1)
        
    except KeyboardInterrupt:
        warning("Ctrl+C detected. Cleaning up...")

    finally:
        if engagement is not None:
            engagement.stop()
        if board_serials is not None:
            HW_STATE.disconnect_peripherals()
            info("Serial connections cleanup complete.")

if __name__ == "__main__":
    main()