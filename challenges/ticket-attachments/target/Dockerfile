FROM awdp/python-base:0.1
RUN mkdir -p /submission
COPY src /opt/challenge/src
COPY entrypoint.py /opt/challenge/entrypoint.py
USER 65534:65534
ENTRYPOINT ["python3", "/opt/challenge/entrypoint.py"]
