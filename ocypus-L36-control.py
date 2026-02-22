#!/usr/bin/env python3
"""
ocypus-control.py
---------------------------------
Ocypus Iota L36 LCD driver (Linux)

Modified from ocypus-control.py, all credits to moyunkz - https://github.com/moyunkz/ocypus-a40-digital-linux

Ajustado para controladores que aceitam UPDATE via HID *output report* (device.write),
com report ID 0x07, comprimento 64, e header 0xFF 0xFF + 3 dígitos (centenas/dezenas/unidades).

FEATURES
  • Auto-detects a likely working HID interface (prefers vendor usage_page and higher interface numbers).
  • Supports temperature display in Celsius (°C) and Fahrenheit (°F) (conversion only; unit icon byte unknown).
  • Works with any psutil sensor.
  • Keeps the panel alive with periodic updates.
  • Includes a command to generate and install a systemd service.
"""

import argparse
import hid
import os
import signal
import sys
import textwrap
import time
from types import FrameType
from typing import List, Dict, Any, Optional, Tuple

import psutil

# --- Constants ---
VID, PID = 0x1a2c, 0x434d
REPORT_ID = 0x07
REPORT_LENGTH = 64  # IMPORTANT: output report length for this device
DEFAULT_SENSOR_SUBSTR = "k10temp"
DEFAULT_REFRESH_RATE = 1.0  # seconds
KEEPALIVE_INTERVAL = 2.0  # seconds


