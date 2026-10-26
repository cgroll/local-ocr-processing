# Sandbox image for the agentic retrieval eval (task 2.1). CPU-only, no PaddlePaddle, no CUDA --
# see design.md Decision 2: EmbeddingGemma 2 loads via sentence-transformers independently of the
# project's GPU-bound Paddle stack, so `device="cpu"` is enough here.
#
# Build:  docker build -t agentic-retrieval-eval-sandbox .
# Run:    see sandbox_tools/README or run.sh -- mounts the HF cache (read-only), a redacted
#         CLAUDE_CONFIG_DIR, and exactly one sandbox_local/ or sandbox_cloud/ folder.
FROM python:3.12-slim

# --extra-index-url (not --index-url): lets pip resolve torch/torchvision/torchaudio from the
# CPU-only wheel index *and* everything else from PyPI in one pass, so it picks a mutually
# compatible torch+torchvision pair instead of installing them in two separate pip calls (which
# produced a torch/torchvision ABI mismatch: "RuntimeError: operator torchvision::nms does not
# exist" -- found while verifying task 2.2).
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        "sentence-transformers[image]" \
        numpy \
        claude-agent-sdk

WORKDIR /app
COPY sandbox_tools/ ./sandbox_tools/

ENV HF_HOME=/hf-cache
ENV HF_HUB_OFFLINE=1
