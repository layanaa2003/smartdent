"""
Download the trained model when SmartDent runs on Hugging Face.

The public Space does not contain models/best.pt, so nobody can download it from the Space.
Instead the model lives in a private Hugging Face model repository (MODEL_REPO, a Space variable)
and is fetched here at start-up with the Space secret HF_TOKEN. On a normal computer MODEL_REPO
is not set and models/best.pt is already there, so this does nothing.
"""
import os
import shutil
import sys
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "best.pt"


def main():
    repo = os.environ.get("MODEL_REPO")
    if not repo or MODEL_PATH.exists():
        return
    from huggingface_hub import hf_hub_download
    try:
        # strip(): a token pasted into the Space settings often carries a space or line break
        cached = hf_hub_download(repo, "best.pt", token=(os.environ.get("HF_TOKEN") or "").strip() or None)
    except Exception as error:                    # the app still starts; uploads say the model is missing
        print(f"Could not download the model from {repo}: {error.__class__.__name__}", file=sys.stderr)
        return
    MODEL_PATH.parent.mkdir(exist_ok=True)
    shutil.copyfile(cached, MODEL_PATH)
    print(f"Model downloaded from {repo}")


if __name__ == "__main__":
    main()
