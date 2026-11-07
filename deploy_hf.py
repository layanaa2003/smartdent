"""
Put SmartDent online as a Hugging Face Docker Space (needs a Hugging Face PRO account).

Usually GitHub does this for you: every push to main runs .github/workflows/deploy-hf.yml with the
repository secret HF_TOKEN. Optional repository secrets DEMO_ADMIN_PASSWORD, DEMO_DOCTOR_PASSWORD and
HF_SECRET_KEY are copied to the Space; without them the Space uses the demo passwords from README.md
(or whatever you set by hand under the Space's Settings > Variables and secrets).
You can also start it by hand on GitHub: Actions > "Deploy to Hugging Face" > Run workflow.

To run it from this computer instead:
    .venv\\Scripts\\pip install huggingface_hub
    .venv\\Scripts\\hf auth login          (a token with "write" access from huggingface.co/settings/tokens)
    .venv\\Scripts\\python deploy_hf.py              (a new Space starts private: only you, when logged in)
    .venv\\Scripts\\python deploy_hf.py --public     (make it visible to anyone with the link)
    .venv\\Scripts\\python deploy_hf.py --private    (make it private again)

It uploads the same files as the TM471 zip (see build_zip.py, which includes the Dockerfile), so the
dataset, database, uploads and .env never leave this computer. The online copy gets its own demo
passwords (not the ones in README.md); a local copy is kept, with its secret key, in instance/hf_demo_logins.txt.
"""
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

from build_zip import ROOT, files_to_pack

SPACE_NAME = "smartdent"
SECRETS_FILE = ROOT / "instance" / "hf_demo_logins.txt"
SECRET_NAMES = {"DEMO_ADMIN_PASSWORD": "DEMO_ADMIN_PASSWORD", "DEMO_DOCTOR_PASSWORD": "DEMO_DOCTOR_PASSWORD",
                "SECRET_KEY": "HF_SECRET_KEY"}      # name on the Space -> name on GitHub

SPACE_README = """---
title: SmartDent
emoji: 🦷
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: AI support for reading panoramic dental X-rays
---

# SmartDent

SmartDent assists dentists in reading panoramic dental X-rays. It marks possible caries,
periapical lesions, impacted teeth and bone loss for the dentist to review. It does not diagnose;
the dentist makes every decision. TM471 final-year project.

This online demo starts with a fresh database each time the Space restarts.
Use fictional or anonymised X-rays only.
"""


def space_secrets():
    """The online copy's demo passwords and secret key: made once, then reused on every deploy."""
    if os.environ.get("GITHUB_ACTIONS"):              # on GitHub: from the repository secrets that are set
        return {space: os.environ[github] for space, github in SECRET_NAMES.items() if os.environ.get(github)}
    if SECRETS_FILE.exists():
        return dict(line.split("=", 1) for line in SECRETS_FILE.read_text().splitlines() if "=" in line)
    values = {"DEMO_ADMIN_PASSWORD": f"Admin-{secrets.token_urlsafe(9)}",
              "DEMO_DOCTOR_PASSWORD": f"Doctor-{secrets.token_urlsafe(9)}",
              "SECRET_KEY": secrets.token_hex(32)}
    SECRETS_FILE.parent.mkdir(exist_ok=True)
    SECRETS_FILE.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    return values


def stage_files(folder):
    """Copy the files to upload into a temporary folder, with the Space's own README."""
    for src, rel in files_to_pack():
        dst = folder / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    (folder / "README.md").write_text(SPACE_README, encoding="utf-8")


def main():
    api = HfApi()
    user = api.whoami()["name"]                      # fails with a clear message if not logged in
    repo_id = f"{user}/{SPACE_NAME}"

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=True, exist_ok=True)
    for flag, private in (("--public", False), ("--private", True)):   # otherwise keep what it is
        if flag in sys.argv[1:]:
            api.update_repo_settings(repo_id, repo_type="space", private=private)

    values = space_secrets()
    for key, value in values.items():                # Space secrets stay hidden, even on a public Space
        api.add_space_secret(repo_id, key, value)

    with tempfile.TemporaryDirectory() as tmp:
        stage_files(Path(tmp))
        api.upload_folder(folder_path=tmp, repo_id=repo_id, repo_type="space",
                          commit_message="Update SmartDent", delete_patterns="*")

    host = f"https://{user.lower().replace('_', '-')}-{SPACE_NAME}.hf.space"
    print(f"\nUploaded to https://huggingface.co/spaces/{repo_id}")
    print(f"The first build takes about 5-10 minutes. Then open the app directly at: {host}")
    if os.environ.get("GITHUB_ACTIONS"):             # never print passwords into GitHub's logs
        return
    print(f"Online demo logins (also in {SECRETS_FILE.relative_to(ROOT)}):")
    print(f"  admin@smartdent.local   {values['DEMO_ADMIN_PASSWORD']}")
    print(f"  doctor@smartdent.local  {values['DEMO_DOCTOR_PASSWORD']}")


if __name__ == "__main__":
    main()
