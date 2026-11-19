// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { Match, Template } from 'aws-cdk-lib/assertions';
import { stacks } from './stacks';

test.each(['intake', 'ml'])('every bucket in %s is encrypted, versioned and private; data buckets use KMS', (name) => {
  const template = Template.fromStack(stacks()[name]);
  for (const [id, bucket] of Object.entries(template.findResources('AWS::S3::Bucket'))) {
    // The portal site bucket holds only the public page, under S3-managed keys.
    const algorithm = id.startsWith('PortalSite') ? 'AES256' : 'aws:kms';
    expect(bucket.Properties.BucketEncryption.ServerSideEncryptionConfiguration[0].ServerSideEncryptionByDefault.SSEAlgorithm).toBe(algorithm);
    expect(bucket.Properties.VersioningConfiguration.Status).toBe('Enabled');
    expect(bucket.Properties.PublicAccessBlockConfiguration).toEqual({
      BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true,
    });
  }
  template.allResourcesProperties('AWS::S3::BucketPolicy', {
    PolicyDocument: { Statement: Match.arrayWith([Match.objectLike({
      Effect: 'Deny', Condition: { Bool: { 'aws:SecureTransport': 'false' } },
    })]) },
  });
});

test.each(['intake', 'ml', 'site'])('no log group in %s outlives its stack or keeps logs forever', (name) => {
  const groups = Template.fromStack(stacks()[name]).findResources('AWS::Logs::LogGroup');
  for (const group of Object.values(groups)) {
    expect(group.DeletionPolicy).toBe('Delete');
    expect(group.Properties.RetentionInDays).toBeGreaterThan(0);
  }
});
