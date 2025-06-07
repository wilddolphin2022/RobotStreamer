import asyncio
import json
from pathlib import Path
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaRecorder

ROBOT_WS_URI = "ws://robot:8765"
OUTPUT_DIR = "output"
VIDEO_OUTPUT = f"{OUTPUT_DIR}/recording.mkv"
COMMAND_LOG = f"{OUTPUT_DIR}/commands.jsonl"

async def recorder_node():
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    async def run_once(ws):
        pc = RTCPeerConnection()
        media_recorder = MediaRecorder(
            VIDEO_OUTPUT,
            format="matroska",
            options={"video_codec": "libx264", "preset": "ultrafast", "b:v": "1024k"},
        )
        recorder_started = False

        # Add video transceiver for receiving video
        pc.addTransceiver("video", direction="recvonly")

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
                    print(f"[Recorder] Sent ICE candidate: {candidate.sdpMid}")
                except Exception as e:
                    print(f"[Recorder] Failed to send ICE candidate: {e}")

        @pc.on("track")
        async def on_track(track):
            nonlocal recorder_started
            if track.kind == "video":
                try:
                    media_recorder.addTrack(track)
                    if not recorder_started:
                        print(f"[Recorder] Video track received – starting recorder -> {VIDEO_OUTPUT}")
                        await media_recorder.start()
                        recorder_started = True
                except ValueError as e:
                    print(f"[Recorder] Failed to add track: {e}")

            @track.on("ended")
            async def _():
                if recorder_started:
                    print("[Recorder] Track ended, stopping recorder")
                    try:
                        await media_recorder.stop()
                    except Exception as e:
                        print(f"[Recorder] Failed to stop MediaRecorder: {e}")

        try:
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            await ws.send(json.dumps({
                "type": pc.localDescription.type,
                "sdp": pc.localDescription.sdp,
            }))
            print("[Recorder] Sent WebRTC offer")
        except Exception as e:
            print(f"[Recorder] Failed to send offer: {e}")
            return

        async def signaling_and_logging():
            try:
                async for message in ws:
                    data = json.loads(message)
                    print(f"[Recorder] Received message: {data}")
                    if data.get("type") == "answer":
                        try:
                            answer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
                            await pc.setRemoteDescription(answer)
                            print("[Recorder] Set remote answer")
                        except Exception as e:
                            print(f"[Recorder] Failed to set remote answer: {e}")
                    elif data.get("type") == "candidate":
                        try:
                            cand = data["candidate"]
                            candidate = RTCIceCandidate(
                                sdpMid=cand["sdpMid"],
                                sdpMLineIndex=cand["sdpMLineIndex"],
                                candidate=cand["candidate"],
                            )
                            await pc.addIceCandidate(candidate)
                            print("[Recorder] Added ICE candidate")
                        except Exception as e:
                            print(f"[Recorder] Failed to add ICE candidate: {e}")
                    elif data.get("command"):
                        try:
                            with open(COMMAND_LOG, "a", encoding="utf-8") as f:
                                json.dump({
                                    "timestamp": asyncio.get_event_loop().time(),
                                    "command": data,
                                }, f)
                                f.write("\n")
                            print(f"[Recorder] Logged command: {data}")
                        except Exception as e:
                            print(f"[Recorder] Failed to log command: {e}")
            except (websockets.exceptions.ConnectionClosedError, asyncio.exceptions.IncompleteReadError) as e:
                print(f"[Recorder] WebSocket closed unexpectedly: {e}")
                return
            except Exception as e:
                print(f"[Recorder] Unexpected error in signaling/logging: {e}")
                return

        try:
            await signaling_and_logging()
        finally:
            if recorder_started:
                print("[Recorder] Stopping MediaRecorder")
                try:
                    await media_recorder.stop()
                except Exception as e:
                    print(f"[Recorder] Failed to stop MediaRecorder: {e}")
            try:
                await pc.close()
            except Exception as e:
                print(f"[Recorder] Failed to close RTCPeerConnection: {e}")
            print("[Recorder] Run_once finished")

    retry_delay = 2  # Increased initial delay for Robot Node startup
    max_retries = 10
    for attempt in range(max_retries):
        try:
            async with websockets.connect(
                ROBOT_WS_URI,
                ping_interval=10,
                ping_timeout=5,
                close_timeout=5
            ) as ws:
                print(f"[Recorder] Connected to WebSocket at {ROBOT_WS_URI}")
                await run_once(ws)
                break
        except (OSError, websockets.exceptions.InvalidHandshake, websockets.exceptions.ConnectionClosedError) as e:
            print(f"[Recorder] WebSocket error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 10)
        except Exception as e:
            print(f"[Recorder] Unexpected error: {e}")
            break
    else:
        print(f"[Recorder] Failed to connect after {max_retries} attempts.")

if __name__ == "__main__":
    try:
        asyncio.run(recorder_node())
    except Exception as e:
        print(f"[Recorder] Fatal error: {e}")
        exit(1)