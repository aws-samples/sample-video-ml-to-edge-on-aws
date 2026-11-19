# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""tiny3d: a small 3D CNN trained from scratch, so the sample downloads no weights."""

from torch import nn


class Tiny3d(nn.Module):
    """Four Conv3d-BatchNorm-ReLU-MaxPool blocks (16, 32, 64, 128 channels), global
    average pooling and a linear head. Input (batch, 3, frames, size, size)."""

    def __init__(self, num_classes: int):
        super().__init__()
        layers, cin = [], 3
        for cout, pool in ((16, (1, 2, 2)), (32, (2, 2, 2)), (64, (2, 2, 2)), (128, (2, 2, 2))):
            layers += [nn.Conv3d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm3d(cout),
                       nn.ReLU(inplace=True), nn.MaxPool3d(pool)]
            cin = cout
        self.features = nn.Sequential(*layers)
        self.head = nn.Linear(cin, num_classes)

    def forward(self, x):
        return self.head(self.features(x).mean(dim=(2, 3, 4)))
