import asyncio
import json
import time
import sys

import cv2
import av
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.mediastreams import MediaStreamError

ROBOT_WS_URI = "ws://robot:8765"

class VideoDisplay:
    """Show frames in an OpenCV window and overlay latency."""

    def __init__(self):
        self.window_name = "Robot Video"
        # Determine whether OpenCV HighGUI is available (inside container often not)
        try:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            self.headless = False
        except cv2.error:
            print("[Operator] OpenCV GUI not available – running headless (no video window)")
            self.headless = True

    async def show(self, frame: av.VideoFrame):
        img = frame.to_ndarray(format="bgr24")
        if frame.pts is not None and frame.time_base:
            if not hasattr(self, "_pts_base"):
                # On first frame establish reference mapping between PTS and wall-clock time
                self._pts_base = frame.pts
                self._time_base_wall = time.time()
            elapsed_pts = (frame.pts - self._pts_base) * frame.time_base  # seconds since first frame
            capture_ts = self._time_base_wall + elapsed_pts
            latency_ms = max(0, (time.time() - capture_ts) * 1000)
        else:
            latency_ms = 0
        if latency_ms > 0:
            cv2.putText(img, f"Latency: {latency_ms:.1f}ms", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
        if not self.headless:
            cv2.imshow(self.window_name, img)
            cv2.waitKey(1)
        else:
            # Print latency every second in headless mode
            print(f"Latency: {latency_ms:.1f} ms")

async def operator():
    """Persistent loop: connect to the Robot WebSocket, then start signaling/UI."""

    async def run_once(ws):
        """Handle one successful WebSocket session."""
        pc = RTCPeerConnection()

        # We will only receive video
        pc.addTransceiver("video", direction="recvonly")

        # Signal local ICE to robot
        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                await ws.send(json.dumps({
                    "type": "candidate",
                    "candidate": {
                        "candidate": candidate.candidate,
                        "sdpMid": candidate.sdpMid,
                        "sdpMLineIndex": candidate.sdpMLineIndex,
                    },
                }))

        display = VideoDisplay()

        # Render incoming frames
        @pc.on("track")
        async def on_track(track):
            while True:
                try:
                    frame = await track.recv()
                except MediaStreamError:
                    # Stream ended gracefully
                    break
                await display.show(frame)

        # Create & send SDP offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await ws.send(json.dumps({"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}))

        async def signaling_loop():
            async for message in ws:
                data = json.loads(message)
                if data.get("type") == "answer":
                    await pc.setRemoteDescription(
                        RTCSessionDescription(sdp=data["sdp"], type=data["type"])
                    )
                elif data.get("type") == "candidate":
                    cand = data["candidate"]
                    await pc.addIceCandidate(
                        RTCIceCandidate(
                            sdpMid=cand["sdpMid"],
                            sdpMLineIndex=cand["sdpMLineIndex"],
                            candidate=cand["candidate"],
                        )
                    )

        async def command_input():
            # Skip interactive CLI if no terminal is attached (e.g., running in detached mode)
            if not sys.stdin or not sys.stdin.isatty():
                print("[Operator] No TTY detected – skipping command input loop")
                await asyncio.Event().wait()  # sleep forever
                return

            loop = asyncio.get_event_loop()
            while True:
                cmd = await loop.run_in_executor(None, input, "Command (p=pause, r=resume, t=text, x=exit): ")
                if cmd == "p":
                    await ws.send(json.dumps({"command": "pause"}))
                elif cmd == "r":
                    await ws.send(json.dumps({"command": "play"}))
                elif cmd == "t":
                    text = await loop.run_in_executor(None, input, "Enter text (empty to cancel): ")
                    if text:
                        await ws.send(json.dumps({"command": "text", "message": text}))
                elif cmd == "x":
                    print("[Operator] Exit requested. Closing connection…")
                    await ws.close()
                    await pc.close()
                    # Cancel signaling loop task and exit
                    for task in asyncio.all_tasks():
                        if task is not asyncio.current_task():
                            task.cancel()
                    return

        try:
            await asyncio.gather(signaling_loop(), command_input())
        except asyncio.CancelledError:
            pass  # graceful shutdown

    # Persistent retry loop
    while True:
        try:
            async with websockets.connect(ROBOT_WS_URI) as ws:
                await run_once(ws)
            # normal exit if run_once returns
            break
        except (OSError, websockets.exceptions.InvalidHandshake) as e:
            print(f"[Operator] WebSocket error: {e}. Retrying in 1 s…")
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(operator())
    except KeyboardInterrupt:
        pass

