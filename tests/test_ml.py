"""Tests for the dataset and evaluation helpers. Run with:  pytest"""
from ml.evaluate import image_level_metrics, iou, match_boxes, worst_images
from ml.prepare_dataset import (convert_label_line, copies_to_keep, original_name,
                                polygon_to_box, split_originals)


def test_original_name_strips_roboflow_suffix():
    assert original_name("abc-NAME_2020_jpg.rf.123abc.jpg") == "abc-NAME_2020"


def test_polygon_to_box():
    cx, cy, w, h = polygon_to_box([0.1, 0.2, 0.3, 0.2, 0.3, 0.6, 0.1, 0.6])
    assert (round(cx, 3), round(cy, 3), round(w, 3), round(h, 3)) == (0.2, 0.4, 0.2, 0.4)


def test_convert_label_line_remaps_and_drops():
    assert convert_label_line("13 0.5 0.5 0.2 0.2")[0] == 3     # Bone Loss -> 3
    assert convert_label_line("11 0.5 0.5 0.2 0.2")[0] == 2     # Impacted tooth -> 2
    assert convert_label_line("2 0.5 0.5 0.2 0.2") is None      # Filling is dropped
    assert convert_label_line("") is None


def test_split_keeps_copies_together_and_is_repeatable():
    groups = {f"xray{i}": [{"image": f"{i}a", "labels": [(i % 4, (0.5, 0.5, 0.1, 0.1))]},
                           {"image": f"{i}b", "labels": []}] for i in range(100)}
    first, second = split_originals(groups), split_originals(groups)
    assert first == second                                       # same seed, same split
    assert set(first.values()) == {"train", "val", "test"}
    assert sum(1 for s in first.values() if s == "train") == 72  # ~70% (rounded per class)


def test_train_keeps_all_copies():
    copies = [{"image": "a"}, {"image": "b"}]
    assert copies_to_keep(copies, "train") == copies


def test_iou():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert round(iou((0, 0, 10, 10), (5, 0, 15, 10)), 3) == 0.333


def test_match_boxes():
    truths = [(0, (0, 0, 10, 10)), (1, (50, 50, 60, 60))]
    predictions = [(0, (1, 1, 10, 10), 0.9),      # finds the caries
                   (1, (0, 0, 10, 10), 0.8)]      # wrong place for class 1
    assert match_boxes(truths, predictions) == (1, 1, 1)


def test_image_level_metrics():
    results = [({0}, {0}), ({0}, set()), (set(), {0}), (set(), set())]
    caries = image_level_metrics(results)["Caries"]
    assert (caries["sensitivity"], caries["specificity"], caries["accuracy"]) == (0.5, 0.5, 0.5)


def test_worst_images_orders_by_mistakes():
    per_image = {"good": ([(0, (0, 0, 10, 10))], [(0, (0, 0, 10, 10), 0.9)]),
                 "bad": ([(0, (0, 0, 10, 10))], [(1, (40, 40, 50, 50), 0.9)])}
    assert worst_images(per_image)[0] == ("bad", 1, 1)
