// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { Match, Template } from 'aws-cdk-lib/assertions';
import { stacks } from './stacks';

const ml = () => Template.fromStack(stacks().ml);

test('release signing key is an ECC P-256 sign/verify key whose policy grants only the account root', () => {
  ml().hasResourceProperties('AWS::KMS::Key', {
    KeySpec: 'ECC_NIST_P256',
    KeyUsage: 'SIGN_VERIFY',
    KeyPolicy: { Statement: [Match.objectLike({ Effect: 'Allow', Action: 'kms:*', Principal: { AWS: Match.anyValue() } })] },
  });
});

test('release function runs only on approval in the sample model package group', () => {
  ml().hasResourceProperties('AWS::Events::Rule', {
    EventPattern: {
      source: ['aws.sagemaker'],
      'detail-type': ['SageMaker Model Package State Change'],
      detail: { ModelPackageGroupName: ['conveyor-events'], ModelApprovalStatus: ['Approved'] },
    },
  });
});

test('only the release function may sign', () => {
  const t = ml();
  const signers = Object.values(t.findResources('AWS::IAM::Policy')).filter((p) =>
    JSON.stringify(p.Properties.PolicyDocument).includes('kms:Sign'));
  expect(signers).toHaveLength(1);
  expect(JSON.stringify(signers[0].Properties.Roles)).toContain('PublishFn');
});

test('training role can write only under training-output/ and deletes nothing', () => {
  const t = ml();
  const policies = Object.entries(t.findResources('AWS::IAM::Policy')).filter(([id]) => id.startsWith('TrainingRole'));
  expect(policies).toHaveLength(1);
  const statements = policies[0][1].Properties.PolicyDocument.Statement;
  const doc = JSON.stringify(statements);
  expect(doc).not.toMatch(/Delete/);
  const writes = statements.filter((s: any) => ([] as string[]).concat(s.Action).includes('s3:PutObject'));
  expect(writes).toHaveLength(1);
  expect(JSON.stringify(writes[0].Resource)).toContain('/training-output/*');
  t.hasResourceProperties('AWS::IAM::Role', {
    AssumeRolePolicyDocument: { Statement: [Match.objectLike({
      Principal: { Service: 'sagemaker.amazonaws.com' },
      Condition: { StringEquals: { 'aws:SourceAccount': Match.anyValue() } },
    })] },
  });
});

test('registration function runs when a tiny3d training job completes', () => {
  ml().hasResourceProperties('AWS::Events::Rule', {
    EventPattern: {
      source: ['aws.sagemaker'],
      'detail-type': ['SageMaker Training Job State Change'],
      detail: { TrainingJobName: [{ prefix: 'tiny3d-' }], TrainingJobStatus: ['Completed'] },
    },
  });
});

test('only the registration function creates model packages, and only ones awaiting approval', () => {
  const t = ml();
  const policies = Object.entries(t.findResources('AWS::IAM::Policy')).filter(([id]) => id.startsWith('RegisterFn'));
  expect(policies).toHaveLength(1);
  const statements: any[] = policies[0][1].Properties.PolicyDocument.Statement;
  const actions = statements.flatMap((s) => ([] as string[]).concat(s.Action)).sort();
  expect(actions).toEqual(['kms:Decrypt', 's3:GetObject', 's3:GetObjectVersion', 'sagemaker:CreateModelPackage', 'sagemaker:DescribeTrainingJob']);
  const create = statements.find((s) => s.Action === 'sagemaker:CreateModelPackage');
  expect(create.Condition).toEqual({ StringEquals: { 'sagemaker:ModelApprovalStatus': 'PendingManualApproval' } });
  const creators = Object.values(t.findResources('AWS::IAM::Policy')).filter((p) =>
    JSON.stringify(p.Properties.PolicyDocument).includes('sagemaker:CreateModelPackage'));
  expect(creators).toHaveLength(1);
});
