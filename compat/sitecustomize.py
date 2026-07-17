"""Runtime compatibility hooks loaded automatically through PYTHONPATH."""

from types import SimpleNamespace

import warp


# cuRobo versions bundled with the RoboTwin image still access
# ``warp.torch.device_from_torch``.  Warp 1.15 exposes the function at the
# package root, so preserve the old namespace expected by cuRobo.
if not hasattr(warp, "torch"):
    warp.torch = SimpleNamespace(device_from_torch=warp.device_from_torch)
