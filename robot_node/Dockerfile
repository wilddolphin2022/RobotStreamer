FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-opencv \
    python3-aiortc \
    ffmpeg \
    python3-av \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir websockets==11.0

COPY . /robot_node/

WORKDIR /robot_node

#RUN pip freeze > requirements.txt
#RUN pip3 install -r requirements.txt

CMD ["python3", "robot_node.py"]
