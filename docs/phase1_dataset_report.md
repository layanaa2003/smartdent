# Phase 1: Dataset report

Dataset: Kaggle "Dental Disease Panoramic Detection Dataset", unzipped into `data/`.
All numbers below come from `python scripts/inspect_dataset.py data` and `data/YOLO/YOLO/data.yaml`.

## What is in `data/`

| Item | What it is |
|---|---|
| `YOLO/YOLO/` | Images + YOLO label files (`train`, `valid`, `test`) and `data.yaml`. **This is the copy we use.** |
| `COCO/COCO/` | The same images again with COCO JSON labels (boxes only, no polygons). Not needed. |
| `best.pt` (368 MB), `checkpoint0033_4scale.pth` (562 MB) | Model weights trained by the dataset author. Not ours, not used; we train our own. |

## Size and splits

| Split | Images | Original radiographs behind them |
|---|---|---|
| train | 9,481 | 5,029 |
| valid | 2,871 | 2,072 |
| test | 1,580 | 1,573 |
| **total** | **13,932** | **5,976 unique** |

The images were exported from Roboflow with augmentation: each original X-ray appears 1 to 6 times
(file names like `NAME_jpg.rf.<hash>.jpg`). Sizes are 640x640 or 1615x840.

## Annotation format

YOLO **segmentation** format: `class x1 y1 x2 y2 ... xn yn` (normalized polygon points).
For our four classes, train and valid mix real polygons with 4-corner shapes (mostly rotated boxes);
the test split has **only** 4-corner shapes. COCO JSON has boxes only.

Consequence: train **detection** (boxes). Ultralytics converts the polygons to boxes automatically.
Segmentation is not reliable here because roughly half of the "masks" are just boxes.

## Class IDs confirmed

`data.yaml` lists 31 classes (0-30). The four targets match what we expected:

| Original ID | Name in data.yaml | New ID |
|---|---|---|
| 0 | Caries | 0 |
| 7 | Periapical lesion | 1 |
| 11 | impacted tooth | 2 |
| 13 | Bone Loss | 3 |

(COCO JSON numbers them 1-31, one higher. We use the YOLO IDs.)
A sample validation X-ray drawn with these labels shows them in the expected places
(third molars as impacted, bands along the bone crest as bone loss, small marks on crowns as caries).

## Per-class counts (four target classes)

| Class | Train imgs / anns | Valid imgs / anns | Test imgs / anns | Original X-rays (train) |
|---|---|---|---|---|
| Caries | 2,182 / 7,350 | 614 / 2,180 | 269 / 1,194 | 1,048 |
| Periapical lesion | 1,691 / 3,596 | 471 / 1,132 | 212 / 563 | 799 |
| Impacted tooth | 7,655 / 18,863 | 2,416 / 5,859 | 1,340 / 3,256 | 4,141 |
| Bone Loss | 1,277 / 2,646 | 212 / 484 | **0 / 0** | 1,257 |

About 95% of images contain at least one target class (8,984 of 9,481 in train).

## Problems found

1. **Class imbalance.** Impacted tooth has about 5x the annotations of Periapical lesion and 7x Bone Loss in train.
   Expect impacted teeth to score well and periapical lesions / bone loss to score lower.
2. **No Bone Loss in the test split.** We cannot measure Bone Loss on the given test set.
3. **Data leakage between splits.** The same original X-ray (as different augmented copies) appears in
   train and test 1,509 times, and in train and valid 1,189 times. Test scores on the given split would be
   unrealistically high.
4. **`data.yaml` test path points to the valid images**, and paths are the author's own computer paths.
5. **File names contain what look like patient names and dates.** The images are public and de-identified
   in content, but we should rename files and never display original file names in the app.

## Recommended fix for Phase 2

Re-split ourselves, by original radiograph: pool all 5,976 originals, keep each original's copies together,
and split about 70 / 15 / 15 so every split has all four classes. Then filter to the four classes, remap
IDs to 0-3, write a new `data.yaml`, and train YOLOv8 detection. For imbalance, report per-class metrics,
and if Periapical lesion / Bone Loss are weak, oversample the images that contain them.

## How Colab will get the data

The notebook will ask you to upload `kaggle.json` (or read it from Colab Secrets), then run:

```
!pip install -q kaggle
!kaggle datasets download -d lokisilvres/dental-disease-panoramic-detection-dataset -p /content/data --unzip
```

Never paste the token into a chat or commit it.
