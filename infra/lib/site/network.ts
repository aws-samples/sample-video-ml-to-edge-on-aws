// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cr from 'aws-cdk-lib/custom-resources';
import { Construct } from 'constructs';

// A VPC with isolated subnets only: no internet or NAT gateway. The gateway
// reaches S3 through a gateway endpoint, and Systems Manager and KMS through
// interface endpoints, so it needs no route out of the VPC. Session Manager on
// Amazon Linux 2023 needs ssm and ssmmessages only.
export class SiteNetwork extends Construct {
  readonly vpc: ec2.Vpc;
  readonly s3Endpoint: ec2.GatewayVpcEndpoint;
  // The AWS-managed prefix list of S3 in this Region, for security group rules.
  readonly s3PrefixListId: string;

  constructor(scope: Construct, id: string) {
    super(scope, id);
    this.vpc = new ec2.Vpc(this, 'Vpc', {
      // One instance per site; a second Availability Zone would double the
      // interface endpoint cost without adding availability to it.
      maxAzs: 1,
      natGateways: 0,
      subnetConfiguration: [{ name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 }],
    });
    this.s3Endpoint = this.vpc.addGatewayEndpoint('S3', { service: ec2.GatewayVpcEndpointAwsService.S3 });
    // Looked up at deploy time so the stack stays Region-agnostic.
    const prefixList = new cr.AwsCustomResource(this, 'S3PrefixList', {
      onUpdate: {
        service: 'EC2',
        action: 'describeManagedPrefixLists',
        parameters: { Filters: [{ Name: 'prefix-list-name', Values: [`com.amazonaws.${cdk.Stack.of(this).region}.s3`] }] },
        physicalResourceId: cr.PhysicalResourceId.of('s3-prefix-list'),
        outputPaths: ['PrefixLists.0.PrefixListId'],
      },
      // DescribeManagedPrefixLists has no resource-level permission.
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({ resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE }),
      installLatestAwsSdk: false,
      logGroup: new logs.LogGroup(this, 'S3PrefixListLogs', { retention: logs.RetentionDays.ONE_MONTH, removalPolicy: cdk.RemovalPolicy.DESTROY }),
    });
    this.s3PrefixListId = prefixList.getResponseField('PrefixLists.0.PrefixListId');
    this.vpc.addFlowLog('FlowLog', {
      destination: ec2.FlowLogDestination.toCloudWatchLogs(new logs.LogGroup(this, 'FlowLogs', {
        retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      })),
    });
    for (const [name, service] of Object.entries({
      Ssm: ec2.InterfaceVpcEndpointAwsService.SSM,
      SsmMessages: ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
      Kms: ec2.InterfaceVpcEndpointAwsService.KMS,
    })) {
      this.vpc.addInterfaceEndpoint(name, { service, privateDnsEnabled: true });
    }
  }
}
