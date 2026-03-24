# Demos

FFmpeg_Src --MXL/v210--> FFmpeg_Dest --rtsp/h264--> MediaMTX

Video only.

## Startup

Assuming the `prod` image is [already built locally](../docs/build.md#docker-production-image).

```bash
docker compose up -d
```

Open browser @ `http://<servirIP>:8889/mxlstream`

## Close

```bash
docker compose down
```
