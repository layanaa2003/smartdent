# SmartDent: facts for the report

Every number here comes from the code, the trained model file or `docs/final_test_results.json`
(made by `scripts/evaluate_final.py`). Use this sheet for Chapter 4 (implementation and results)
and as a shared reference for Chapters 5 and 6.

---

## 1. What SmartDent is

A web application that assists dentists in reading **panoramic dental X-rays**. It marks five
possible findings with boxes and confidence scores: **caries, periapical lesion, impacted tooth,
bone loss and retained root**. The dentist reviews every finding (agree / disagree), can add
findings the AI missed, and gets suggested next steps and a PDF report. SmartDent does not
diagnose; the dentist makes every decision.

## 2. Dataset

| | |
|---|---|
| Source | Kaggle "Dental Disease Panoramic Detection Dataset" (Roboflow export, YOLO format, 31 classes) |
| Size | 13,932 images made from **5,976 original panoramic X-rays** (Roboflow added augmented copies) |
| Classes kept | 5 of the 31: Caries, Periapical lesion, Impacted tooth, Bone Loss, Retained root (renumbered 0-4) |
| Labels | Polygons in the source, converted to boxes (`ml/prepare_dataset.py`) |

Problems found in the original Kaggle split (see `docs/phase1_dataset_report.md`):
- The Kaggle **test split had no Bone Loss** at all.
- Augmented copies of the **same X-ray were in train and test** (data leakage).
- File names contained patient names.

What we did (`ml/prepare_dataset.py`):
- **Re-split 70 / 15 / 15 by original X-ray** (grouped), stratified by the rarest class in each X-ray,
  fixed seed 42. Leakage check: **0** X-rays in more than one split.
- Train keeps all augmented copies; val and test keep one copy per X-ray (highest resolution).
- Every image renamed (`xray_00001_0.jpg`), so no patient names remain.
- Rare-class oversampling in **train only**: X-rays with a periapical lesion, bone loss or retained
  root are repeated twice more (`--oversample 2`).
- Preprocessing (`ml/preprocess.py`), identical in training and in the app: grayscale, 3x3 median
  filter (noise), CLAHE contrast (clip 2.0, 8x8 tiles), back to 3 channels.

Split sizes (X-rays with the class / boxes of the class):

| Split | X-rays | Caries | Periapical lesion | Impacted tooth | Bone Loss | Retained root |
|---|---|---|---|---|---|---|
| Train (before oversampling) | 4,183 | 2,194 / 7,646 | 1,691 / 3,844 | 7,992 / 19,565 | 1,050 / 2,191 | 53 / 132 |
| Validation | 896 | 190 / 677 | 133 / 201 | 724 / 1,768 | 215 / 452 | 6 / 9 |
| Test | 897 | 183 / 549 | 120 / 160 | 738 / 1,806 | 208 / 451 | 7 / 22 |

Train counts are image counts including Roboflow's augmented copies (9,780 images; 14,872 after oversampling).

## 3. Model and training

| | |
|---|---|
| Model | **YOLOv8s** (Ultralytics), starting from COCO-pretrained weights |
| Input size | **1024 px** (version 1 used 640; larger keeps small caries and the thin bone-loss line) |
| Batch | 4 |
| Epochs | up to 72, early stopping patience 15, `time` limit so a Kaggle session can finish evaluation |
| Augmentation | YOLO defaults, but **no colour augmentation** (`hsv_h=0, hsv_s=0`; X-rays are grey), left-right flip 0.5 |
| Hardware | Kaggle Notebooks GPU (P100 / T4); runs resumed across sessions from `last.pt` |
| Notebook | `notebooks/smartdent_training_5class_kaggle.ipynb` (Colab version: `smartdent_training_5class.ipynb`) |
| Output | `models/best.pt` (22.6 MB) and `models/thresholds.json` |
| DENTEX | Optional extra dataset supported (`ml/add_dentex.py`) but **not used** in the final model |

### Per-class confidence thresholds

The model is run once at a very low confidence (0.01). For each class we then look at per-X-ray
sensitivity and specificity at thresholds 0.05-0.50 on the **validation** set and keep the highest
threshold that still reaches **80% sensitivity** (`ml/evaluate.py: pick_thresholds`). For a tool a
dentist double-checks, missing less is worth some extra false alarms.

