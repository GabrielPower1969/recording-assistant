FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV RA_CONTAINER=1
COPY scripts ./scripts
COPY assets ./assets
COPY examples ./examples
EXPOSE 8765
# Published to localhost by compose: browsers allow the camera and microphone only on localhost or HTTPS.
CMD ["python", "scripts/serve.py", "examples/demo", "--host", "0.0.0.0", "--no-whisper"]
