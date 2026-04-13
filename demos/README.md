# Demos

```mermaid
graph LR
    subgraph "FFmpeg-MXL pipeline"
    A0((fa:fa-film demo_reel.ts)) --> A[FFmpeg Source] -- "Uncompressed (v210)<br/> MXL" --> B[FFmpeg Destination]
    A1((Branding message)) --> A
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

## Monitor

Open browser @ `http://<serverIP>:8889/mxlstream`

## Troubleshoot

```bash
docker compose logs -f # watch for retstarting services

sudo netstat -laputen | grep -E "8889|8554" # show socket status

find /dev/shm/ffmpeg # ls flow content
```

## Close

```bash
docker compose down
```
