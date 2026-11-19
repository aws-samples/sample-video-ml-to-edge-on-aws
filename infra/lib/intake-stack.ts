// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import { EncryptedBucket } from './encrypted-bucket';
import { MalwareScan } from './intake/malware-scan';
import { Portal } from './intake/portal';
import { Validation } from './intake/validation';
import { PREFIX } from './config';

// Contributor portal, intake of untrusted clips, malware scan, validation into
// the curated dataset.
export class IntakeStack extends cdk.Stack {
  readonly curated: EncryptedBucket;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    const intake = new EncryptedBucket(this, 'Intake');
    this.curated = new EncryptedBucket(this, 'Curated');

    // Untrusted bytes are kept only long enough to be scanned and validated.
    intake.bucket.addLifecycleRule({ expiration: cdk.Duration.days(7), noncurrentVersionExpiration: cdk.Duration.days(1) });
    // The browser PUTs with a presigned URL, which is the authorization; CORS only
    // has to let the portal page read the response. A wildcard origin keeps the
    // bucket from depending on the distribution, whose CSP names this bucket.
    intake.bucket.addCorsRule({ allowedMethods: [s3.HttpMethods.PUT], allowedOrigins: ['*'], allowedHeaders: ['content-type', 'x-amz-tagging'], maxAge: 3000 });

    const scan = new MalwareScan(this, 'MalwareScan', intake);
    intake.bucket.addToResourcePolicy(new iam.PolicyStatement({
      sid: 'ReadOnlyAfterCleanScan',
      effect: iam.Effect.DENY,
      principals: [new iam.AnyPrincipal()],
      actions: ['s3:GetObject', 's3:GetObjectVersion'],
      resources: [intake.bucket.arnForObjects('*')],
      conditions: {
        StringNotEquals: { 's3:ExistingObjectTag/GuardDutyMalwareScanStatus': 'NO_THREATS_FOUND' },
        ArnNotEquals: { 'aws:PrincipalArn': scan.role.roleArn },
      },
    }));

    new Portal(this, 'Portal', intake, this.curated);
    new Validation(this, 'Validation', { intake, curated: this.curated });

    new cdk.CfnOutput(this, 'CuratedBucket', { value: this.curated.bucket.bucketName });
  }
}
