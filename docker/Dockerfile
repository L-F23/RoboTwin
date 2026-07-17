# syntax=docker/dockerfile:1

ARG CUDA_IMAGE=nvidia/cuda:12.1.0-devel-ubuntu22.04
FROM ${CUDA_IMAGE}

ARG ROBOTWIN_UID=1000
ARG ROBOTWIN_GID=1000
ARG TORCH_CUDA_ARCH_LIST=8.9

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST}

RUN HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= apt-get update \
    && HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        ffmpeg \
        git \
        libegl1 \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libvulkan1 \
        libx11-6 \
        libxext6 \
        libxkbcommon0 \
        libxrender1 \
        mesa-vulkan-drivers \
        ninja-build \
        python3.10 \
        python3.10-dev \
        python3-pip \
        python3-venv \
        vulkan-tools \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/python3.10 /usr/local/bin/python \
    && ln -s /usr/bin/pip3 /usr/local/bin/pip

COPY docker/requirements.txt /tmp/tablesim-requirements.txt

RUN python -m pip install --upgrade pip "setuptools<81" wheel \
    && python -m pip install \
        torch==2.4.1 \
        torchvision==0.19.1 \
    && python -m pip install -r /tmp/tablesim-requirements.txt \
    && python -m pip install \
        "git+https://github.com/facebookresearch/pytorch3d.git@stable" \
        --no-build-isolation

# RoboTwin 2.0 currently requires these two upstream compatibility patches.
RUN SAPIEN_DIR="$(python -m pip show sapien | awk '/^Location:/{print $2}')/sapien" \
    && sed -i -E 's/open\(urdf_file, "r"\)/open(urdf_file, "r", encoding="utf-8")/' \
        "${SAPIEN_DIR}/wrapper/urdf_loader.py" \
    && sed -i -E 's/open\(srdf_file, "r"\)/open(srdf_file, "r", encoding="utf-8")/' \
        "${SAPIEN_DIR}/wrapper/urdf_loader.py" \
    && sed -i 's/urdf_file\[:-4\] + "srdf"/urdf_file[:-4] + ".srdf"/' \
        "${SAPIEN_DIR}/wrapper/urdf_loader.py" \
    && MPLIB_DIR="$(python -m pip show mplib | awk '/^Location:/{print $2}')/mplib" \
    && sed -i -E \
        's/(if np\.linalg\.norm\(delta_twist\) < 1e-4 )or collide (or not within_joint_limit:)/\1\2/' \
        "${MPLIB_DIR}/planner.py"

RUN git clone --branch v0.7.8 --depth 1 \
        https://github.com/NVlabs/curobo.git /opt/curobo \
    && python -m pip install -e /opt/curobo --no-build-isolation \
    && rm -rf /opt/curobo/.git

RUN groupadd --gid "${ROBOTWIN_GID}" robotwin \
    && useradd --uid "${ROBOTWIN_UID}" --gid "${ROBOTWIN_GID}" \
        --create-home --shell /bin/bash robotwin \
    && mkdir -p /workspace/RoboTwin /home/robotwin/.cache \
    && chown -R robotwin:robotwin /workspace/RoboTwin /home/robotwin

USER robotwin
WORKDIR /workspace/RoboTwin

CMD ["bash"]
