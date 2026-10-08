FROM awdp/ticket-target:1.0
USER root
RUN mkdir -p /work && chown 65534:65534 /work
COPY attack_entrypoint.py /opt/challenge/gzctf_entrypoint.py
USER 65534:65534
ENV TICKET_MODE=attack TICKET_BIND=0.0.0.0
ENTRYPOINT ["python3", "/opt/challenge/gzctf_entrypoint.py"]
