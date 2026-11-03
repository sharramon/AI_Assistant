"""The shared voice service: speech to text over a WebSocket. Never imports `assistant`.

Kept empty so clients can import `voice_service.protocol` without the server's
dependencies (FastAPI, sherpa-onnx, sounddevice).
"""
