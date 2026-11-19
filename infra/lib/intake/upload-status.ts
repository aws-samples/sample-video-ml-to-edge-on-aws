// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { EncryptedBucket } from '../encrypted-bucket';
import { LABELS, PREFIX, SITES } from '../config';

export interface UploadStatusProps {
  intake: EncryptedBucket;
  curated: EncryptedBucket;
}

// Read-only status of a contributor's own uploads. It reads only object tags on
// the intake bucket, never intake bytes, so the clean-scan read gate stays intact.
export class UploadStatus extends Construct {
  readonly fn: lambda.Function;

  constructor(scope: Construct, id: string, props: UploadStatusProps) {
    super(scope, id);
    const { intake, curated } = props;
    this.fn = new lambda.Function(this, 'Fn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.main',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../../lambdas/status')),
      timeout: cdk.Duration.seconds(15),
      environment: {
        INTAKE_BUCKET: intake.bucket.bucketName,
        CURATED_BUCKET: curated.bucket.bucketName,
        SITES: SITES.join(','),
        LABELS: LABELS.join(','),
      },
      logGroup: new logs.LogGroup(this, 'Logs', { retention: logs.RetentionDays.ONE_MONTH, removalPolicy: cdk.RemovalPolicy.DESTROY }),
    });
    this.fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'ReadIntakeTags',
      actions: ['s3:GetObjectTagging'],
      resources: [intake.bucket.arnForObjects(`${PREFIX.intake}*`)],
    }));
    // An accepted clip is found by listing; only rejection records are read.
    this.fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'ReadRejections',
      actions: ['s3:GetObject'],
      resources: [curated.bucket.arnForObjects(`${PREFIX.rejected}*`)],
    }));
    // Without ListBucket a missing object answers 403 instead of 404.
    for (const [sid, bucket, prefixes] of [
      ['ListIntake', intake, [PREFIX.intake]],
      ['ListVerdicts', curated, [PREFIX.curated, PREFIX.rejected]],
    ] as const) {
      this.fn.addToRolePolicy(new iam.PolicyStatement({
        sid,
        actions: ['s3:ListBucket'],
        resources: [bucket.bucket.bucketArn],
        conditions: { StringLike: { 's3:prefix': prefixes.map((p) => `${p}*`) } },
      }));
    }
    curated.key.grantDecrypt(this.fn);
  }
}