| Class | Threshold | Why |
|---|---|---|
| Caries | 0.05 | highest threshold with >= 80% sensitivity on val |
| Periapical lesion | 0.05 | no threshold reached 80%; lowest tried |
| Impacted tooth | 0.50 | reaches 80% even at the highest threshold |
| Bone Loss | **0.15** | val suggested 0.10, but that gave val specificity 0.23. At 0.15 val sensitivity is 0.80 and specificity 0.48, so we chose 0.15 |
| Retained root | 0.05 | too few cases to tune; lowest tried |

## 4. Results on the held-out test set (897 X-rays never seen in training)

### 4a. Per X-ray: "does this X-ray show the condition?" (at the thresholds above)

| Condition | TP | FN | FP | TN | Sensitivity | Specificity | Accuracy |
|---|---|---|---|---|---|---|---|
| Caries | 154 | 29 | 121 | 593 | **0.842** | 0.831 | 0.833 |
| Periapical lesion | 72 | 48 | 187 | 590 | **0.600** | 0.759 | 0.738 |
| Impacted tooth | 727 | 11 | 33 | 126 | **0.985** | 0.792 | 0.951 |
| Bone Loss | 176 | 32 | 371 | 318 | **0.846** | 0.462 | 0.551 |
| Retained root | 3 | 4 | 13 | 877 | 0.429 | 0.985 | 0.981 |

Retained root: only 7 test X-rays have one, so this number is very uncertain. Validation and
test together: 6 of 13 found, sensitivity 0.46 (95% CI 0.23-0.71), specificity 0.988.

### 4b. Per box (YOLO's standard detection metrics, test set)

| Condition | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Caries | 0.321 | 0.475 | 0.388 | 0.155 |
| Periapical lesion | 0.144 | 0.231 | 0.104 | 0.035 |
| Impacted tooth | 0.784 | 0.973 | 0.928 | 0.593 |
| Bone Loss | 0.171 | 0.490 | 0.198 | 0.099 |
| Retained root | 0.435 | 0.273 | 0.342 | 0.171 |
| **All** | **0.371** | **0.489** | **0.392** | **0.211** |

Box metrics are much lower than per-X-ray metrics because a box only counts if it overlaps the
true box by at least 50%. Bone loss is a long band whose box size varies a lot between annotators,
and caries / periapical lesions are small, so exact overlap is hard even when the area is right.

### 4c. Compared with version 1 (4 classes, 640 px, Colab)

| Per-X-ray sensitivity | v1 | Final |
|---|---|---|
| Caries | 0.57 | **0.84** |
| Periapical lesion | 0.33 | **0.60** |
| Impacted tooth | 0.995 | 0.985 |
| Bone Loss | 0.42 | **0.85** |
| Retained root | (not in v1) | 0.43 |
| mAP50, all classes | 0.42 (4 classes) | 0.39 (5 classes) |

v1 used one 25% threshold for all classes; the final model uses the per-class thresholds above
(`models/best_v1.pt` keeps the v1 model).

### 4d. Speed

About **0.33 s per X-ray** for detection on a laptop CPU at 1024 px (no GPU). The whole analysis
in the app, including the annotated image and PDF report, takes a few seconds. The first heatmap
of an X-ray takes about 4 s (model loading), later ones about 0.5 s.

### 4e. Limitations to discuss

- **Bone loss specificity is low (0.46):** more than half of X-rays without bone loss get a box.
  This is the cost of high sensitivity.
- **Periapical lesions** are found in 60% of affected X-rays; small, faint lesions are missed.
- **Retained root** has very few training (53 X-rays) and test examples; its numbers are not reliable.
- One dataset, one source: no external validation on X-rays from other clinics or machines.
- Thresholds were chosen on validation, reported on test (no tuning on test).

## 5. Explainable AI: heatmaps

`app/heatmap.py`, switch **"Show heatmap"** on the X-ray page.

- Method: **EigenCAM** (Muhammad & Yeasin, 2020), a gradient-free member of the Grad-CAM family.
  Classic Grad-CAM needs the gradient of one class score, which a YOLO detector does not give for a
  whole image; EigenCAM needs no gradients and no retraining.
- It takes the feature maps feeding the YOLO **small- and medium-object detection heads**, keeps
  their first principal component, averages them and colours the result over the X-ray
  (red/yellow = most influence; weak areas below 25% are left uncoloured). The large-object head was
  left out because in testing it only highlighted the image border.
- The heatmap is made the first time the dentist asks for it and is redone after a re-analysis.
- Observation: hot spots sit on the lesion areas the boxes mark, but the model also attends to the
  cervical spine and jaw joints (normal anatomy). The page tells the dentist that the heatmap shows
  what drove the model, not whether a finding is real.

## 6. The application

