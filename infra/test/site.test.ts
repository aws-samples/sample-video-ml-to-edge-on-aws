// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { Match, Template } from 'aws-cdk-lib/assertions';
import { stacks } from './stacks';

const site = () => Template.fromStack(stacks().site);

test('gateway security group has no ingress rule', () => {
  const t = site();
  const id = Object.keys(t.findResources('AWS::EC2::SecurityGroup')).find((k) => k.startsWith('GatewaySg'))!;
  expect(t.findResources('AWS::EC2::SecurityGroup')[id].Properties.SecurityGroupIngress).toBeUndefined();
  const ingress = Object.values(t.findResources('AWS::EC2::SecurityGroupIngress'));
  expect(ingress.filter((r) => JSON.stringify(r.Properties.GroupId).includes(id))).toHaveLength(0);
});

test('the VPC has no route to the internet', () => {
  const t = site();
  t.resourceCountIs('AWS::EC2::InternetGateway', 0);
  t.resourceCountIs('AWS::EC2::NatGateway', 0);
  t.allResourcesProperties('AWS::EC2::Subnet', { MapPublicIpOnLaunch: false });
  t.resourceCountIs('AWS::EC2::VPCEndpoint', 4);
});

test('gateway reads only its own channel and the releases, and pins the public key', () => {
  const doc = JSON.stringify(site().findResources('AWS::IAM::Policy'));
  expect(doc).toContain('/channels/factory-a.json');
  expect(doc).not.toContain('/channels/*');
  expect(doc).not.toContain('factory-b');
  expect(doc).toContain('kms:GetPublicKey');
  expect(doc).not.toMatch(/s3:PutObject|kms:Sign/);
});

test('gateway instance requires IMDSv2 and has an encrypted root volume', () => {
  site().hasResourceProperties('AWS::EC2::LaunchTemplate', {
    LaunchTemplateData: { MetadataOptions: { HttpTokens: 'required' } },
  });
  site().hasResourceProperties('AWS::EC2::Instance', {
    BlockDeviceMappings: [Match.objectLike({ Ebs: Match.objectLike({ Encrypted: true }) })],
  });
});

test('gateway reads only its own bundle object from the CDK asset bucket', () => {
  const statements = Object.values(site().findResources('AWS::IAM::Policy'))
    .flatMap((p) => p.Properties.PolicyDocument.Statement);
  const assets = statements.filter((s: any) => JSON.stringify(s.Resource).includes('cdk-hnb659fds-assets'));
  expect(assets.length).toBeGreaterThan(0);
  for (const s of assets) {
    expect(s.Action).toBe('s3:GetObject');
    const resources = JSON.stringify(s.Resource);
    expect(resources).not.toMatch(/assets-\$\{AWS::AccountId\}-\$\{AWS::Region\}"\]\]\}(,|\])/);
    expect(resources).not.toContain('/*"');
    expect(resources).toMatch(/\.zip/);
  }
});

test('gateway egress reaches only the endpoints, on 443', () => {
  const t = site();
  const id = Object.keys(t.findResources('AWS::EC2::SecurityGroup')).find((k) => k.startsWith('GatewaySg'))!;
  const inline = t.findResources('AWS::EC2::SecurityGroup')[id].Properties.SecurityGroupEgress;
  const separate = Object.values(t.findResources('AWS::EC2::SecurityGroupEgress'))
    .filter((r) => JSON.stringify(r.Properties.GroupId).includes(id)).map((r) => r.Properties);
  const egress = [...inline, ...separate];
  expect(egress).toHaveLength(2);
  for (const rule of egress) {
    expect([rule.FromPort, rule.ToPort, rule.IpProtocol]).toEqual([443, 443, 'tcp']);
    expect(rule.CidrIp).not.toBe('0.0.0.0/0');
  }
  expect(egress.some((r: any) => r.DestinationPrefixListId)).toBe(true);
});

test('the S3 endpoint policy allows only reads of the release and bundle objects and the AL2023 repositories', () => {
  const endpoints = Object.values(site().findResources('AWS::EC2::VPCEndpoint'))
    .filter((e) => JSON.stringify(e.Properties.ServiceName).includes('.s3'));
  expect(endpoints).toHaveLength(1);
  const statements = endpoints[0].Properties.PolicyDocument.Statement;
  expect(statements.map((s: any) => s.Action).sort()).toEqual(['s3:GetObject', 's3:ListBucket']);
  const reads = statements.find((s: any) => s.Action === 's3:GetObject').Resource;
  expect(reads).toHaveLength(4);
  const repos = reads.filter((r: any) => JSON.stringify(r).includes('al2023-repos-'));
  expect(repos).toEqual([{
    'Fn::Join': ['', ['arn:', { Ref: 'AWS::Partition' }, ':s3:::al2023-repos-', { Ref: 'AWS::Region' }, '-de612dc2/*']],
  }]);
  for (const s of statements) expect(JSON.stringify(s.Resource)).not.toMatch(/"\*"/);
  const list = statements.find((s: any) => s.Action === 's3:ListBucket');
  expect(list.Condition).toEqual({ StringEquals: { 's3:prefix': 'channels/factory-a.json' } });
});

test('gateway role has no managed policy and only the SSM Agent actions it needs', () => {
  const t = site();
  const roles = Object.entries(t.findResources('AWS::IAM::Role')).filter(([id]) => id.startsWith('GatewayRole'));
  expect(roles).toHaveLength(1);
  expect(roles[0][1].Properties.ManagedPolicyArns).toBeUndefined();
  const actions = Object.values(t.findResources('AWS::IAM::Policy'))
    .filter((p) => JSON.stringify(p.Properties.Roles).includes(roles[0][0]))
    .flatMap((p) => p.Properties.PolicyDocument.Statement)
    .flatMap((s: any) => ([] as string[]).concat(s.Action));
  expect(actions.filter((a) => /^(ssm|ssmmessages|ec2messages):/.test(a)).sort()).toEqual([
    'ssm:UpdateInstanceInformation',
    'ssmmessages:CreateControlChannel',
    'ssmmessages:CreateDataChannel',
    'ssmmessages:OpenControlChannel',
    'ssmmessages:OpenDataChannel',
  ]);
});

test('gateway user data installs and runs Python 3.12', () => {
  const instances = Object.values(site().findResources('AWS::EC2::Instance'));
  expect(instances).toHaveLength(1);
  const userData = JSON.stringify(instances[0].Properties.UserData);
  expect(userData).toContain('dnf install -y python3.12');
  expect(userData).toContain('python3.12 -m zipfile');
  expect(userData).not.toMatch(/python3 /);
});
