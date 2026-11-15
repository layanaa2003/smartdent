"""
Add the DENTEX panoramic X-rays to OUR TRAINING SET ONLY.

DENTEX (MICCAI 2023 challenge, CC BY 4.0) has 705 panoramic X-rays where every
abnormal tooth has a box and a diagnosis. Three of its diagnoses match ours:

    DENTEX "Caries" and "Deep Caries"  -> 0 Caries
    DENTEX "Periapical Lesion"         -> 1 Periapical lesion
    DENTEX "Impacted"                  -> 2 Impacted tooth

Things to know (and to mention in the report):
  * DENTEX has NO Bone Loss labels. Bone loss in these X-rays is unlabelled,
    so the model may learn "this is not bone loss". Compare the Bone Loss score
    with and without DENTEX before you keep it.
  * DENTEX boxes outline the WHOLE abnormal tooth; the Kaggle caries boxes mark
    the lesion itself. Per-X-ray sensitivity is not affected by this, but box
    mAP for caries may drop.
  * Val and test stay 100% Kaggle, so scores stay comparable with earlier runs.

Run it AFTER ml.prepare_dataset, on the same --out folder:
    python -m ml.add_dentex --src /content/dentex --out /content/prepared
    python -m ml.add_dentex --src /content/dentex --dry-run     # only print the numbers

--src may hold the DENTEX zip files or the already unzipped folders.
"""
import argparse
import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path

from ml import CLASS_NAMES

# DENTEX diagnosis name (lower case) -> our new class ID. Bone Loss (3) has no match.
DENTEX_TO_NEW = {"caries": 0, "deep caries": 0, "periapical lesion": 1, "impacted": 2}
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
RARE_CLASSES = {1}             # Periapical lesion: repeat these X-rays like prepare_dataset does


# ---------------------------------------------------------------- finding the files

def unzip_all(src):
    """Unzip every DENTEX zip inside src (once), keeping only the diagnosis part to save disk space."""
    for zip_path in sorted(Path(src).rglob("*.zip")):
        target = zip_path.with_suffix("")
        if target.exists():
            continue
        with zipfile.ZipFile(zip_path) as z:
            wanted = [n for n in z.namelist() if "disease" in n.lower()]
            print(f"Unzipping {len(wanted)} files from {zip_path.name}")
            z.extractall(target, members=wanted)


def find_disease_json(src):
    """Find the DENTEX JSON that has diagnosis labels (its annotations carry 'category_id_3')."""
    for json_path in sorted(Path(src).rglob("*.json")):
        try:
            data = json.loads(json_path.read_text())
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and any("category_id_3" in a for a in data.get("annotations", [])):
            return json_path, data
    raise FileNotFoundError(f"No DENTEX diagnosis JSON (with category_id_3) found inside {src}")


def index_images(folder):
    """Map each image file name to its path, searching all sub-folders."""
    return {p.name: p for p in Path(folder).rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES}


# ---------------------------------------------------------------- converting the labels

def diagnosis_map(data):
    """DENTEX category_id_3 -> our class ID, looked up by NAME so the ID order doesn't matter."""
    mapping = {}
    for category in data.get("categories_3", []):
        name = category["name"].strip().lower()
        if name in DENTEX_TO_NEW:
            mapping[category["id"]] = DENTEX_TO_NEW[name]
        else:
            print(f"  ignoring unknown DENTEX diagnosis: {category['name']}")
    return mapping


def coco_to_yolo(bbox, width, height):
    """COCO box [x, y, w, h] in pixels -> YOLO box (cx, cy, w, h) in the 0-1 range, clipped to the image."""
    x, y, w, h = bbox
    x1, y1 = max(x, 0), max(y, 0)
    x2, y2 = min(x + w, width), min(y + h, height)
    return (x1 + x2) / 2 / width, (y1 + y2) / 2 / height, (x2 - x1) / width, (y2 - y1) / height


