// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as cdk from 'aws-cdk-lib';
import { IntakeStack } from '../lib/intake-stack';
import { MlStack } from '../lib/ml-stack';
import { SiteStack } from '../lib/site-stack';
import * as cdkJson from '../cdk.json';

let cache: Record<string, cdk.Stack> | undefined;

// The app as bin/app.ts builds it under cdk.json, synthesized once for every test file.
export function stacks(): Record<string, cdk.Stack> {
  if (!cache) {
    // The context bin/app.ts runs with, including the permissions boundary.
    const app = new cdk.App({ context: cdkJson.context });
    const intake = new IntakeStack(app, 'ConveyorIntake');
    const ml = new MlStack(app, 'ConveyorMl', { curated: intake.curated });
    const site = new SiteStack(app, 'ConveyorSite-factory-a', { site: 'factory-a', release: ml.release, signingKey: ml.signingKey });
    cache = { intake, ml, site };
  }
  return cache;
}
