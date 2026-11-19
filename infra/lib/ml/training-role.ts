// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { EncryptedBucket } from '../encrypted-bucket';
import { PREFIX } from '../config';

// Account that hosts the AWS Deep Learning Containers images in most Regions.
export const DLC_REGISTRY = '763104351884';
// SageMaker's log group and metric namespace for training jobs.
const TRAINING_JOBS = '/aws/sagemaker/TrainingJobs';

export interface TrainingRoleProps {
  curated: EncryptedBucket;
  ml: EncryptedBucket;
}

// Execution role for SageMaker training jobs. The job runs code and pip installs,
// so the role reads only its inputs and adds objects only under training-output/:
// it cannot change code, snapshots or curated clips, or delete anything.
export class TrainingRole extends Construct {
  readonly role: iam.Role;

  constructor(scope: Construct, id: string, props: TrainingRoleProps) {
    super(scope, id);
    const { region, account } = cdk.Stack.of(this);
    const { curated, ml } = props;

    this.role = new iam.Role(this, 'Role', {
      assumedBy: new iam.ServicePrincipal('sagemaker.amazonaws.com', {
        conditions: { StringEquals: { 'aws:SourceAccount': account } },
      }),
    });
    this.role.addToPolicy(new iam.PolicyStatement({
      sid: 'ReadInputs',
      actions: ['s3:GetObject'],
      resources: [
        curated.bucket.arnForObjects(`${PREFIX.curated}*`),
        ml.bucket.arnForObjects(`${PREFIX.code}*`),
        ml.bucket.arnForObjects(`${PREFIX.manifests}*`),
      ],
    }));
    // The manifest channel is an S3Prefix data source, which SageMaker lists.
    this.role.addToPolicy(new iam.PolicyStatement({
      sid: 'ListManifests',
      actions: ['s3:ListBucket'],
      resources: [ml.bucket.bucketArn],
      conditions: { StringLike: { 's3:prefix': `${PREFIX.manifests}*` } },
    }));
    this.role.addToPolicy(new iam.PolicyStatement({
      sid: 'WriteTrainingOutput',
      actions: ['s3:PutObject', 's3:AbortMultipartUpload'],
      resources: [ml.bucket.arnForObjects(`${PREFIX.trainingOutput}*`)],
    }));
    this.role.addToPolicy(new iam.PolicyStatement({
      sid: 'DecryptInputs',
      actions: ['kms:Decrypt'],
      resources: [curated.key.keyArn, ml.key.keyArn],
      conditions: { StringLike: { 'kms:ViaService': `s3.${region}.amazonaws.com` } },
    }));
    this.role.addToPolicy(new iam.PolicyStatement({
      sid: 'EncryptOutput',
      actions: ['kms:GenerateDataKey', 'kms:Encrypt'],
      resources: [ml.key.keyArn],
      conditions: { StringLike: { 'kms:ViaService': `s3.${region}.amazonaws.com` } },
    }));

    const logGroup = `arn:aws:logs:${region}:${account}:log-group:${TRAINING_JOBS}`;
    this.role.addToPolicy(new iam.PolicyStatement({
      sid: 'TrainingJobLogs',
      actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogStreams'],
      resources: [logGroup, `${logGroup}:*`],
    }));
    this.role.addToPolicy(new iam.PolicyStatement({
      sid: 'PullTrainingImage',
      actions: ['ecr:BatchCheckLayerAvailability', 'ecr:GetDownloadUrlForLayer', 'ecr:BatchGetImage'],
      resources: [`arn:aws:ecr:${region}:${DLC_REGISTRY}:repository/pytorch-training`],
    }));
    // GetAuthorizationToken and PutMetricData take no resource ARN; the metric
    // write is held to SageMaker's namespace by condition instead.
    this.role.addToPolicy(new iam.PolicyStatement({ sid: 'EcrToken', actions: ['ecr:GetAuthorizationToken'], resources: ['*'] }));
    this.role.addToPolicy(new iam.PolicyStatement({
      sid: 'TrainingMetrics',
      actions: ['cloudwatch:PutMetricData'],
      resources: ['*'],
      conditions: { StringEquals: { 'cloudwatch:namespace': TRAINING_JOBS } },
    }));
  }
}
