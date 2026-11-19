// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { EncryptedBucket } from '../encrypted-bucket';
import { MODEL_PACKAGE_GROUP, PREFIX, SITES } from '../config';

export interface ReleaseProps {
  ml: EncryptedBucket;
  release: EncryptedBucket;
}

// Turns a human approval in the model registry into a signed release: the
// EventBridge rule fires on Approved, the function signs release.json with an
// asymmetric KMS key whose private half never leaves KMS, and points every site
// channel at the new version.
export class Release extends Construct {
  readonly signingKey: kms.Key;

  constructor(scope: Construct, id: string, props: ReleaseProps) {
    super(scope, id);
    const { region, account } = cdk.Stack.of(this);
    const { ml, release } = props;

    this.signingKey = new kms.Key(this, 'SigningKey', {
      keySpec: kms.KeySpec.ECC_NIST_P256,
      keyUsage: kms.KeyUsage.SIGN_VERIFY,
      description: 'Signs model releases for the site gateways',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const fn = new lambda.Function(this, 'Fn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.main',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../../lambdas/release')),
      memorySize: 512,
      timeout: cdk.Duration.minutes(2),
      environment: {
        RELEASE_BUCKET: release.bucket.bucketName,
        SIGNING_KEY_ID: this.signingKey.keyArn,
        SITES: SITES.join(','),
      },
      logGroup: new logs.LogGroup(this, 'Logs', { retention: logs.RetentionDays.ONE_MONTH, removalPolicy: cdk.RemovalPolicy.DESTROY }),
    });
    fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'DescribePackages',
      actions: ['sagemaker:DescribeModelPackage'],
      resources: [`arn:aws:sagemaker:${region}:${account}:model-package/${MODEL_PACKAGE_GROUP}/*`],
    }));
    fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'ReadTrainingOutput',
      actions: ['s3:GetObject', 's3:GetObjectVersion'],
      resources: [ml.bucket.arnForObjects(`${PREFIX.trainingOutput}*`)],
    }));
    fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'WriteReleases',
      actions: ['s3:PutObject'],
      resources: [release.bucket.arnForObjects(`${PREFIX.releases}*`), release.bucket.arnForObjects(`${PREFIX.channels}*`)],
    }));
    ml.key.grantDecrypt(fn);
    // An encrypted PUT asks KMS only for a data key.
    release.key.grant(fn, 'kms:GenerateDataKey');
    this.signingKey.grant(fn, 'kms:Sign');

    new events.Rule(this, 'OnApproved', {
      description: 'A model package in the sample group was approved',
      eventPattern: {
        source: ['aws.sagemaker'],
        detailType: ['SageMaker Model Package State Change'],
        detail: { ModelPackageGroupName: [MODEL_PACKAGE_GROUP], ModelApprovalStatus: ['Approved'] },
      },
      targets: [new targets.LambdaFunction(fn, { retryAttempts: 2 })],
    });
  }
}
