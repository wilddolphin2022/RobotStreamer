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

`recorder` writes files **inside** its container. To store them on the host simply add a volume in `RobotStreamer.yml`, e.g.

```yaml
recorder:
  build: ./recorder_node
  volumes:
    - ./output:/recorder_node   # host ./output ➔ container /recorder_node
  depends_on:
    - robot
```

With that tweak the recorded *recording.mp4* and *commands.jsonl* will appear in `./output` on your host.

---

## Troubleshooting

* Ensure no other process is using the webcam.
* On macOS/Windows you may need to run the robot node natively or grant camera access to Docker.
* If ICE negotiation fails, verify that containers can reach each other via the default Docker network (they should with Compose).

---

## License

MIT © Wilddolphin2022 
