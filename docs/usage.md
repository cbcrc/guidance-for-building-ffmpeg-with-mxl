# Usage Examples

The following examples assume that MXL and FFmpeg were built using
`host-setup-and-build.sh ~/src ~/build --dev` or
`docker-setup-and-build.sh ~/src ~/build --dev`.

MXL uses `tmpfs` to host the MXL domain. First, prepare the mount folder:

```bash
$ mkdir -p /dev/shm/mxl
```

## Read a test source with FFmpeg

MXL SDK comes with Gstreamer-based writer as a test source. Let's playback MXL content with `ffplay` and
show flow description with `ffprobe`.

Video:
```bash
$ (cd ~/build/mxl/build/Linux-GCC-Debug/static && \
   ./tools/mxl-gst/mxl-gst-testsrc --video-config-file ./lib/tests/data/v210_flow.json --domain /dev/shm/mxl)&
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffplay /dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ed.mxl-flow
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffprobe /dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ed.mxl-flow
Input #0, mxl, from '/dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ed.mxl-flow':
  Duration: N/A, start: 0.000000, bitrate: N/A
  Stream #0:0: Video: v210 (v210 / 0x30313276), yuv422p10le(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 29.97 fps, 29.97 tbr, 29.97 tbn
    Metadata:
      mxl_id          : 5fbec3b1-1b0f-417d-9059-8b94a47197ed
      mxl_description : MXL Test Flow, 1080p29
      mxl_label       : MXL Test Flow, 1080p29
      mxl_format      : urn:x-nmos:format:video
      mxl_media_type  : video/v210
      mxl_colorspace  : BT709
```

Audio:
```bash
$ mkdir -p /dev/shm/mxl
$ (cd ~/build/mxl/build/Linux-GCC-Debug/static && ./tools/mxl-gst/mxl-gst-testsrc --audio-config-file ./lib/tests/data/audio_flow.json --domain /dev/shm/mxl )&
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffplay /dev/shm/mxl/b3bb5be7-9fe9-4324-a5bb-4c70e1084449.mxl-flow
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffprobe /dev/shm/mxl/b3bb5be7-9fe9-4324-a5bb-4c70e1084449.mxl-flow
Input #0, mxl, from '/dev/shm/mxl/b3bb5be7-9fe9-4324-a5bb-4c70e1084449.mxl-flow':
  Duration: N/A, start: 0.000000, bitrate: 3072 kb/s
  Stream #0:0: Audio: pcm_f32le, 48000 Hz, 2 channels, flt, 3072 kb/s
    Metadata:
      mxl_id          : b3bb5be7-9fe9-4324-a5bb-4c70e1084449
      mxl_description : MXL Audio Flow
      mxl_label       : MXL Audio Flow
      mxl_format      : urn:x-nmos:format:audio
      mxl_media_type  : audio/float32
```

## FFmpeg mxl write → ffplay mxl read

Let's replace the test source with FFmpeg.
MXL SDK also comes with `mxl-info` utility which shows flow metrics:

Video:
```bash
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffmpeg  -re -f lavfi -i testsrc2=size=1920x1080:rate=50 -c:v v210 -f mxl -video_flow_id fe781cad-8a82-4b8e-a3c2-f833c70ac73e /dev/shm/mxl &
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffplay /dev/shm/mxl/fe781cad-8a82-4b8e-a3c2-f833c70ac73e.mxl-flow
$ ~/build/mxl/install/Linux-GCC-Debug/static/bin/mxl-info --domain /dev/shm/mxl --flow fe781cad-8a82-4b8e-a3c2-f833c70ac73e
- Flow [fe781cad-8a82-4b8e-a3c2-f833c70ac73e]
	           Version: 1
	       Struct size: 2048
	            Format: Video
	 Grain/sample rate: 50/1
	 Commit batch size: 1080
	   Sync batch size: 1080
	  Payload Location: Host
	      Device Index: -1
	             Flags: 00000000
	       Grain count: 10

	        Head index: 88411783498
	   Last write time: 1768235669455895609
	    Last read time: 1768235648241778461
	  Latency (grains): 18446744073709551591
	            Active: true
```

Audio:
```bash
$ ~/build/ffmpeg/install/Linux-GCC-Debug/static/bin/ffmpeg -re -f lavfi -i "sine=frequency=200:sample_rate=48000,aformat=sample_fmts=flt:channel_layouts=stereo" -map 0:a:0 -c:a pcm_f32le -f mxl -audio_flow_id ca28b9ff-9d44-41ba-9c88-99329e7995a6 /dev/shm/mxl &
$ ~/build/mxl/install/Linux-GCC-Debug/static/bin/mxl-info --domain /dev/shm/mxl --flow ca28b9ff-9d44-41ba-9c88-99329e7995a6
- Flow [ca28b9ff-9d44-41ba-9c88-99329e7995a6]
	           Version: 1
	       Struct size: 2048
	            Format: Audio
	 Grain/sample rate: 48000/1
	 Commit batch size: 480
	   Sync batch size: 480
	  Payload Location: Host
	      Device Index: -1
	             Flags: 00000000
	     Channel count: 2
	     Buffer length: 10240

	        Head index: 84875304606224
	   Last write time: 1768235403360202151
	    Last read time: 1768235403360202151
	  Latency (grains): 18446744073709528025
	            Active: true
```

## MXL URI Support

[URI addressability](https://github.com/dmf-mxl/mxl/blob/main/docs/Addressability.md).

Examples:

```bash
$ ./ffprobe "mxl:///dev/shm/mxl?id=5fbec3b1-1b0f-417d-9059-8b94a47197ed"
$ ./ffprobe "mxl:///dev/shm/mxl?id=5fbec3b1-1b0f-417d-9059-8b94a47197ed&id=c0685cd6-0b52-4508-9f99-4eedaf874540"
```

The MXL demuxer supports local filesystem paths only. URIs with an
authority (host) are rejected. For example:

```bash
$ ./ffprobe -hide_banner -v verbose "mxl://rdma.host/dev/shm/mxl?id=5fbec3b1-1b0f-417d-9059-8b94a47197ed"
mxl AVProbeData:
  filename: mxl://rdma.host/dev/shm/mxl?id=5fbec3b1-1b0f-417d-9059-8b94a47197ed
  buf_size: 0
  mime_type: (null)
MXL URI host not supported: "mxl://rdma.host/dev/shm/mxl?id=5fbec3b1-1b0f-417d-9059-8b94a47197ed"
MXL failed to parse locator: "mxl://rdma.host/dev/shm/mxl?id=5fbec3b1-1b0f-417d-9059-8b94a47197ed"
MXL probe score = 0
mxl://rdma.host/dev/shm/mxl?id=5fbec3b1-1b0f-417d-9059-8b94a47197ed: Protocol not found
```

Direct file paths are also supported for single flows:

```bash
$ ./ffprobe /dev/shm/mxl/5fbec3b1-1b0f-417d-9059-8b94a47197ed.mxl-flow
```
