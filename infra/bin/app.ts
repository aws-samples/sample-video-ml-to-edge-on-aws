// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as cdk from 'aws-cdk-lib';
import { IntakeStack } from '../lib/intake-stack';
import { MlStack } from '../lib/ml-stack';
import { SiteStack } from '../lib/site-stack';
import { SITES } from '../lib/config';

const app = new cdk.App();
cdk.Tags.of(app).add('project', 'sample-video-ml-to-edge');
const intake = new IntakeStack(app, 'ConveyorIntake');
const ml = new MlStack(app, 'ConveyorMl', { curated: intake.curated });
for (const site of SITES) {
  new SiteStack(app, `ConveyorSite-${site}`, { site, release: ml.release, signingKey: ml.signingKey });
}
