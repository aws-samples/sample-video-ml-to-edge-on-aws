// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { Match, Template } from 'aws-cdk-lib/assertions';
import { stacks } from './stacks';

const intake = () => Template.fromStack(stacks().intake);

function logicalId(template: Template, type: string, idPrefix: string): string {
  const id = Object.keys(template.findResources(type)).find((k) => k.startsWith(idPrefix));
  if (!id) throw new Error(`no ${type} ${idPrefix}*`);
  return id;
}

test('intake objects are unreadable until GuardDuty tags them clean, except by the scanner', () => {
  const t = intake();
  const bucket = logicalId(t, 'AWS::S3::Bucket', 'IntakeBucket');
  const scanner = logicalId(t, 'AWS::IAM::Role', 'MalwareScanRole');
  t.hasResourceProperties('AWS::S3::BucketPolicy', {
    Bucket: { Ref: bucket },
    PolicyDocument: { Statement: Match.arrayWith([{
      Sid: 'ReadOnlyAfterCleanScan',
      Effect: 'Deny',
      Principal: { AWS: '*' },
      Action: ['s3:GetObject', 's3:GetObjectVersion'],
      Resource: { 'Fn::Join': ['', [{ 'Fn::GetAtt': [bucket, 'Arn'] }, '/*']] },
      Condition: {
        StringNotEquals: { 's3:ExistingObjectTag/GuardDutyMalwareScanStatus': 'NO_THREATS_FOUND' },
        ArnNotEquals: { 'aws:PrincipalArn': { 'Fn::GetAtt': [scanner, 'Arn'] } },
      },
    }]) },
  });
});

test('GuardDuty malware protection tags every object under intake/', () => {
  const t = intake();
  t.resourceCountIs('AWS::GuardDuty::MalwareProtectionPlan', 1);
  t.hasResourceProperties('AWS::GuardDuty::MalwareProtectionPlan', {
    ProtectedResource: { S3Bucket: { BucketName: { Ref: logicalId(t, 'AWS::S3::Bucket', 'IntakeBucket') }, ObjectPrefixes: ['intake/'] } },
    Actions: { Tagging: { Status: 'ENABLED' } },
    Role: { 'Fn::GetAtt': [logicalId(t, 'AWS::IAM::Role', 'MalwareScanRole'), 'Arn'] },
  });
});

test('validation runs only on a clean scan of the intake bucket and reads only clean objects', () => {
  const t = intake();
  t.hasResourceProperties('AWS::Events::Rule', {
    EventPattern: {
      source: ['aws.guardduty'],
      'detail-type': ['GuardDuty Malware Protection Object Scan Result'],
      detail: Match.objectLike({ scanResultDetails: { scanResultStatus: ['NO_THREATS_FOUND'] } }),
    },
  });
  t.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: { Statement: Match.arrayWith([Match.objectLike({
      Sid: 'ReadScannedClean',
      Condition: { StringEquals: { 's3:ExistingObjectTag/GuardDutyMalwareScanStatus': 'NO_THREATS_FOUND' } },
    })]) },
  });
});

test('contributors cannot sign themselves up and the API requires a JWT', () => {
  const t = intake();
  t.hasResourceProperties('AWS::Cognito::UserPool', { AdminCreateUserConfig: { AllowAdminCreateUserOnly: true } });
  t.allResourcesProperties('AWS::ApiGatewayV2::Route', { AuthorizationType: 'JWT' });
  t.resourceCountIs('AWS::Cognito::UserPoolGroup', 2);
});

test('portal sends a strict CSP and reaches the site bucket through OAC only', () => {
  const t = intake();
  t.hasResourceProperties('AWS::CloudFront::ResponseHeadersPolicy', {
    ResponseHeadersPolicyConfig: { SecurityHeadersConfig: Match.objectLike({
      ContentSecurityPolicy: { Override: true, ContentSecurityPolicy: Match.objectLike({ 'Fn::Join': Match.anyValue() }) },
    }) },
  });
  const csp = JSON.stringify(Object.values(t.findResources('AWS::CloudFront::ResponseHeadersPolicy'))[0]);
  expect(csp).toContain("default-src 'none'");
  expect(csp).not.toContain('unsafe-inline');
  t.resourceCountIs('AWS::CloudFront::OriginAccessControl', 1);
});

