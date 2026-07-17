# RoboTwin Docker environment

This image targets RoboTwin 2.0 on the local RTX 4090. It uses Python 3.10,
CUDA 12.1, PyTorch 2.4.1, SAPIEN 3.0.0b1, MPLib 0.2.1, and CuRobo 0.7.8.

RoboTwin's `main` branch uses SAPIEN. Isaac Sim and MuJoCo are separate local
simulators and are intentionally not installed again in this image.

## Build

From the RoboTwin repository root:

```bash
docker compose build robotwin
```

The build uses host networking because this machine's Docker proxy listens on
the host loopback interface (`127.0.0.1:7890`). This setting only affects the
image build; the running service still uses Compose's isolated network.

The default CuRobo/PyTorch3D CUDA build target is compute capability 8.9 for
the RTX 4090. To build for another GPU, override `TORCH_CUDA_ARCH_LIST`:

```bash
TORCH_CUDA_ARCH_LIST='8.6' docker compose build robotwin
```

## Verify

```bash
docker compose run --rm robotwin python -c \
  "import torch,sapien,mplib,curobo; print(torch.__version__, torch.cuda.is_available(), sapien.__version__, mplib.__version__)"

docker compose run --rm robotwin python script/test_render.py
```

The second command should print `Render Well`. The Compose service passes the
NVIDIA `graphics` capability required by SAPIEN's Vulkan renderer.

## Use

Open an interactive shell:

```bash
docker compose run --rm robotwin
```

Collect a small task dataset with the existing assets mounted from the host:

```bash
docker compose run --rm robotwin \
  bash collect_data.sh beat_block_hammer demo_clean 0
```

Generated files remain in the host checkout. The container runs as UID/GID
1000 by default so those files are not owned by root. Override
`ROBOTWIN_UID`/`ROBOTWIN_GID` during the build if the host account differs.

For a visible viewer, allow the local X server connection before starting the
container if required by the desktop session:

```bash
xhost +si:localuser:$(id -un)
```
