Sample panoramic X-rays for trying SmartDent
============================================

sample_01.jpg ... sample_05.jpg are panoramic dental X-rays from the public Kaggle
"Dental Disease Panoramic Detection Dataset". All five come from SmartDent's own
TEST split (ml/prepare_dataset.py, seed 42), so the model never saw them in training.

De-identification: the original file names (which contained names) were replaced with
sample_NN.jpg, and each image was re-saved, which drops any embedded metadata.
The images were checked by eye: they carry no names, dates or other text (only an "L" side marker).

Labelled conditions in the dataset (ground truth, for comparison with SmartDent's output):
  sample_01.jpg  Bone loss, caries, periapical lesion
  sample_02.jpg  Caries, periapical lesion
  sample_03.jpg  Bone loss, caries, impacted tooth
  sample_04.jpg  Bone loss, caries, periapical lesion
  sample_05.jpg  Bone loss, caries, impacted tooth

How to use: log in as the demo dentist, open "Demo Patient", and upload one of these files.