test('every bucket key rotates and keeps the default account-root key policy only', () => {
  const t = intake();
  for (const key of Object.values(t.findResources('AWS::KMS::Key'))) {
    expect(key.Properties.EnableKeyRotation).toBe(true);
    expect(key.Properties.KeyPolicy.Statement).toHaveLength(1);
  }
});

function putResources(t: Template, roleIdPrefix: string): string {
  const policies = Object.values(t.findResources('AWS::IAM::Policy'))
    .filter((p) => JSON.stringify(p.Properties.Roles).includes(roleIdPrefix));
  const statements = policies.flatMap((p) => p.Properties.PolicyDocument.Statement)
    .filter((s: any) => ([] as string[]).concat(s.Action).includes('s3:PutObject'));
  expect(statements).toHaveLength(1);
  return JSON.stringify(statements[0].Resource);
}

test('presign can put only under intake/ and validation only under curated/ and rejected/', () => {
  const t = intake();
  const presign = putResources(t, 'PortalPresignFnServiceRole');
  expect(presign).toContain('"/intake/*"');
  expect(presign.match(/"\/[a-z]+\/\*"/g)).toEqual(['"/intake/*"']);
  const validate = putResources(t, 'ValidationFnServiceRole');
  expect(validate.match(/"\/[a-z]+\/\*"/g)?.sort()).toEqual(['"/curated/*"', '"/rejected/*"']);
  expect(validate).toContain('CuratedBucket');
  expect(validate).not.toContain('IntakeBucket');
});

test('the upload status route needs a JWT and reads only tags of intake objects', () => {
  const t = intake();
  t.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: 'GET /api/uploads', AuthorizationType: 'JWT' });
  const statements = Object.values(t.findResources('AWS::IAM::Policy'))
    .filter((p) => JSON.stringify(p.Properties.Roles).includes('PortalUploadStatusFnServiceRole'))
    .flatMap((p) => p.Properties.PolicyDocument.Statement);
  const intakeObjects = statements.filter((s: any) => JSON.stringify(s.Resource).includes('IntakeBucket') && JSON.stringify(s.Resource).includes('/intake/'));
  expect(intakeObjects.map((s: any) => s.Action)).toEqual(['s3:GetObjectTagging']);
  const actions = statements.flatMap((s: any) => ([] as string[]).concat(s.Action));
  expect(actions.filter((a: string) => a.startsWith('s3:Put') || a.startsWith('s3:Delete'))).toEqual([]);
  expect(JSON.stringify(statements.filter((s: any) => ([] as string[]).concat(s.Action).includes('s3:GetObject')).map((s: any) => s.Resource)))
    .not.toContain('IntakeBucket');
});

test('the upload status route reads the bytes of rejection records only', () => {
  const statements = Object.values(intake().findResources('AWS::IAM::Policy'))
    .filter((p) => JSON.stringify(p.Properties.Roles).includes('PortalUploadStatusFnServiceRole'))
    .flatMap((p) => p.Properties.PolicyDocument.Statement);
  const reads = statements.filter((s: any) => ([] as string[]).concat(s.Action).includes('s3:GetObject'));
  const resources = JSON.stringify(reads.map((s: any) => s.Resource));
  expect(resources.match(/"\/[a-z]+\/\*"/g)).toEqual(['"/rejected/*"']);
});

test('the portal CloudFront names carry the Region, as CloudFront names are global to the account', () => {
  const t = intake();
  for (const [type, config] of [['AWS::CloudFront::OriginAccessControl', 'OriginAccessControlConfig'], ['AWS::CloudFront::ResponseHeadersPolicy', 'ResponseHeadersPolicyConfig']]) {
    const resources = Object.values(t.findResources(type));
    expect(resources).toHaveLength(1);
    expect(JSON.stringify(resources[0].Properties[config].Name)).toContain('AWS::Region');
  }
});

test('browsers revalidate the portal files, so a deploy reaches them at the next load', () => {
  const t = intake();
  t.hasResourceProperties('Custom::CDKBucketDeployment', {
    SystemMetadata: { 'cache-control': 'no-cache' },
    DistributionPaths: ['/*'],
  });
});
