// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { Template } from 'aws-cdk-lib/assertions';
import * as execPolicy from '../cfn-exec-policy.json';
import { stacks } from './stacks';

test.each(['intake', 'ml', 'site'])('every role in %s carries the bootstrap permissions boundary', (name) => {
  const roles = Template.fromStack(stacks()[name]).findResources('AWS::IAM::Role');
  expect(Object.keys(roles).length).toBeGreaterThan(0);
  for (const role of Object.values(roles)) {
    expect(JSON.stringify(role.Properties.PermissionsBoundary)).toContain(':policy/ConveyorSampleBoundary');
  }
});

test('the CloudFormation execution policy grants no wildcard action and IAM only on Conveyor* roles', () => {
  for (const statement of execPolicy.Statement) {
    const actions = ([] as string[]).concat(statement.Action);
    expect(actions).not.toContain('*');
    expect(actions.filter((a) => a.startsWith('iam:') && a.includes('*'))).toEqual([]);
    if (['iam:CreateRole', 'iam:PutRolePolicy', 'iam:AttachRolePolicy'].some((a) => actions.includes(a))) {
      expect(JSON.stringify((statement as any).Condition)).toContain(':policy/ConveyorSampleBoundary');
    }
    if (actions.some((a) => a.startsWith('iam:')) && statement.Sid !== 'GuardDutyServiceRole') {
      for (const resource of ([] as string[]).concat(statement.Resource)) {
        expect(resource).toMatch(/:(role|instance-profile)\/Conveyor\*$/);
      }
    }
  }
});

test('the boundary grants no IAM action', () => {
  const boundary = require('../permissions-boundary.json');
  const actions = boundary.Statement.flatMap((s: any) => ([] as string[]).concat(s.Action));
  expect(actions.filter((a: string) => a.startsWith('iam:') || a === '*')).toEqual([]);
});

test.each(['cfn-exec-policy', 'cfn-exec-policy-compute', 'permissions-boundary', 'operator-policy'])(
  '%s grants no service-wide action and uses "*" only for actions without resource-level permissions', (file) => {
    const policy = require(`../${file}.json`);
    for (const statement of policy.Statement) {
      const actions = ([] as string[]).concat(statement.Action);
      expect(actions.filter((a) => a === '*' || a.endsWith(':*'))).toEqual([]);
      if (([] as string[]).concat(statement.Resource).includes('*')) {
        expect(statement.Sid.startsWith('NoResourceLevel') || statement.Condition !== undefined).toBe(true);
      }
    }
  });

test('the operator policy writes no IAM and assumes only the CDK deploy and file-publishing roles', () => {
  const operator = require('../operator-policy.json');
  const actions: string[] = operator.Statement.flatMap((s: any) => ([] as string[]).concat(s.Action));
  expect(actions.filter((a) => a.startsWith('iam:'))).toEqual(['iam:PassRole']);
  expect(actions.filter((a) => /^cloudformation:(Create|Update|Delete|Execute)/.test(a))).toEqual([]);
  const assume = operator.Statement.filter((s: any) => ([] as string[]).concat(s.Action).includes('sts:AssumeRole'));
  expect(assume.flatMap((s: any) => s.Resource).sort()).toEqual([
    'arn:aws:iam::${aws:PrincipalAccount}:role/cdk-hnb659fds-deploy-role-${aws:PrincipalAccount}-*',
    'arn:aws:iam::${aws:PrincipalAccount}:role/cdk-hnb659fds-file-publishing-role-${aws:PrincipalAccount}-*',
  ]);
});

// The bucket names are wildcards, so a same-named bucket in another account would match.
test.each(['operator-policy', 'permissions-boundary'])('every S3 grant to the sample buckets in %s stays in the account', (file) => {
  const policy = require(`../${file}.json`);
  const s3 = policy.Statement.filter((s: any) => ([] as string[]).concat(s.Resource).some((r) => /^arn:aws:s3:::conveyor/.test(r)));
  expect(s3.length).toBeGreaterThan(0);
  for (const statement of s3) {
    expect(statement.Condition.StringEquals['s3:ResourceAccount']).toBe('${aws:PrincipalAccount}');
  }
});

