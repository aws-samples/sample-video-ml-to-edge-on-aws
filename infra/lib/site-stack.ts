// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as s3assets from 'aws-cdk-lib/aws-s3-assets';
import { Construct } from 'constructs';
import { EncryptedBucket } from './encrypted-bucket';
import { SiteNetwork } from './site/network';
import { PREFIX } from './config';

const ROOT = path.join(__dirname, '../..');

export interface SiteStackProps extends cdk.StackProps {
  site: string;
  release: EncryptedBucket;
  signingKey: kms.IKey;
}

// The edge gateway of one site, simulated by an EC2 instance with no inbound
// rule and no public address. It pulls its own release channel, verifies each
// release before installing it, and serves a local UI on 127.0.0.1:8080 that
// operators reach through Session Manager port forwarding.
export class SiteStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: SiteStackProps) {
    super(scope, id, props);
    const { site, release, signingKey } = props;
    const network = new SiteNetwork(this, 'Network');
    const { vpc } = network;

    const role = new iam.Role(this, 'GatewayRole', { assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com') });
    // What the SSM Agent needs to register and to carry Run Command and Session
    // Manager over ssmmessages; AmazonSSMManagedInstanceCore would also let the
    // gateway read every parameter in the account.
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'RegisterWithSystemsManager',
      actions: ['ssm:UpdateInstanceInformation'],
      resources: [`arn:aws:ec2:${this.region}:${this.account}:instance/*`],
    }));
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'SessionChannels',
      // ssmmessages has no resource-level permission.
      actions: ['ssmmessages:CreateControlChannel', 'ssmmessages:CreateDataChannel', 'ssmmessages:OpenControlChannel', 'ssmmessages:OpenDataChannel'],
      resources: ['*'],
    }));
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'ReadOwnChannelAndReleases',
      actions: ['s3:GetObject'],
      resources: [release.bucket.arnForObjects(`${PREFIX.channels}${site}.json`), release.bucket.arnForObjects(`${PREFIX.releases}*`)],
    }));
    // Lets a missing channel answer 404, which the fetch reads as "nothing approved yet".
    const ownChannel = new iam.PolicyStatement({
      sid: 'ListOwnChannel',
      actions: ['s3:ListBucket'],
      resources: [release.bucket.bucketArn],
      conditions: { StringEquals: { 's3:prefix': `${PREFIX.channels}${site}.json` } },
    });
    role.addToPolicy(ownChannel);
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'DecryptReleases',
      actions: ['kms:Decrypt'],
      resources: [release.key.keyArn],
      conditions: { StringLike: { 'kms:ViaService': `s3.${this.region}.amazonaws.com` } },
    }));
    role.addToPolicy(new iam.PolicyStatement({ sid: 'PinPublicKey', actions: ['kms:GetPublicKey'], resources: [signingKey.keyArn] }));

    // The site bundle with the shared tokens.css and the validation probe copied
    // in, so the gateway uses the same styles and the same clip checks as the cloud.
    const siteDir = path.join(ROOT, 'site');
    const bundle = new s3assets.Asset(this, 'Bundle', {
      path: siteDir,
      assetHashType: cdk.AssetHashType.OUTPUT,
      bundling: {
        image: cdk.DockerImage.fromRegistry('public.ecr.aws/docker/library/alpine:3'),
        local: {
          tryBundle(outputDir: string) {
            fs.cpSync(siteDir, outputDir, { recursive: true });
            fs.copyFileSync(path.join(ROOT, 'shared/ui/tokens.css'), path.join(outputDir, 'gateway/static/tokens.css'));
            fs.copyFileSync(path.join(ROOT, 'lambdas/validate/probe.py'), path.join(outputDir, 'gateway/probe.py'));
            return true;
          },
        },
      },
    });
    // Only this object: the asset bucket holds every CDK asset in the account.
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'ReadOwnBundle',
      actions: ['s3:GetObject'],
      resources: [bundle.bucket.arnForObjects(bundle.s3ObjectKey)],
    }));

    const userData = ec2.UserData.forLinux();
    const src = '/opt/conveyor-src';
    const zip = userData.addS3DownloadCommand({ bucket: bundle.bucket, bucketKey: bundle.s3ObjectKey, localFile: '/tmp/site.zip' });
    userData.addCommands('dnf install -y python3.12', `python3.12 -m zipfile -e ${zip} ${src}`);
    userData.addCommands(`bash ${src}/install.sh ${src} ${site} ${release.bucket.bucketName} ${signingKey.keyArn} ${this.region}`);

    const securityGroup = new ec2.SecurityGroup(this, 'GatewaySg', {
      vpc,
      description: 'Site gateway: no inbound rules; outbound only reaches the VPC endpoints',
      allowAllOutbound: false,
    });
    securityGroup.addEgressRule(ec2.Peer.ipv4(vpc.vpcCidrBlock), ec2.Port.tcp(443), 'Interface endpoints');
    securityGroup.addEgressRule(ec2.Peer.prefixList(network.s3PrefixListId), ec2.Port.tcp(443), 'S3 gateway endpoint');
    // Through the S3 endpoint the VPC reaches only what the gateway reads.
    network.s3Endpoint.addToPolicy(new iam.PolicyStatement({
      principals: [new iam.AnyPrincipal()],
      actions: ['s3:ListBucket'],
      resources: [release.bucket.bucketArn],
      conditions: { StringEquals: { 's3:prefix': `${PREFIX.channels}${site}.json` } },
    }));
    network.s3Endpoint.addToPolicy(new iam.PolicyStatement({
      principals: [new iam.AnyPrincipal()],
      actions: ['s3:GetObject'],
      resources: [
        release.bucket.arnForObjects(`${PREFIX.channels}${site}.json`),
        release.bucket.arnForObjects(`${PREFIX.releases}*`),
        bundle.bucket.arnForObjects(bundle.s3ObjectKey),
      ],
    }));
    // AL2023 package repositories, read-only, AWS-owned: dnf installs python3.12 from them.
    network.s3Endpoint.addToPolicy(new iam.PolicyStatement({
      principals: [new iam.AnyPrincipal()],
      actions: ['s3:GetObject'],
      resources: [`arn:${this.partition}:s3:::al2023-repos-${this.region}-de612dc2/*`],
    }));
    const instance = new ec2.Instance(this, 'Gateway', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.SMALL),
      machineImage: ec2.MachineImage.latestAmazonLinux2023({ cpuType: ec2.AmazonLinuxCpuType.ARM_64 }),
      securityGroup: securityGroup,
      role,
      userData,
      // The gateway installs its code on first boot only, so new code means a new instance.
      userDataCausesReplacement: true,
      requireImdsv2: true,
      associatePublicIpAddress: false,
      blockDevices: [{ deviceName: '/dev/xvda', volume: ec2.BlockDeviceVolume.ebs(16, { encrypted: true }) }],
    });
    // Install only once the endpoints exist, or the first boot cannot reach S3 and KMS.
    instance.node.addDependency(vpc);

    new cdk.CfnOutput(this, 'InstanceId', { value: instance.instanceId });
    new cdk.CfnOutput(this, 'OpenUi', {
      value: `aws ssm start-session --target ${instance.instanceId} --document-name AWS-StartPortForwardingSession --parameters portNumber=8080,localPortNumber=8080`,
    });
  }
}
