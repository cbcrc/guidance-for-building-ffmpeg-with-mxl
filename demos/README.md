# Demos

```mermaid
graph LR
    subgraph "FFmpeg-MXL pipeline"
    A0((fa:fa-file-video)) --> A[FFmpeg Source] -- "Uncompressed (v210)<br/> MXL" --> B[FFmpeg Destination]
    end

    subgraph "Distribution"
    B -- "H.264<br/> RTSP" --> C[MediaMTX]
    C -- "H.264<br/> WebRTC" --> D[Client A]
    C -- "H.264<br/> WebRTC" --> E[Client B]
    end
```

Video only.

## Startup the services

```bash
docker compose up -d 
```

Open browser @ `http://<servirIP>:8889/mxlstream`

## Inspect the domain

```bash
docker volume inspect demos_mxl-domain | grep Mountpoint                                                              ✔  17:06:54 
        "Mountpoint": "/var/lib/docker/volumes/demos_mxl-domain/_data",
sudo find /var/lib/docker/volumes/demos_mxl-domain/_data
...
```

## Close

```bash
docker compose down
```
