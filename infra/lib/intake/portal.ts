// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpJwtAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';
import { EncryptedBucket } from '../encrypted-bucket';
import { UploadStatus } from './upload-status';
import { LABELS, PREFIX, SITES } from '../config';

const ROOT = path.join(__dirname, '../../..');
const MAX_CLIP_BYTES = 200 * 1024 * 1024;

// Contributor portal: a static site behind CloudFront, Cognito sign-in with one
// group per site, and a JWT-authorized API whose presign function hands out
// single-object PUT URLs into the intake bucket.
export class Portal extends Construct {
  constructor(scope: Construct, id: string, intake: EncryptedBucket, curated: EncryptedBucket) {
    super(scope, id);
    const { region } = cdk.Stack.of(this);

    // Contributors are created by scripts/create_contributor.sh, never by sign-up.
    const userPool = new cognito.UserPool(this, 'UserPool', {
      selfSignUpEnabled: false,
      signInAliases: { username: true },
      passwordPolicy: { minLength: 12 },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    for (const site of SITES) {
      new cognito.CfnUserPoolGroup(this, `Group-${site}`, { userPoolId: userPool.userPoolId, groupName: site });
    }
    const client = userPool.addClient('WebClient', { generateSecret: false, authFlows: { userPassword: true }, disableOAuth: true });

    const presign = new lambda.Function(this, 'PresignFn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.main',
      code: lambda.Code.fromAsset(path.join(ROOT, 'lambdas/presign')),
      timeout: cdk.Duration.seconds(10),
      environment: {
        INTAKE_BUCKET: intake.bucket.bucketName,
        LABELS: LABELS.join(','),
        SITES: SITES.join(','),
        MAX_BYTES: String(MAX_CLIP_BYTES),
      },
      logGroup: new logs.LogGroup(this, 'PresignLogs', { retention: logs.RetentionDays.ONE_MONTH, removalPolicy: cdk.RemovalPolicy.DESTROY }),
    });
    // The presigned PUT runs with this role, so it is the upload's only grant.
    // PutObjectTagging lets the upload carry the signed contributor tag.
    presign.addToRolePolicy(new iam.PolicyStatement({
      actions: ['s3:PutObject', 's3:PutObjectTagging'],
      resources: [intake.bucket.arnForObjects(`${PREFIX.intake}*`)],
    }));
    // An encrypted PUT asks KMS only for a data key.
    intake.key.grant(presign, 'kms:GenerateDataKey');

    const api = new apigwv2.HttpApi(this, 'Api', { createDefaultStage: true });
    const issuer = `https://cognito-idp.${region}.amazonaws.com/${userPool.userPoolId}`;
    const authorizer = new HttpJwtAuthorizer('Jwt', issuer, { jwtAudience: [client.userPoolClientId] });
    api.addRoutes({
      path: '/api/presign',
      methods: [apigwv2.HttpMethod.POST],
      integration: new HttpLambdaIntegration('Presign', presign),
      authorizer,
    });
    api.addRoutes({
      path: '/api/uploads',
      methods: [apigwv2.HttpMethod.GET],
      integration: new HttpLambdaIntegration('UploadStatus', new UploadStatus(this, 'UploadStatus', { intake, curated }).fn),
      authorizer,
    });

    const site = new s3.Bucket(this, 'Site', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    const csp = [
      "default-src 'none'",
      "script-src 'self'",
      "style-src 'self'",
      `connect-src 'self' https://cognito-idp.${region}.amazonaws.com https://${intake.bucket.bucketName}.s3.${region}.amazonaws.com`,
      "img-src 'self'",
      "base-uri 'none'",
      "form-action 'none'",
      "frame-ancestors 'none'",
    ].join('; ');
    // CloudFront names are global to the account, so each Region's deployment gets its own.
    const headers = new cloudfront.ResponseHeadersPolicy(this, 'SecurityHeaders', {
      responseHeadersPolicyName: `${cdk.Stack.of(this).stackName}-portal-headers-${region}`,
      securityHeadersBehavior: {
        contentSecurityPolicy: { contentSecurityPolicy: csp, override: true },
        strictTransportSecurity: { accessControlMaxAge: cdk.Duration.days(365), includeSubdomains: true, override: true },
        contentTypeOptions: { override: true },
        frameOptions: { frameOption: cloudfront.HeadersFrameOption.DENY, override: true },
        referrerPolicy: { referrerPolicy: cloudfront.HeadersReferrerPolicy.NO_REFERRER, override: true },
      },
    });
    const apiDomain = cdk.Fn.select(2, cdk.Fn.split('/', api.apiEndpoint));
    const distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultRootObject: 'index.html',
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(site, {
          originAccessControl: new cloudfront.S3OriginAccessControl(this, 'SiteAccess', {
            originAccessControlName: `${cdk.Stack.of(this).stackName}-portal-${region}`,
          }),
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        responseHeadersPolicy: headers,
      },
      // Same origin as the page, so the API needs no CORS.
      additionalBehaviors: {
        '/api/*': {
          origin: new origins.HttpOrigin(apiDomain),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
          responseHeadersPolicy: headers,
        },
      },
    });

    new s3deploy.BucketDeployment(this, 'Deploy', {
      destinationBucket: site,
      sources: [
        s3deploy.Source.asset(path.join(ROOT, 'web')),
        // One tokens.css for both user interfaces; the gateway bundle copies the same file.
        s3deploy.Source.asset(path.join(ROOT, 'shared/ui')),
        s3deploy.Source.jsonData('config.json', { region, userPoolClientId: client.userPoolClientId, labels: LABELS }),
      ],
      distribution: distribution,
      distributionPaths: ['/*'],
      // The file names carry no version, so without this a browser reuses its old
      // copy by heuristic freshness for hours after a deploy.
      cacheControl: [s3deploy.CacheControl.noCache()],
      logGroup: new logs.LogGroup(this, 'DeployLogs', { retention: logs.RetentionDays.ONE_MONTH, removalPolicy: cdk.RemovalPolicy.DESTROY }),
    });

    new cdk.CfnOutput(scope, 'PortalUrl', { value: `https://${distribution.distributionDomainName}` });
    new cdk.CfnOutput(scope, 'UserPoolId', { value: userPool.userPoolId });
    new cdk.CfnOutput(scope, 'UserPoolClientId', { value: client.userPoolClientId });
  }
}
