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

COPY . /operator_node/

WORKDIR /operator_node

#RUN pip freeze > requirements.txt
#RUN pip3 install -r requirements.txt
RUN pip3 install meson

CMD ["python3", "operator_node.py"]
