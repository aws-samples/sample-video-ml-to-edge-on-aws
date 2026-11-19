// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as cdk from 'aws-cdk-lib';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

// A versioned, TLS-only, private bucket encrypted with its own customer managed
// key, so access to its objects needs both an S3 grant and a grant on that key.
export class EncryptedBucket extends Construct {
  readonly bucket: s3.Bucket;
  readonly key: kms.Key;

  constructor(scope: Construct, id: string) {
    super(scope, id);
    this.key = new kms.Key(this, 'Key', {
      enableKeyRotation: true,
      description: `${id} bucket encryption`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    this.bucket = new s3.Bucket(this, 'Bucket', {
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: this.key,
      bucketKeyEnabled: true,
      versioned: true,
      enforceSSL: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
  }
}
