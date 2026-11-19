// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

// The fictitious sites and the labels a contributor may assign to a clip.
export const SITES = ['factory-a', 'factory-b'];
export const LABELS = ['normal', 'jam', 'drop', 'empty'];
export const PREFIX = {
  intake: 'intake/',
  curated: 'curated/',
  rejected: 'rejected/',
  manifests: 'manifests/',
  code: 'code/',
  trainingOutput: 'training-output/',
  releases: 'releases/',
  channels: 'channels/',
};
export const MODEL_PACKAGE_GROUP = 'conveyor-events';
// scripts/train_job.py names every training job of the sample with this prefix.
export const TRAINING_JOB_PREFIX = 'tiny3d-';
