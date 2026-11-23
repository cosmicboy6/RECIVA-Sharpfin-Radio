FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgtk2.0-0 \
      fonts-dejavu-core \
      xvfb \
      x11-utils \
      xdotool \
      scrot \
      fluxbox \
      python3-minimal \
      ca-certificates \
      libssl3 \
      python3-pil \
      tesseract-ocr \
      at-spi2-core \
      libgail-common \
      python3-pyatspi \
      python3-gi \
      dbus-x11 \
    && ln -sf /usr/lib/x86_64-linux-gnu/libssl.so.3 /usr/lib/x86_64-linux-gnu/libssl.so \
    && ln -sf /usr/lib/x86_64-linux-gnu/libcrypto.so.3 /usr/lib/x86_64-linux-gnu/libcrypto.so \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/RecivaServer

COPY RecivaServer/ /opt/RecivaServer/
COPY files/sharpfin-base_0.3_IPdio.patch /opt/RecivaServer/patches/base_0.3.patch

COPY entrypoint.sh /entrypoint.sh
COPY configure_gui.sh /opt/configure_gui.sh
COPY dnsproxy.py /opt/dnsproxy.py
COPY ntp_server.py /opt/ntp_server.py
COPY sync_sharpfin_menu.py /opt/sync_sharpfin_menu.py
COPY patch_server.py /opt/patch_server.py

RUN chmod +x \
      /entrypoint.sh \
      /opt/configure_gui.sh \
      /opt/dnsproxy.py \
      /opt/patch_server.py \
      /opt/RecivaServer/server

EXPOSE 80/tcp 443/tcp 8080/tcp 53/udp 123/udp

ENTRYPOINT ["/entrypoint.sh"]
