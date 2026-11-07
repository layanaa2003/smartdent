# SmartDent as a Hugging Face Docker Space (also runs with plain Docker).
#   docker build -t smartdent .  &&  docker run -p 7860:7860 smartdent   ->  http://localhost:7860
# The database lives inside the container, so it starts fresh (with the demo accounts) on every restart.
FROM python:3.13-slim

# OpenCV needs these system libraries.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face runs the container as user 1000, who must be able to write the database and uploads.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/home/user/.config/Ultralytics
WORKDIR /home/user/app

# Packages first, so they are cached between builds. The CPU build of PyTorch keeps the image small.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt gunicorn==23.0.0 \
        --extra-index-url https://download.pytorch.org/whl/cpu

COPY --chown=user . .

EXPOSE 7860
# Create the database (demo accounts if empty), then serve. One worker keeps one copy of the AI model in memory.
CMD python scripts/seed.py --demo && \
    exec gunicorn --bind 0.0.0.0:7860 --workers 1 --threads 4 --timeout 180 run:app
