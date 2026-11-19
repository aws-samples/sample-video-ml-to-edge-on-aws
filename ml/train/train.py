# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""SageMaker script-mode training of tiny3d on a frozen dataset snapshot.

Inputs: SM_CHANNEL_TRAIN/<site>/<label>/*.mp4 (the curated clips) and
SM_CHANNEL_SNAPSHOT/manifest.json with the held-out test clips in
SM_CHANNEL_SNAPSHOT/test/<site>/<label>/*.mp4 (scripts/snapshot.py). The curated
clips are split into train and validation, and the epoch with the best validation
accuracy is kept, so validation accuracy is a selection score. The exported ONNX
model, which is what ships, is then scored once on the test clips, which take no
part in training or selection: test_accuracy is the model's quality metric.

Output in SM_MODEL_DIR: model.onnx, labels.json, preprocess.py (this job's own copy,
which the gateway decodes with), metrics.json and selftest/<label>/*.mp4 drawn from
the test clips. The job fails before writing metrics.json when the ONNX export
disagrees with the trained network. Prints `epoch=<n> train_loss=<x>
val_accuracy=<y>` per epoch and `test_accuracy=<z>` once for the SageMaker metric
regexes.
"""

import argparse
import copy
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset  # noqa: E402
from model import Tiny3d  # noqa: E402
import preprocess  # noqa: E402
from preprocess import CLIP_FORMAT, load_clip  # noqa: E402

# fp32 torch and onnxruntime CPU logits agree to about 1e-6; 1e-3 still catches an
# export that computes a different function.
ONNX_MAX_ABS_DIFF = 1e-3
SELFTEST_PER_GROUP = 2
LR = 3e-3
VAL_FRACTION = 0.2
SEED = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--train-dir", type=Path, default=Path(os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train")))
    parser.add_argument("--snapshot-dir", type=Path, default=Path(os.environ.get("SM_CHANNEL_SNAPSHOT", "/opt/ml/input/data/snapshot")))
    parser.add_argument("--model-dir", type=Path, default=Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model")))
    return parser.parse_args()


def tensors(clips, labels):
    x = np.stack([load_clip(str(path), **CLIP_FORMAT) for path, _, _ in clips])
    return torch.from_numpy(x), torch.tensor([labels.index(label) for _, _, label in clips])


@torch.no_grad()
def predict(model, x, device, bs=64):
    model.eval()
    return torch.cat([model(x[i:i + bs].to(device)).argmax(1).cpu() for i in range(0, len(x), bs)])


def fit(model, xtr, ytr, xva, yva, args, device):
    """Trains and keeps the weights of the epoch with the best validation accuracy;
    returns that accuracy and epoch."""
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    steps = args.epochs * ((len(xtr) + args.batch_size - 1) // args.batch_size)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, total_steps=steps)
    loss_fn = nn.CrossEntropyLoss()
    best, best_epoch, best_state = -1.0, 0, None
    for epoch in range(1, args.epochs + 1):
        model.train()
        perm, total = torch.randperm(len(xtr)), 0.0
        for i in range(0, len(xtr), args.batch_size):
            idx = perm[i:i + args.batch_size]
            xb = xtr[idx]
            # Mirroring keeps the label: belts run in both directions in the data.
            if torch.rand(1) < 0.5:
                xb = xb.flip(-1)
            opt.zero_grad()
            loss = loss_fn(model(xb.to(device)), ytr[idx].to(device))
            loss.backward()
            opt.step()
            sched.step()
            total += float(loss) * len(idx)
        val_acc = float((predict(model, xva, device) == yva).float().mean())
        print(f"epoch={epoch} train_loss={total / len(xtr):.4f} val_accuracy={val_acc:.4f}", flush=True)
        if val_acc > best:
            best, best_epoch, best_state = val_acc, epoch, copy.deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    return best, best_epoch


def export_onnx(model, path: Path, sample: torch.Tensor) -> float:
    """Exports the model and returns the largest logit difference to torch on `sample`."""
    import onnxruntime as ort

    model = model.eval().cpu()
    torch.onnx.export(model, sample[:1], str(path), input_names=["clip"], output_names=["logits"],
                      opset_version=17, dynamo=False, dynamic_axes={"clip": {0: "batch"}, "logits": {0: "batch"}})
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    with torch.no_grad():
        expected = model(sample).numpy()
    return float(np.max(np.abs(expected - session.run(["logits"], {"clip": sample.numpy()})[0])))


def onnx_predict(path: Path, x: torch.Tensor, bs: int = 64) -> torch.Tensor:
    """Class predictions of the exported model file, the one the release ships."""
    import onnxruntime as ort

    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return torch.cat([torch.from_numpy(session.run(["logits"], {"clip": x[i:i + bs].numpy()})[0]).argmax(1)
                      for i in range(0, len(x), bs)])


def main() -> None:
    args = parse_args()
    torch.manual_seed(SEED)
    args.model_dir.mkdir(parents=True, exist_ok=True)
    manifest = dataset.verify_snapshot(args.train_dir, args.snapshot_dir)
    clips = dataset.list_clips(args.train_dir)
    test = dataset.list_clips(args.snapshot_dir / "test")
    labels = sorted({label for _, _, label in clips})
    unknown = {label for _, _, label in test} - set(labels)
    if unknown:
        raise SystemExit(f"test clips carry labels no training clip has: {sorted(unknown)}")
    train, val = dataset.split(clips, VAL_FRACTION, SEED)
    if not val:
        raise SystemExit("no validation clips: every (site, label) group has a single clip")
    print(f"labels={labels} num_train={len(train)} num_val={len(val)} num_test={len(test)}", flush=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    xtr, ytr = tensors(train, labels)
    xva, yva = tensors(val, labels)
    model = Tiny3d(len(labels)).to(device)
    selection_val, selected_epoch = fit(model, xtr, ytr, xva, yva, args, device)

    onnx_path = args.model_dir / "model.onnx"
    diff = export_onnx(model, onnx_path, xva[:8])
    if diff > ONNX_MAX_ABS_DIFF:
        raise SystemExit(f"ONNX logits differ from torch by {diff:.2e} > {ONNX_MAX_ABS_DIFF:.0e}")
    xte, yte = tensors(test, labels)
    pred = onnx_predict(onnx_path, xte)
    test_acc = round(float((pred == yte).float().mean()), 4)
    per_label = {lab: round(float((pred[yte == c] == c).float().mean()), 4)
                 for c, lab in enumerate(labels) if bool((yte == c).any())}
    print(f"test_accuracy={test_acc:.4f}", flush=True)

    for path, site, label in dataset.selftest_clips(test, SELFTEST_PER_GROUP):
        # Test clip names repeat across sites.
        target = args.model_dir / "selftest" / label / f"{site}-{path.name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (args.model_dir / "labels.json").write_text(json.dumps(labels))
    shutil.copyfile(preprocess.__file__, args.model_dir / "preprocess.py")
    metrics = {"arch": "tiny3d", "test_accuracy": test_acc, "test_accuracy_per_label": per_label,
               "selection_val_accuracy": round(selection_val, 4), "selected_epoch": selected_epoch,
               "num_train": len(train), "num_val": len(val), "num_test": len(test), "onnx_max_abs_diff": diff,
               "snapshot": manifest["snapshot"], "epochs": args.epochs}
    (args.model_dir / "metrics.json").write_text(json.dumps(metrics, indent=1))
    print(json.dumps(metrics), flush=True)


if __name__ == "__main__":
    main()
