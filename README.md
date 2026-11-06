# SmartDent

SmartDent is a web app that **assists dentists** in reading **panoramic dental X-rays**.
It marks possible findings with boxes and confidence scores, so the dentist can review them
alongside their own judgment. **SmartDent does not diagnose.** The dentist makes every decision
and can agree or disagree with each AI finding.

- Image type: **panoramic** X-rays only (JPEG or PNG).
- It looks for **4 conditions**: caries, periapical lesion, impacted tooth, bone loss.
- Everything runs on your own computer. X-rays never leave it.

TM471 final-year project.

---

## Quick start

You need **Python 3.10 or newer** ([python.org/downloads](https://www.python.org/downloads/)).
On Windows, tick **"Add python.exe to PATH"** during installation.

| System | What to do |
|---|---|
| **Windows** | Unzip the folder, then double-click **`start.bat`** |
| **Mac** | Unzip, then double-click **`start.command`** (or run `./start.sh` in Terminal) |
| **Linux** | Unzip, then run `./start.sh` (or `bash start.sh`) |

The start script does everything:

1. Checks that Python 3.10+ is installed.
2. Creates a private Python environment in `.venv` (first run only).
3. Installs the packages from `requirements.txt` (first run only: **needs internet, about 1 GB, 5-15 minutes**).
4. Creates the database and adds the demo accounts below (only if the database is empty).
5. Starts SmartDent and opens **http://localhost:5000** in your browser.

Later runs start in a few seconds and work **offline**. Keep the black window open while you use
SmartDent; close it (or press Ctrl+C) to stop.

No `.env` file is needed. SmartDent creates its own secret key in `instance/secret_key`.

## Demo logins

| Role | Email | Password |
|---|---|---|
| Administrator | `admin@smartdent.local` | `SmartDent-admin-2026` |
| Dentist | `doctor@smartdent.local` | `SmartDent-doctor-2026` |

The demo dentist has one fictional patient, **Demo Patient**. These accounts exist only in a new,
empty database (`instance/smartdent.db`). They are for demonstration only.

## How to use

**As the dentist** (`doctor@smartdent.local`):

1. Open **Demo Patient** from *My patients* (or add a new patient with *Add patient*).
2. Under **Upload a new X-ray**, choose one of the files in the `samples/` folder and click **Upload X-ray**.
3. SmartDent analyses it (a few seconds on a normal laptop) and opens the result:
   - coloured boxes on the X-ray (click the X-ray to zoom);
   - the list of **AI findings** with confidence scores; click **Agree** or **Disagree** on each one;
   - **Suggested next steps** based on published dental guidelines;
   - **Download PDF report** for the patient.
4. The dashboard shows which X-rays still wait for your review.

**As the administrator** (`admin@smartdent.local`): add, edit or remove dentists, see all patients,
and transfer patients from one dentist to another. The administrator cannot open X-rays; only the
patient's own dentist can.

Use fictional or anonymised images only.

## The AI model

| | |
|---|---|
| Model | YOLOv8s object detector (Ultralytics), file `models/best.pt` (22 MB) |
| Data | Kaggle "Dental Disease Panoramic Detection Dataset", 5,976 unique panoramic X-rays |
| Split | Re-split 70/15/15 by original X-ray, so no X-ray is in both training and test (`ml/prepare_dataset.py`) |
| Training | Google Colab GPU, 640 px images (`notebooks/smartdent_training.ipynb`) |
| Preprocessing | The same noise reduction and contrast step in training and in the app (`ml/preprocess.py`) |
| Speed | About 0.2 s per X-ray on a laptop CPU (no GPU needed) |
| Threshold | Boxes under 25% confidence are not shown |

Test-set results (sensitivity per X-ray): impacted tooth 0.995, caries 0.57, bone loss 0.42,
periapical lesion 0.33; mAP50 over all classes 0.42. Small lesions are the hardest, which is
one more reason the dentist must check the whole image and not only the boxes.

## Project structure

```
smartdent/
├── start.bat / start.sh / start.command   one-click start (Windows / Linux+Mac / Mac)
├── run.py                 starts the web app (python run.py --open)
├── requirements.txt       pinned Python packages
├── .env.example           optional settings (email sending, port)
├── app/                   the Flask web app
│   ├── __init__.py        app factory, secret key, error pages
│   ├── auth.py            login, logout, role checks
│   ├── admin.py           administrator pages
│   ├── doctor.py          dentist pages: patients, upload, results, downloads
│   ├── inference.py       runs the YOLO model and draws the boxes
│   ├── analysis.py        stores results and builds the PDF report
│   ├── recommendations.py suggested next steps per finding
│   ├── reports.py         PDF report (ReportLab)
│   ├── models.py          database tables (SQLite)
│   ├── templates/         HTML pages
│   └── static/            CSS, JavaScript, logo
├── ml/                    preprocessing, dataset preparation, evaluation
├── models/best.pt         the trained model
├── notebooks/             Google Colab training notebook
├── scripts/seed.py        creates the database and demo accounts
├── samples/               5 de-identified test X-rays to try
├── tests/                 automated tests (pytest)
├── docs/                  project documents
└── instance/              created on first run: database, uploads, secret key (not in the zip)
```

Run the tests with `.venv\Scripts\python -m pytest` (Windows) or `.venv/bin/python -m pytest` (Mac/Linux).

## Troubleshooting

| Problem | Fix |
|---|---|
| "Python 3.10 or newer was not found" | Install Python from python.org. On Windows tick "Add python.exe to PATH", then run `start.bat` again. |
| Installing packages fails | The first run needs internet. Check the connection and run the start script again; it continues where it stopped. |
| The browser does not open | Open **http://localhost:5000** yourself. If the window says another port (e.g. 5001), use that one. |
| Port 5000 is in use | SmartDent picks the next free port and prints it. On a Mac, AirPlay Receiver often uses port 5000. |
| "The .venv folder is broken" | Delete the `.venv` folder and run the start script again. |
| Wrong email or password | The demo logins only exist in a new database. To start fresh, stop SmartDent and rename `instance/smartdent.db`; the next start creates a new one with the demo accounts. |
| "The AI model file (models/best.pt) is missing" | Make sure `models/best.pt` was unzipped with the rest of the folder. |
| `./start.sh: Permission denied` | Run `bash start.sh`, or `chmod +x start.sh start.command` once. |
| Mac says the file is from an unidentified developer | Right-click `start.command`, choose Open, then Open again. |
| Fonts look plain | The web fonts come from Google Fonts; without internet the app uses system fonts. Everything still works. |

## Privacy and limits

- SmartDent is a decision-support tool for qualified dentists, not a medical device.
- Uploaded X-rays get random file names and are only served to the patient's own dentist.
- Passwords are stored as hashes only. The app listens on this computer only (127.0.0.1).
