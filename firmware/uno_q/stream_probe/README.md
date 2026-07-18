# Phoneharmonic UNO Q IMU Stream Probe

This isolated Arduino App proves the complete physical path from a Modulino
Movement to the real Phoneharmonic server:

```text
Movement -> UNO Q MCU -> Arduino Bridge -> UNO Q Linux -> WiFi -> server /ws
```

It deliberately excludes gesture classification, LEDs, buzzers, AI mode, and
phone selection. The only output is the production `wand.imu` stream.

## Hardware and prerequisites

- Connect the Modulino Movement to the UNO Q Qwiic connector.
- Provision the UNO Q and laptop onto the same WiFi network.
- Confirm `ssh arduino@<board-name>.local` works.
- Use a current UNO Q Linux image containing `arduino-app-cli`.
- Install the laptop server dependencies:

  ```bash
  python3 -m pip install -r server/requirements.txt
  ```

Find the laptop's WiFi IPv4 address with `ipconfig getifaddr en0` on macOS,
`hostname -I` on Linux, or `ipconfig` on Windows. Do not use `127.0.0.1`: that
would refer to the UNO Q itself when used by the board.

Close browser, simulator, and CV wand clients before testing. Phoneharmonic has
one active wand slot, and the most recently connected wand owns it.

## Run the test

From any working directory, run:

```bash
./firmware/uno_q/stream_probe/run_probe.sh \
  --board arduino@uno-q.local \
  --server-ip 192.168.1.42
```

The launcher copies only this isolated App to
`/home/arduino/ArduinoApps/phoneharmonic-stream-probe`, compiles and flashes its
MCU sketch, starts its Linux process, starts or reuses the real server, and runs
the guided monitor. It never stores WiFi credentials or a generated IP address
in the repository.

Use `--dry-run` to validate arguments without contacting the board. Use
`--keep-running` to leave the minimal streamer running after a successful test
for integration with the rest of the application. Without that flag, the
launcher stops the probe App when it exits.

## Physical phases

The default test lasts 30 seconds:

1. **0–8 seconds:** hold the board flat and completely still.
2. **8–20 seconds:** rotate it clearly around its vertical/yaw axis.
3. **20–30 seconds:** stop and hold it still again.

PASS requires a connected hardware wand, 45–70 sensor frames/s, 8–15 batches/s,
no invalid frames or sequence gaps, no receive pause over one second, gravity
near 9.81 m/s², low gyro activity while still, and obvious yaw movement during
the middle phase.

## Troubleshooting

| Symptom | Likely boundary |
|---|---|
| No hardware wand in the roster | Deployment, WiFi, server URL, or handshake |
| Wand connects but receives zero frames | Modulino initialization or MCU/Linux Bridge |
| Gravity is near `1` instead of `9.81` | Missing g-to-m/s² conversion |
| Invalid frames | CSV parsing, non-finite sensor output, or serialization |
| Low rate or long pauses | MCU scheduling, Bridge queue pressure, or WiFi |
| Frames arrive but yaw never moves | Gyro axis mapping or physical sensor reading |
| Server reports sequence gaps | Linux batching, reconnects, or WiFi loss |

Board-side logs are available after deployment with:

```bash
ssh arduino@uno-q.local \
  "arduino-app-cli app logs /home/arduino/ArduinoApps/phoneharmonic-stream-probe --all"
```

## Useful options

```text
--server-port PORT   default 8080
--session NAME       default lol1
--duration SECONDS   default 30
--keep-running       preserve the running board App after PASS
--dry-run            show resolved settings without changing anything
```

The Arduino App structure and dependencies are declared in `app.yaml` and
`sketch/sketch.yaml`; no App Lab GUI action is required.
