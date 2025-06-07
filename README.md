# RobotStreamer

A simple three-node system (Robot / Operator / Recorder) that demonstrates WebRTC video streaming, command/control via WebSockets, real-time latency display and video recording – all containerised with Docker Compose.

---

## Architecture

```
+---------+       WebRTC        +-----------+
| Robot   |  <----------------> | Operator  |
| Node    |                    /+-----------+
+----+----+                   /
     ^  ^   WebSockets        /
     |  +--------------------+
     |                       \
     |  WebRTC               \
     |                        +-----------+
     +----------------------> | Recorder  |
                              | Node      |
                              +-----------+
```

* **Robot Node** – Captures webcam frames, overlays text, embeds timestamps and streams video to any connected peer. Accepts `play`, `pause` and `text` commands over the same WebSocket used for signaling.
* **Operator Node** – Receives and displays the live stream with latency overlay. Sends keyboard commands to control the robot.
* **Recorder Node** – Receives the stream, records it to *recording.mp4* and logs every control command with a timestamp.

---

## Requirements

* Docker ≥ 20.10
* Docker Compose plugin (or `docker-compose` v1)  
  `brew install docker` on macOS or follow [Docker docs](https://docs.docker.com/)
* A webcam accessible as **/dev/video0** on the host (Linux).  
  macOS/Windows users can run the robot node directly on the host or with additional camera-pass-through solutions.

---

## Build

Clone the repo and run:

```bash
cd RobotStreamer
# Build all three services
docker compose build        # docker-compose build (v1) also works
```

Build output shows each of the `robot`, `operator` and `recorder` images being created with all required Python dependencies, OpenCV, FFmpeg and aiortc.

---

## Run

```bash
# Start the stack (press Ctrl-C to stop)
docker compose up           # or docker-compose up
```

Service rundown:

* **robot** – exposes port **8765** internally, streams your webcam.
* **operator** – connects to the robot service, opens an OpenCV window.
* **recorder** – connects to the robot service and saves *recording.mp4* + *commands.jsonl* in its container.

### Operator controls

Inside the *operator* container a small CLI waits for keyboard input:

* `p` – Pause video on Robot side
* `r` – Resume video
* `t` – Send a custom text message (will be overlaid on the robot video)

Latency (capture → display) is measured automatically and shown on the video.

---

## Persisting recordings

`recorder` writes files **inside** its container. To store them on the host simply add (already added) a volume in `compose.yml`, e.g.

```yaml
recorder:
  build: ./recorder_node
  volumes:
    - ./output:/recorder_node   # host ./output ➔ container /recorder_node
  depends_on:
    - robot
```

With that tweak the recorded *recording.mp4* and *commands.jsonl* will (now does) appear in `./output` on your host.

---

## Troubleshooting

* Ensure no other process is using the webcam.
* On macOS/Windows you may need to run the robot node natively or grant camera access to Docker.
* If ICE negotiation fails, verify that containers can reach each other via the default Docker network (they should with Compose).

---

## No webcam? Simulating video on any platform

`/dev/video0` is a Linux‐specific device file created by the V4L2 (Video-for-Linux) driver.  
On macOS, Windows, CI services, or even Linux machines without a camera the device does **not** exist, so the Docker mapping inside `compose.yml` fails.

You have three easy work-arounds:

1. **Run the Robot Node directly on the host** (macOS / Windows)
   * Comment-out the `robot:` service (or its `devices:` line) in *compose.yml*.
   * `cd robot_node && python robot_node.py` – the process can access the host camera directly; the other services still connect to it via `ws://host.docker.internal:8765`.

2. **Use a fallback video inside the container** (all platforms)
   * Delete the `devices:` stanza from the `robot:` service so Docker no longer expects `/dev/video0`.
   * Add a short `sample.mp4` to *robot_node/* and change the code:

     ```python
     self.cap = cv2.VideoCapture(0)
     if not self.cap.isOpened():
         print("No webcam found — falling back to sample.mp4")
         self.cap = cv2.VideoCapture("sample.mp4")
     ```

   * Now `docker compose up` will stream the sample video instead of a real camera.

3. **Create a virtual webcam device** (Linux)
   * Install v4l2loopback: `sudo apt install v4l2loopback-utils`.
   * `sudo modprobe v4l2loopback devices=1 video_nr=10` — creates */dev/video10*.
   * Push any video into it using FFmpeg:

     ```bash
     ffmpeg -re -stream_loop -1 -i sample.mp4 -vf format=yuv420p -f v4l2 /dev/video10
     ```

   * Change the device mapping in *compose.yml* to `/dev/video10:/dev/video10`.

Pick whichever option suits your setup – the rest of the stack (Operator + Recorder) stays unchanged.

---

## License

MIT © Wilddolphin2022