test('the boundary lets only the release function sign', () => {
  const boundary = require('../permissions-boundary.json');
  const signers = boundary.Statement.filter((s: any) => ([] as string[]).concat(s.Action).includes('kms:Sign'));
  expect(signers).toHaveLength(1);
  const pattern: string = signers[0].Condition.ArnLike['aws:PrincipalArn'];
  // CloudFormation names a role <stack>-<logical id>-<suffix>.
  const roles = Object.keys(Template.fromStack(stacks().ml).findResources('AWS::IAM::Role'));
  const named = roles.filter((id) => `arn:aws:iam::\${aws:PrincipalAccount}:role/ConveyorMl-${id}`.startsWith(pattern.slice(0, -1)));
  expect(named).toHaveLength(1);
  expect(named[0]).toMatch(/^PublishFnServiceRole/);
});

test('the boundary grants the SSM Agent its session channels and registration, and no parameter', () => {
  const boundary = require('../permissions-boundary.json');
  const statements = boundary.Statement.filter((s: any) => ([] as string[]).concat(s.Action).some((a) => /^(ssm|ssmmessages|ec2messages):/.test(a)));
  expect(statements.flatMap((s: any) => s.Action).sort()).toEqual([
    'ssm:UpdateInstanceInformation',
    'ssmmessages:CreateControlChannel',
    'ssmmessages:CreateDataChannel',
    'ssmmessages:OpenControlChannel',
    'ssmmessages:OpenDataChannel',
  ]);
  expect(JSON.stringify(boundary)).not.toContain(':parameter/');
});

test.each(['cfn-exec-policy', 'cfn-exec-policy-compute', 'permissions-boundary', 'operator-policy'])(
  'no wildcard action in %s', (file) => {
    const policy = require(`../${file}.json`);
    const actions: string[] = policy.Statement.flatMap((s: any) => ([] as string[]).concat(s.Action));
    expect(actions.filter((a) => a.includes('*'))).toEqual([]);
  });

// A role is denied at run time any action its policy grants that the boundary does not list.
test.each(['intake', 'ml', 'site'])('the boundary lists every action the role policies in %s grant', (name) => {
  const boundary = require('../permissions-boundary.json');
  const allowed = new Set(boundary.Statement.flatMap((s: any) => ([] as string[]).concat(s.Action)));
  const missing = Object.entries(Template.fromStack(stacks()[name]).findResources('AWS::IAM::Policy'))
    .filter(([id]) => !id.startsWith('CustomCDKBucketDeployment'))
    .flatMap(([, p]) => p.Properties.PolicyDocument.Statement.flatMap((s: any) => ([] as string[]).concat(s.Action)))
    .filter((a: string) => !allowed.has(a));
  expect([...new Set(missing)]).toEqual([]);
});

// The BucketDeployment construct writes its own grants; the boundary's explicit
// actions are what that role can use.
test.each(['intake', 'ml', 'site'])('no wildcard action in the role policies %s writes', (name) => {
  const t = Template.fromStack(stacks()[name]);
  const wildcards = Object.entries(t.findResources('AWS::IAM::Policy'))
    .filter(([id]) => !id.startsWith('CustomCDKBucketDeployment'))
    .flatMap(([id, p]) => p.Properties.PolicyDocument.Statement
      .flatMap((s: any) => ([] as string[]).concat(s.Action))
      .filter((a: string) => a.includes('*'))
      .map((a: string) => `${id} ${a}`));
  expect(wildcards).toEqual([]);
});

// IAM counts a managed policy without whitespace, after bootstrap.sh writes in the account id.
test.each(['cfn-exec-policy', 'cfn-exec-policy-compute', 'permissions-boundary'])('%s fits the managed policy size limit', (file) => {
  const policy = require(`../${file}.json`);
  expect(JSON.stringify(policy).replace(/\$\{aws:PrincipalAccount\}/g, '123456789012').length).toBeLessThanOrEqual(6144);
});

test('the execution policy can tag the HTTP API stage, which its CloudFormation handler does on create', () => {
  const statement = execPolicy.Statement.find((s) => s.Sid === 'ApiGateway')!;
  expect(statement.Action).toEqual(expect.arrayContaining(['apigateway:TagResource', 'apigateway:UntagResource']));
  expect(statement.Resource).toContain('arn:aws:apigateway:*::/apis/*');
});

// A function's last log lines can arrive after CloudFormation deleted its log group;
// without CreateLogGroup there, Lambda cannot recreate the group outside the stack.
test('the boundary lets no role create the log groups the stacks declare', () => {
  const boundary = require('../permissions-boundary.json');
  const creates = boundary.Statement.filter((s: any) => ([] as string[]).concat(s.Action).includes('logs:CreateLogGroup'));
  for (const s of creates) {
    expect(([] as string[]).concat(s.Resource)).not.toContain('arn:aws:logs:*:${aws:PrincipalAccount}:log-group:Conveyor*');
  }
});
