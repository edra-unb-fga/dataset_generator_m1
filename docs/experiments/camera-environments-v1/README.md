# Camera and environments evidence

Open [the standalone report](index.html) locally. It embeds the available reviewed sheets and needs no network. `compact.json` contains selected measurements and statuses without local absolute paths.

Reproduce from the repository root when the ignored raw experiment bundle is available:

```sh
python3 scripts/report_camera_environments.py --input outputs/experiments/realism-camera-round --output docs/experiments/camera-environments-v1
```

Missing reduced cases are marked missing. Old smoke imagery is an earlier prototype; the current 3D work is unqualified. The small 2D screen and partial 3D runs do not support real-reference, model-performance, benchmark or promotion claims. Raw experiment outputs remain ignored.
