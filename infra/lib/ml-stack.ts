// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as cdk from 'aws-cdk-lib';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';
import { Construct } from 'constructs';
import { EncryptedBucket } from './encrypted-bucket';
import { Register } from './ml/register';
import { Release } from './ml/release';
import { DLC_REGISTRY, TrainingRole } from './ml/training-role';
import { MODEL_PACKAGE_GROUP } from './config';

export interface MlStackProps extends cdk.StackProps {
  curated: EncryptedBucket;
}

// Dataset snapshots, training, the model registry with its registration function,
// and signed releases.
export class MlStack extends cdk.Stack {
  readonly release: EncryptedBucket;
  readonly signingKey: kms.Key;

  constructor(scope: Construct, id: string, props: MlStackProps) {
    super(scope, id, props);
    const ml = new EncryptedBucket(this, 'Ml');
    this.release = new EncryptedBucket(this, 'Release');
    const training = new TrainingRole(this, 'Training', { curated: props.curated, ml });

    const group = new sagemaker.CfnModelPackageGroup(this, 'Registry', {
      modelPackageGroupName: MODEL_PACKAGE_GROUP,
      modelPackageGroupDescription: 'tiny3d conveyor event classifiers',
    });
    group.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);
    new Register(this, 'Register', { ml, trainingRole: training.role });
    this.signingKey = new Release(this, 'Publish', { ml, release: this.release }).signingKey;

    new cdk.CfnOutput(this, 'MlBucket', { value: ml.bucket.bucketName });
    new cdk.CfnOutput(this, 'MlBucketKeyArn', { value: ml.key.keyArn });
    new cdk.CfnOutput(this, 'TrainingRoleArn', { value: training.role.roleArn });
    // The training scripts pull the SageMaker images from the registry the role may read.
    new cdk.CfnOutput(this, 'DlcRegistry', { value: DLC_REGISTRY });
    new cdk.CfnOutput(this, 'ModelPackageGroup', { value: MODEL_PACKAGE_GROUP });
  }
}
