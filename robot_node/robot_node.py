import asyncio
import json
import time
import fractions
import cv2
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
import numpy as np
import av

pcs = set()
websockets_set = set()

class VideoStream(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.synthetic = False
        self.cap = cv2.VideoCapture(0, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            print("[Robot] /dev/video0 not available – falling back to sample.mp4")
            self.cap = cv2.VideoCapture("sample.mp4", cv2.CAP_FFMPEG)
            if not self.cap.isOpened():
                print("[Robot] sample.mp4 not found – switching to synthetic video feed")
                self.synthetic = True
                self.cap.release()
            else:
                print("[Robot] Successfully opened sample.mp4")
        else:
            print("[Robot] Successfully opened /dev/video0")
        self.text = ""
        self.playing = True
        self.np = np
        self.last_frame_time = 0

    async def recv(self):
        # Limit frame rate to ~30fps
        current_time = time.time()
        if current_time - self.last_frame_time < 0.033:
            await asyncio.sleep(0.033 - (current_time - self.last_frame_time))
        self.last_frame_time = time.time()

        while not self.playing:
            await asyncio.sleep(0.05)
        try:
            if self.synthetic:
                frame = self.np.zeros((480, 640, 3), dtype=self.np.uint8)
                cv2.putText(frame, time.strftime("%H:%M:%S"), (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)
            else:
                ret, frame = self.cap.read()
                if not ret:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                    if not ret:
                        print("[Robot] Failed to read frame")
                        await asyncio.sleep(0.01)
                        return await self.recv()
                if self.text:
                    cv2.putText(frame, self.text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                video_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
                capture_ts = int(time.time() * 90_000)
                video_frame.pts = capture_ts
                video_frame.time_base = fractions.Fraction(1, 90_000)
                return video_frame
        except Exception as e:
            print(f"[Robot] Error in video frame processing: {e}")
            await asyncio.sleep(0.01)
            return await self.recv()

stream = VideoStream()
relay = MediaRelay()

async def handle_client(ws, _):
    websockets_set.add(ws)
    pc = RTCPeerConnection()
    pcs.add(pc)
    try:
        pc.addTrack(relay.subscribe(stream))
    except Exception as e:
        print(f"[Robot] Failed to add track to peer connection: {e}")
        await pc.close()
        websockets_set.discard(ws)
        pcs.discard(pc)
        return

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            try:
                await ws.send(json.dumps({
                    "type": "candidate",
                    "candidate": {
                        "candidate": candidate.candidate,
                        "sdpMid": candidate.sdpMid,
                        "sdpMLineIndex": candidate.sdpMLineIndex,
                    }
                }))
                print(f"[Robot] Sent ICE candidate to {ws.remote_address}")
            except Exception as e:
                print(f"[Robot] Failed to send ICE candidate: {e}")

    try:
        async for message in ws:
            try:
                data = json.loads(message)
                print(f"[Robot] Received message: {data}")
                if data.get("type") == "offer":
                    try:
                        offer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
                        await pc.setRemoteDescription(offer)
                        answer = await pc.createAnswer()
                        await pc.setLocalDescription(answer)
                        await ws.send(json.dumps({
                            "type": pc.localDescription.type,
                            "sdp": pc.localDescription.sdp,
                        }))
                        print(f"[Robot] Sent WebRTC answer to {ws.remote_address}")
                    except Exception as e:
                        print(f"[Robot] WebRTC signaling error: {e}")
                elif data.get("type") == "candidate":
                    try:
                        cand = data["candidate"]
                        candidate = RTCIceCandidate(
                            sdpMid=cand["sdpMid"],
                            sdpMLineIndex=cand["sdpMLineIndex"],
                            candidate=cand["candidate"],
                        )
                        await pc.addIceCandidate(candidate)
                        print(f"[Robot] Added ICE candidate from {ws.remote_address}")
                    except Exception as e:
                        print(f"[Robot] Failed to add ICE candidate: {e}")
                elif data.get("command"):
                    cmd = data["command"]
                    if cmd == "pause":
                        stream.playing = False
                    elif cmd == "play":
                        stream.playing = True
                    elif cmd == "text":
                        stream.text = data.get("message", "")
                    for other_ws in list(websockets_set):
                        if other_ws is not ws:
                            try:
                                await other_ws.send(message)
                                print(f"[Robot] Broadcast command to {other_ws.remote_address}")
                            except Exception as e:
                                print(f"[Robot] Failed to broadcast to {other_ws.remote_address}: {e}")
            except json.JSONDecodeError as e:
                print(f"[Robot] Invalid JSON message: {e}")
            except Exception as e:
                print(f"[Robot] Error processing message: {e}")
    except (websockets.exceptions.ConnectionClosedError, asyncio.exceptions.IncompleteReadError) as e:
        print(f"[Robot] WebSocket closed for {ws.remote_address}: {e}")
    except Exception as e:
        print(f"[Robot] Unexpected error in handle_client: {e}")
    finally:
        websockets_set.discard(ws)
        await pc.close()
        pcs.discard(pc)
        print(f"[Robot] Cleaned up connection for {ws.remote_address}")

async def run_robot():
    server = await websockets.serve(
        handle_client,
        "0.0.0.0",
        8765,
        ping_interval=10,
        ping_timeout=5,
        close_timeout=5
    )
    print("Robot Node running. Awaiting connections on ws://0.0.0.0:8765 ...")
    try:
        await server.wait_closed()
    except Exception as e:
        print(f"[Robot] Server error: {e}")
    finally:
        coros = [pc.close() for pc in pcs]
        if coros:
            await asyncio.gather(*coros)
        if stream.cap.isOpened():
            stream.cap.release()
        print("[Robot] Server shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(run_robot())
    except Exception as e:
        print(f"[Robot] Fatal error: {e}")
        exit(1)