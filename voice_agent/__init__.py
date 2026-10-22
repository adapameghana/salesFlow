"""Open-source AI voice agent that phones customers about unpaid orders.

Heavy dependencies (torch, faster-whisper, parler-tts, silero-vad) are imported
lazily inside the modules that need them, so the conversation logic, phrases,
number words and protocol code can be imported and tested without them.
"""
