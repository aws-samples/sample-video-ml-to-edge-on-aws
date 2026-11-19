// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { EncryptedBucket } from '../encrypted-bucket';
import { MODEL_PACKAGE_GROUP, PREFIX, TRAINING_JOB_PREFIX } from '../config';
import { DLC_REGISTRY } from './training-role';

// The image a model package names for its artefact; the sample never deploys it.
const INFERENCE_IMAGE = 'pytorch-inference:2.6.0-cpu-py312';

export interface RegisterProps {
  ml: EncryptedBucket;
  trainingRole: iam.IRole;
}

// Registers every completed training job of the sample in the model registry as
// PendingManualApproval, in the cloud, so registration does not depend on the
// operator's machine staying up while the job runs.
export class Register extends Construct {
  constructor(scope: Construct, id: string, props: RegisterProps) {
    super(scope, id);
    const { region, account } = cdk.Stack.of(this);
    const { ml, trainingRole } = props;

    const fn = new lambda.Function(this, 'Fn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.main',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../../lambdas/register')),
      memorySize: 512,
      timeout: cdk.Duration.minutes(2),
      environment: {
        MODEL_PACKAGE_GROUP,
        TRAINING_ROLE_ARN: trainingRole.roleArn,
        INFERENCE_IMAGE: `${DLC_REGISTRY}.dkr.ecr.${region}.amazonaws.com/${INFERENCE_IMAGE}`,
      },
      logGroup: new logs.LogGroup(this, 'Logs', { retention: logs.RetentionDays.ONE_MONTH, removalPolicy: cdk.RemovalPolicy.DESTROY }),
    });
    fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'DescribeTrainingJobs',
      actions: ['sagemaker:DescribeTrainingJob'],
      resources: [`arn:aws:sagemaker:${region}:${account}:training-job/${TRAINING_JOB_PREFIX}*`],
    }));
    // The function can only register packages that still await a person's approval.
    fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'RegisterPendingPackages',
      actions: ['sagemaker:CreateModelPackage'],
      resources: [
        `arn:aws:sagemaker:${region}:${account}:model-package-group/${MODEL_PACKAGE_GROUP}`,
        `arn:aws:sagemaker:${region}:${account}:model-package/${MODEL_PACKAGE_GROUP}/*`,
      ],
      conditions: { StringEquals: { 'sagemaker:ModelApprovalStatus': 'PendingManualApproval' } },
    }));
    fn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'ReadTrainingOutput',
      actions: ['s3:GetObject', 's3:GetObjectVersion'],
      resources: [ml.bucket.arnForObjects(`${PREFIX.trainingOutput}*`)],
    }));
    ml.key.grantDecrypt(fn);

    new events.Rule(this, 'OnTrainingCompleted', {
      description: 'A training job of the sample completed',
      eventPattern: {
        source: ['aws.sagemaker'],
        detailType: ['SageMaker Training Job State Change'],
        detail: { TrainingJobName: events.Match.prefix(TRAINING_JOB_PREFIX), TrainingJobStatus: ['Completed'] },
      },
      targets: [new targets.LambdaFunction(fn, { retryAttempts: 2 })],
    });
  }
}
