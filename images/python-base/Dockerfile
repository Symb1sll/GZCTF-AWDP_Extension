FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN sed -i 's#http://archive.ubuntu.com/ubuntu/#http://mirrors.aliyun.com/ubuntu/#g; s#http://security.ubuntu.com/ubuntu/#http://mirrors.aliyun.com/ubuntu/#g' /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && sed -i 's#http://mirrors.aliyun.com/ubuntu/#https://mirrors.aliyun.com/ubuntu/#g' /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends patch python3 \
    && rm -rf /var/lib/apt/lists/*