class OcypusController:
    """Manages the Ocypus LCD device."""

    def __init__(self):
        self.device: Optional[hid.device] = None
        self.interface_number: Optional[int] = None
        self.path: Optional[bytes] = None

    def __enter__(self):
        """Context manager entry: opens the device."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: closes the device."""
        self.close()

    @staticmethod
    def _unique_devices(devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate enumerate() results by (interface_number, path)."""
        uniq = {}
        for d in devices:
            key = (d.get("interface_number"), d.get("path"))
            if key[0] is None or key[1] is None:
                continue
            uniq[key] = d
        return list(uniq.values())

    @staticmethod
    def _sorted_candidates(devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prefer vendor-defined usage_page (>= 0xFF00), and higher interface_number.
        This usually avoids the "keyboard-like" interface.
        """
        def score(d: Dict[str, Any]) -> Tuple[int, int]:
            up = d.get("usage_page") or 0
            iface = d.get("interface_number") or 0
            vendor = 1 if up >= 0xFF00 else 0
            return (vendor, iface)

        return sorted(devices, key=score, reverse=True)

    @staticmethod
    def _build_display_report(value_int: int) -> bytearray:
        """
        Build report:
          [0]  = REPORT_ID
          [1]  = 0xFF
          [2]  = 0xFF
          [3]  = hundreds
          [4]  = tens
          [5]  = ones
        Rest zeros.
        """
        value_int = max(0, min(999, int(value_int)))
        h = value_int // 100
        t = (value_int % 100) // 10
        o = value_int % 10

        report = bytearray([REPORT_ID] + [0] * (REPORT_LENGTH - 1))
        report[1] = 0xFF
        report[2] = 0xFF
        report[3] = h
        report[4] = t
        report[5] = o
        return report

    def open(self) -> bool:
        """Opens the first likely working Ocypus device interface."""
        devices = hid.enumerate(VID, PID)
        if not devices:
            print("No Ocypus cooler found.")
            return False

        candidates = self._sorted_candidates(self._unique_devices(devices))

        last_err = None
        for device_info in candidates:
            interface_number = device_info.get("interface_number")
            path = device_info.get("path")
            if interface_number is None or path is None:
                continue

            device = None
            try:
                device = hid.device()
                device.open_path(path)

                # Minimal write test (does not guarantee display change, but validates output report path)
                probe = self._build_display_report(0)
                written = device.write(probe)
                if written <= 0:
                    raise RuntimeError(f"write() returned {written}")

                self.device = device
                self.interface_number = interface_number
                self.path = path
                print(f"Connected to Ocypus cooler on interface {interface_number}")
                return True

            except Exception as e:
                last_err = e
                # Uncomment to debug candidate selection:
                # up = device_info.get("usage_page")
                # us = device_info.get("usage")
                # print(f"Failed interface {interface_number} (usage_page={up}, usage={us}): {e}")
                try:
                    if device:
                        device.close()
                except Exception:
                    pass
                continue

        print("Error: No working Ocypus interface found.")
        if last_err:
            print(f"Last error: {last_err}")
        return False

    def close(self):
        """Closes the device connection."""
        if self.device:
            try:
                self.device.close()
            except Exception as e:
                print(f"Error closing device: {e}")
            finally:
                self.device = None
                self.interface_number = None
                self.path = None

    def send_temperature(self, temp_celsius: float, unit: str = "c") -> bool:
        """
        Sends temperature data to the LCD display.

        Note: unit "flag/icon byte" is unknown for this report format.
        We do conversion C<->F and show digits only.
        """
        if not self.device:
            print("Device not connected.")
            return False

        # Convert temperature based on unit
        if unit.lower() == "f":
            display_temp = temp_celsius * 9 / 5 + 32
        else:
            display_temp = temp_celsius

        # Keep within a reasonable range; L36 supports 3 digits.
        value_int = int(round(display_temp))
        value_int = max(0, min(212, value_int))  # safe cap; adjust later if needed

        try:
            report = self._build_display_report(value_int)
            written = self.device.write(report)
            if written <= 0:
                raise RuntimeError(f"write() returned {written}")
            return True
        except Exception as e:
            print(f"Error sending temperature: {e}")
            return False

    def blank_display(self) -> bool:
        """
        Attempts to blank the display.

        Some devices may show 000 instead of blank depending on firmware.
        If your device shows 000 and you want true blank, we can sniff/adjust later.
        """
        if not self.device:
            print("Device not connected.")
            return False

        try:
            report = bytearray([REPORT_ID] + [0] * (REPORT_LENGTH - 1))
            written = self.device.write(report)
            if written <= 0:
                raise RuntimeError(f"write() returned {written}")
            return True
        except Exception as e:
            print(f"Error blanking display: {e}")
            return False

    def list_devices(self) -> List[Dict[str, Any]]:
        """Lists all Ocypus devices found (deduplicated)."""
        return self._unique_devices(hid.enumerate(VID, PID))


def get_temperature_sensors() -> Dict[str, List[Tuple[str, float]]]:
    """Gets all available temperature sensors."""
    try:
        return psutil.sensors_temperatures()
    except Exception as e:
        print(f"Error reading temperature sensors: {e}")
        return {}


def find_sensor_by_substring(
    sensors: Dict[str, List[Tuple[str, float]]],
    substring: str
) -> Optional[Tuple[str, float]]:
    """Finds the first sensor containing the given substring."""
    for sensor_name, sensor_list in sensors.items():
        if substring.lower() in sensor_name.lower() and sensor_list:
            return sensor_name, sensor_list[0].current
    return None


def build_temperature_report(sensor_substring: str = DEFAULT_SENSOR_SUBSTR) -> str:
    """Builds a temperature report for debugging."""
    sensors = get_temperature_sensors()
    if not sensors:
        return "No temperature sensors found."

    report_lines = ["Available temperature sensors:"]
    for sensor_name, sensor_list in sensors.items():
        for sensor in sensor_list:
            temp_str = f"{sensor.current:.1f}°C"
            highlight = " ← SELECTED" if sensor_substring.lower() in sensor_name.lower() else ""
            report_lines.append(f"  {sensor_name}: {temp_str}{highlight}")

    return "\n".join(report_lines)


def run_display_loop(controller: OcypusController, sensor_substring: str, unit: str, refresh_rate: float):
    """Runs the main temperature display loop."""
    print(f"Starting temperature display (unit: {unit.upper()}, refresh: {refresh_rate}s)")
    print("Press Ctrl+C to stop.")

    last_keepalive = time.time()

    while True:
        try:
            sensors = get_temperature_sensors()
            sensor_data = find_sensor_by_substring(sensors, sensor_substring)

            if sensor_data:
                sensor_name, temp_celsius = sensor_data
                success = controller.send_temperature(temp_celsius, unit)
                if success:
                    display_temp = temp_celsius if unit.lower() == "c" else temp_celsius * 9 / 5 + 32
                    unit_symbol = "°C" if unit.lower() == "c" else "°F"
                    print(f"\rSensor: {sensor_name} | Temp: {display_temp:.1f}{unit_symbol}", end="", flush=True)
                else:
                    print("\rFailed to send temperature", end="", flush=True)
            else:
                print(f"\rSensor containing '{sensor_substring}' not found", end="", flush=True)
                current_time = time.time()
                if current_time - last_keepalive >= KEEPALIVE_INTERVAL:
                    controller.send_temperature(0, unit)
                    last_keepalive = current_time

            time.sleep(refresh_rate)

        except KeyboardInterrupt:
            print("\nStopping temperature display.")
            break
        except Exception as e:
            print(f"\nError in display loop: {e}")
            time.sleep(refresh_rate)


def install_systemd_service(unit: str = "c", sensor: str = DEFAULT_SENSOR_SUBSTR, rate: float = DEFAULT_REFRESH_RATE,
                           service_name: str = "ocypus-lcd"):
    """Creates and installs a systemd service unit."""
    script_path = os.path.abspath(__file__)

    service_content = f"""[Unit]
Description=Ocypus LCD Temperature Display
After=multi-user.target

[Service]
Type=simple
User=root
ExecStart={sys.executable} {script_path} on -u {unit} -s "{sensor}" -r {rate}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    service_file_path = f"/etc/systemd/system/{service_name}.service"

    try:
        with open(service_file_path, "w") as f:
            f.write(service_content)

        print(f"Systemd service created: {service_file_path}")
        print("\nTo enable and start the service:")
        print("  sudo systemctl daemon-reload")
        print(f"  sudo systemctl enable --now {service_name}.service")
        print("\nTo check service status:")
        print(f"  systemctl status {service_name}.service")

    except PermissionError:
        print("Error: Permission denied. Run with sudo to install the service.")
    except Exception as e:
        print(f"Error creating service file: {e}")


def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Ocypus LCD driver for Linux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          %(prog)s list                    # List all Ocypus devices
          %(prog)s on                      # Start temperature display (Celsius)
          %(prog)s on -u f                 # Start temperature display (Fahrenheit)
          %(prog)s on -s "coretemp" -u c   # Use specific sensor
          %(prog)s off                     # Turn off display
          %(prog)s install-service         # Install systemd service
        """)
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("list", help="List all found Ocypus cooler devices")

    on_parser = subparsers.add_parser("on", help="Turn on display and stream temperature")
    on_parser.add_argument("-u", "--unit", choices=["c", "f"], default="c",
                           help="Temperature unit: c=Celsius, f=Fahrenheit (default: c)")
    on_parser.add_argument("-s", "--sensor", default=DEFAULT_SENSOR_SUBSTR,
                           help=f"Substring of psutil sensor to use (default: {DEFAULT_SENSOR_SUBSTR})")
    on_parser.add_argument("-r", "--rate", type=float, default=DEFAULT_REFRESH_RATE,
                           help=f"Update interval in seconds (default: {DEFAULT_REFRESH_RATE})")

    subparsers.add_parser("off", help="Turn off (blank) the display")

    service_parser = subparsers.add_parser("install-service", help="Install systemd unit for background operation")
    service_parser.add_argument("-u", "--unit", choices=["c", "f"], default="c",
                                help="Temperature unit for the service (default: c)")
    service_parser.add_argument("-s", "--sensor", default=DEFAULT_SENSOR_SUBSTR,
                                help=f"Sensor substring for the service (default: {DEFAULT_SENSOR_SUBSTR})")
    service_parser.add_argument("-r", "--rate", type=float, default=DEFAULT_REFRESH_RATE,
                                help=f"Update interval for the service (default: {DEFAULT_REFRESH_RATE})")
    service_parser.add_argument("--name", default="ocypus-lcd",
                                help="Name for the systemd unit file (default: ocypus-lcd)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    def signal_handler(signum: int, frame: Optional[FrameType]):
        print("\nReceived interrupt signal. Exiting gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.command == "list":
        controller = OcypusController()
        devices = controller.list_devices()
        if devices:
            print(f"Found {len(devices)} Ocypus cooler device(s):")
            for i, device in enumerate(devices, 1):
                interface = device.get("interface_number", "Unknown")
                path = device.get("path", "Unknown")
                up = device.get("usage_page")
                us = device.get("usage")
                p = path.decode() if isinstance(path, (bytes, bytearray)) else str(path)
                print(f"  {i}. Interface {interface} (Path: {p}) usage_page={up} usage={us}")
        else:
            print("No Ocypus cooler devices found.")

    elif args.command == "on":
        with OcypusController() as controller:
            if controller.device:
                run_display_loop(controller, args.sensor, args.unit, args.rate)

    elif args.command == "off":
        with OcypusController() as controller:
            if controller.device:
                success = controller.blank_display()
                print("Display turned off." if success else "Failed to turn off display.")

    elif args.command == "install-service":
        install_systemd_service(args.unit, args.sensor, args.rate, args.name)


if __name__ == "__main__":
    main()