def collect_images(data, mapping):
    """Return [{"file_name", "labels": [(class, box), ...]}] for every DENTEX image."""
    images = {im["id"]: {"file_name": Path(im["file_name"]).name, "width": im["width"],
                         "height": im["height"], "labels": []} for im in data["images"]}
    for ann in data["annotations"]:
        image = images.get(ann["image_id"])
        cls = mapping.get(ann.get("category_id_3"))
        if image is None or cls is None or ann["bbox"][2] < 1 or ann["bbox"][3] < 1:
            continue
        image["labels"].append((cls, coco_to_yolo(ann["bbox"], image["width"], image["height"])))
    return list(images.values())


# ---------------------------------------------------------------- writing

def build_plan(images, oversample):
    """List every output image: (new_name, image, labels). Rare-class X-rays are repeated."""
    plan = []
    for index, image in enumerate(sorted(images, key=lambda im: im["file_name"])):
        plan.append((f"dentex_{index:04d}", image, image["labels"]))
        if RARE_CLASSES & {cls for cls, _ in image["labels"]}:
            plan += [(f"dentex_{index:04d}_os{r + 1}", image, image["labels"]) for r in range(oversample)]
    return plan


def summarize(plan):
    """Print how many images and boxes DENTEX adds per class."""
    boxes, images = Counter(), Counter()
    for _, _, labels in plan:
        classes = [cls for cls, _ in labels]
        boxes.update(classes)
        images.update(set(classes))
    print(f"DENTEX adds {len(plan)} training images:")
    for cls, name in enumerate(CLASS_NAMES):
        print(f"  {name:<18} {images[cls]:>5} images {boxes[cls]:>6} boxes")


def write_plan(plan, image_paths, out_dir, preprocess=True):
    """Write the images and YOLO label files into out_dir/train."""
    from ml.prepare_dataset import write_label_file, write_image
    image_dir, label_dir = Path(out_dir) / "train" / "images", Path(out_dir) / "train" / "labels"
    if not image_dir.exists():
        raise FileNotFoundError(f"{image_dir} not found. Run ml.prepare_dataset first.")
    written = {}
    for i, (new_name, image, labels) in enumerate(plan):
        dst = image_dir / f"{new_name}.jpg"
        src = image_paths[image["file_name"]]
        if src in written:
            shutil.copyfile(written[src], dst)       # oversampled copy: no need to re-process
        else:
            write_image(src, dst, preprocess)
            written[src] = dst
        write_label_file(label_dir / f"{new_name}.txt", labels)
        if i % 200 == 0:
            print(f"  written {i}/{len(plan)} images")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", default="dentex", help="folder with the DENTEX download")
    parser.add_argument("--out", default="prepared", help="the dataset made by ml.prepare_dataset")
    parser.add_argument("--oversample", type=int, default=1,
                        help="extra copies of DENTEX X-rays with a periapical lesion (0 = off)")
    parser.add_argument("--no-preprocess", action="store_true", help="copy images without cleaning them")
    parser.add_argument("--dry-run", action="store_true", help="only print the numbers")
    args = parser.parse_args()

    unzip_all(args.src)
    json_path, data = find_disease_json(args.src)
    print(f"Using labels from {json_path}")
    images = collect_images(data, diagnosis_map(data))
    image_paths = index_images(json_path.parent) or index_images(json_path.parent.parent)
    missing = [im["file_name"] for im in images if im["file_name"] not in image_paths]
    if missing:
        print(f"  skipping {len(missing)} labelled images whose file was not found, e.g. {missing[0]}")
        images = [im for im in images if im["file_name"] in image_paths]
    plan = build_plan(images, args.oversample)
    summarize(plan)
    if not args.dry_run:
        write_plan(plan, image_paths, args.out, preprocess=not args.no_preprocess)
        print(f"\nDone. DENTEX added to {Path(args.out).resolve() / 'train'} (val and test unchanged)")


if __name__ == "__main__":
    main()