| | |
|---|---|
| Stack | Python 3, **Flask** 3.1, Flask-Login, Flask-WTF, **SQLite** (SQLAlchemy), ReportLab (PDF), OpenCV, PyTorch / Ultralytics |
| Roles | **Administrator** and **Dentist** |
| Runs | locally (`start.bat` / `start.sh` / `start.command`, `http://localhost:5000`) or online as a Hugging Face Docker Space |

Dentist features:
- Patients: add, edit, list with search and sorting; transfer a patient to another dentist.
- Upload a panoramic X-ray (JPEG/PNG, max 20 MB; checked by decoding it, not by its name).
- Automatic AI analysis: coloured boxes with confidence, findings list, plain-language summary.
- Human in the loop: **Agree / Disagree** on each AI finding; **mark missed findings** by drawing a
  box, choosing the condition and adding a note (stored apart from the AI's findings).
- **Suggested next steps** per finding, from published dental guidelines (with sources); rejected
  findings are left out.
- **Heatmap** of where the AI looked.
- Zoomable viewer (scroll to zoom, drag to move).
- **PDF report** (rebuilt after every review), download X-ray, email X-ray and report if SMTP is set up.
- Dashboard with statistics and the X-rays still waiting for review.

Sources behind the suggested next steps (`app/recommendations.py`):

| Finding | Source |
|---|---|
| Periapical lesion | ESE S3-level guideline, Treatment of pulpal and apical disease (2023) |
| Caries | FDI policy statement on carious lesions (2019); SDCEP caries guidance (2018) |
| Bone loss | EFP S3-level guideline, Treatment of stage I-III periodontitis (2020) |
| Retained root | Nayyar J, Clarke M, O'Sullivan M, Stassen LF. Fractured root tips during dental extractions and retained root fragments: a clinical dilemma? *Br Dent J* 2015;218(5):285-290 (doi:10.1038/sj.bdj.2015.147); Benton PN, Chang P. Oral Surgery, Extraction of Roots. *StatPearls*, 2023; Patel V et al. *Dental Update* 2013;40(5):370-6, doi:10.12968/denu.2013.40.5.370 (roots left in bone; full title: "To retrieve or not to retrieve the coronectomy root – the clinical dilemma"); supervising dentist to confirm. Review articles: no formal guideline exists for retained roots |
| Impacted tooth | NICE TA1, Guidance on the extraction of wisdom teeth |

Administrator features: add, edit and remove dentists; see all patients; transfer one patient or all
of a dentist's patients; a dentist who still has patients cannot be removed until they are moved.
The administrator cannot open X-rays.

## 7. Security and privacy

- Passwords stored as **hashes** only (Werkzeug).
- **CSRF protection** on every form (Flask-WTF).
- Role checks on every page; a dentist can only open **their own** patients (anything else returns 404).
- Uploaded X-rays get **random file names** and are stored outside the public folder; they are served
  only to the patient's own dentist.
- Upload size limit 20 MB; files must decode as images.
- Locally the app listens on **127.0.0.1 only**, with the debug console off.
- Secret key from an environment variable, or generated into `instance/secret_key` on first run.
- Online demo: secure, cross-site cookies (HTTPS), its own demo passwords; the model file lives in a
  **private** Hugging Face model repository and is downloaded by the Space at start-up.
- Dataset images renamed so no patient names remain; use anonymised X-rays only.

## 8. Testing

**68 automated tests** (pytest, `tests/`), all passing: login and roles, access control between
dentists, patient management and transfers, upload validation, the full AI pipeline with the real
model (upload, analysis, re-run, reviews, PDF), per-class thresholds, dentist-added findings,
recommendations, dataset preparation (split, no leakage, box conversion), evaluation maths, and the
heatmap.

## 9. Deployment

- **Offline package:** `python build_zip.py` makes `dist/SmartDent.zip` (code, model, samples,
  notebooks, docs; no dataset, database or secrets). The marker unzips it and runs `start.bat`.
- **Online demo:** https://layanaalnabulsi-smartdent.hf.space (Hugging Face Docker Space, CPU).
  Fresh database on every restart; for demonstration with anonymised images only.
- **Source:** private GitHub repository `layanaa2003/smartdent`.

## 10. How to reproduce the numbers

1. Unzip the Kaggle dataset into `data/` (so `data/YOLO/YOLO/data.yaml` exists).
2. `.venv\Scripts\python scripts\evaluate_final.py eval_output` (about 20 minutes on a CPU).
3. Compare `eval_output/final_results.json` with `docs/final_test_results.json`.
The same split and numbers were also produced independently by the Kaggle notebook.
