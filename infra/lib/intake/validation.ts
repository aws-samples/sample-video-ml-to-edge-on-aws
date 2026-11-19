// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { EncryptedBucket } from '../encrypted-bucket';
import { LABELS, PREFIX, SITES } from '../config';

const ROOT = path.join(__dirname, '../../..');

export interface ValidationProps {
  intake: EncryptedBucket;
  curated: EncryptedBucket;
}

// Probes and re-encodes each clean clip into the curated bucket. It runs only on
// GuardDuty's NO_THREATS_FOUND result, and its role can read only objects carrying
// that tag, so an unscanned or infected object never reaches OpenCV.
export class Validation extends Construct {
  constructor(scope: Construct, id: string, props: ValidationProps) {
    super(scope, id);
    const { intake, curated } = props;

    const opencv = new lambda.LayerVersion(this, 'OpenCv', {
      code: lambda.Code.fromAsset(path.join(ROOT, 'infra/layers/opencv')),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      compatibleArchitectures: [lambda.Architecture.ARM_64],
      description: 'opencv-python-headless and numpy for the validation function',
    });
    const fn = new lambda.Function(this, 'Fn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.main',
      code: lambda.Code.fromAsset(path.join(ROOT, 'lambdas/validate')),
      layers: [opencv],
      memorySize: 2048,
      ephemeralStorageSize: cdk.Size.gibibytes(2),
      timeout: cdk.Duration.minutes(5),
      environment: {
        INTAKE_BUCKET: intake.bucket.bucketName,
        CURATED_BUCKET: curated.bucket.bucketName,
        SITES: SITES.join(','),
        LABELS: LABELS.join(','),
      },
      logGroup: new logs.LogGroup(this, 'Logs', { retention: logs.RetentionDays.ONE_MONTH, removalPolicy: cdk.RemovalPolicy.DESTROY }),
    });
    fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'ReadScannedClean',
      actions: ['s3:GetObject', 's3:GetObjectVersion'],
      resources: [intake.bucket.arnForObjects(`${PREFIX.intake}*`)],
      conditions: { StringEquals: { 's3:ExistingObjectTag/GuardDutyMalwareScanStatus': 'NO_THREATS_FOUND' } },
    }));
    fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'WriteCuratedAndRejected',
      actions: ['s3:PutObject'],
      resources: [curated.bucket.arnForObjects(`${PREFIX.curated}*`), curated.bucket.arnForObjects(`${PREFIX.rejected}*`)],
    }));
    intake.key.grantDecrypt(fn);
    // An encrypted PUT asks KMS only for a data key.
    curated.key.grant(fn, 'kms:GenerateDataKey');

    new events.Rule(this, 'OnCleanScan', {
      description: 'GuardDuty found no threat in a contributed clip',
      eventPattern: {
        source: ['aws.guardduty'],
        detailType: ['GuardDuty Malware Protection Object Scan Result'],
        detail: {
          scanStatus: ['COMPLETED'],
          resourceType: ['S3_OBJECT'],
          s3ObjectDetails: { bucketName: [intake.bucket.bucketName] },
          scanResultDetails: { scanResultStatus: ['NO_THREATS_FOUND'] },
        },
      },
      targets: [new targets.LambdaFunction(fn, { retryAttempts: 2 })],
    });
  }
}
