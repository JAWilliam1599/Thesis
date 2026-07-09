"""Hybrid web-app demo — the AWS side of a website whose database lives on-prem.

Topology (Option A, production-realistic connectivity):

    Browser
      |  HTTPS
      v
    CloudFront ──> S3 (static frontend, private via OAC)
      |
      |  /api/*  (fetch)
      v
    API Gateway ──> Lambda (inside VPC private-isolated subnets)
                      |  reads DB creds from Secrets Manager (VPC endpoint, no NAT)
                      |  psycopg2 -> TCP 5432
                      v
    Tailscale subnet-router EC2 (VPC) ──Tailscale mesh──> On-prem PostgreSQL

The database is intentionally NOT on AWS: it is provisioned on-prem by the
Ansible half of this demo, and reached over a Tailscale subnet route.

This stack is deliberately *mostly* hardened — a few best-practice gaps
(e.g. no WAF / no access logging on CloudFront) are left in on purpose so the
security gate and risk-scoring engine have real findings to report.

Docker-free: the psycopg2 dependency ships as a plain-asset Lambda layer
(populate ``layers/psycopg2/python`` with ``pip install``), so ``cdk synth``
never needs Docker.

Context inputs (override with ``-c key=value``):
  - onprem_db_cidr   CIDR of the on-prem subnet routed over Tailscale (default 192.168.64.0/24)
  - onprem_db_host   Tailscale IP / hostname of the PostgreSQL server (default 100.64.0.10)
  - db_name          Database name Lambda connects to (default guestbook)
  - db_user          Database user Lambda connects as (default appuser)
  - tailscale_instance_type  EC2 size for the subnet router (default t3.micro)
"""
import json
import os

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_apigateway as apigw,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

HERE = os.path.dirname(os.path.abspath(__file__))


class HybridWebappStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Context parameters (with safe defaults) ---
        onprem_db_cidr = self.node.try_get_context("onprem_db_cidr") or "192.168.64.0/24"
        onprem_db_host = self.node.try_get_context("onprem_db_host") or "100.64.0.10"
        db_name = self.node.try_get_context("db_name") or "guestbook"
        db_user = self.node.try_get_context("db_user") or "appuser"
        tailscale_instance_type = (
            self.node.try_get_context("tailscale_instance_type") or "t3.micro"
        )

        # ------------------------------------------------------------------
        # Networking: a VPC with a public subnet (Tailscale router) and
        # private-isolated subnets (Lambda). No NAT gateway — Lambda reaches
        # Secrets Manager through an interface VPC endpoint instead.
        # ------------------------------------------------------------------
        vpc = ec2.Vpc(
            self,
            "HybridVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # --- Security groups ---
        tailscale_sg = ec2.SecurityGroup(
            self,
            "TailscaleRouterSg",
            vpc=vpc,
            description="Tailscale subnet router - WireGuard and outbound mesh",
            allow_all_outbound=True,
        )
        # Tailscale establishes the mesh with outbound traffic only (direct
        # connections plus a DERP relay fallback over 443), so no public
        # inbound rule is required here.

        lambda_sg = ec2.SecurityGroup(
            self,
            "ApiLambdaSg",
            vpc=vpc,
            description="Backend Lambda - egress to on-prem PostgreSQL",
            allow_all_outbound=True,
        )

        endpoint_sg = ec2.SecurityGroup(
            self,
            "SecretsEndpointSg",
            vpc=vpc,
            description="Secrets Manager interface endpoint",
            allow_all_outbound=True,
        )
        endpoint_sg.add_ingress_rule(
            lambda_sg,
            ec2.Port.tcp(443),
            "HTTPS from backend Lambda",
        )
        # The Lambda reaches the on-prem PostgreSQL server *through* the router
        # (the VPC routes below send the on-prem / Tailscale CIDRs to it). The
        # router forwards those packets to the tailnet, so its SG must accept
        # the Lambda's forwarded DB traffic on 5432.
        tailscale_sg.add_ingress_rule(
            lambda_sg,
            ec2.Port.tcp(5432),
            "Forwarded PostgreSQL from backend Lambda to on-prem DB",
        )

        # --- Secrets Manager reachable from isolated subnets (no NAT) ---
        vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[endpoint_sg],
        )

        # ------------------------------------------------------------------
        # Tailscale subnet router: an EC2 instance that advertises this VPC to
        # the tailnet and routes the on-prem DB subnet back into the VPC.
        # Run `tailscale up --advertise-routes=<vpc cidr> --accept-routes` and
        # approve the routes in the Tailscale admin console after deploy.
        # ------------------------------------------------------------------
        router_role = iam.Role(
            self,
            "TailscaleRouterRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        router_user_data = ec2.UserData.for_linux()
        router_user_data.add_commands(
            "set -euxo pipefail",
            "sysctl -w net.ipv4.ip_forward=1",
            "sysctl -w net.ipv6.conf.all.forwarding=1",
            "curl -fsSL https://tailscale.com/install.sh | sh",
            "systemctl enable --now tailscaled",
            "echo 'Run: tailscale up --advertise-routes="
            + str(vpc.vpc_cidr_block)
            + " --accept-routes --authkey <TS_AUTHKEY>'",
        )

        tailscale_router = ec2.Instance(
            self,
            "TailscaleRouter",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType(tailscale_instance_type),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=tailscale_sg,
            role=router_role,
            user_data=router_user_data,
            require_imdsv2=True,
        )
        # A router must forward packets that are not addressed to itself.
        tailscale_router.instance.add_property_override("SourceDestCheck", False)

        # Route both the on-prem LAN subnet and the Tailscale CGNAT range
        # (100.64.0.0/10 - used when the DB is addressed by its 100.x tailnet
        # IP) through the router, for every isolated subnet the Lambda lives in.
        routed_cidrs = {"OnPrem": onprem_db_cidr, "Tailnet": "100.64.0.0/10"}
        for i, subnet in enumerate(vpc.isolated_subnets):
            for label, cidr in routed_cidrs.items():
                ec2.CfnRoute(
                    self,
                    f"{label}Route{i}",
                    route_table_id=subnet.route_table.route_table_id,
                    destination_cidr_block=cidr,
                    instance_id=tailscale_router.instance_id,
                )

        # ------------------------------------------------------------------
        # Database credentials for the on-prem PostgreSQL server.
        # The username is fixed; the password is generated and must match the
        # one Ansible sets on-prem (see the walkthrough for syncing them).
        # ------------------------------------------------------------------
        db_secret = secretsmanager.Secret(
            self,
            "OnPremDbSecret",
            description="Connection details for the on-prem PostgreSQL database",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps(
                    {
                        "username": db_user,
                        "host": onprem_db_host,
                        "port": 5432,
                        "dbname": db_name,
                    }
                ),
                generate_string_key="password",
                exclude_characters="\"@/\\ '",
                password_length=24,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ------------------------------------------------------------------
        # Backend Lambda (inside the VPC) — talks to the on-prem DB.
        # psycopg2 is supplied as a plain-asset layer (Docker-free synth).
        # ------------------------------------------------------------------
        psycopg2_layer = lambda_.LayerVersion(
            self,
            "Psycopg2Layer",
            code=lambda_.Code.from_asset(os.path.join(HERE, "layers", "psycopg2")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="psycopg2-binary for on-prem PostgreSQL access",
        )

        api_fn = lambda_.Function(
            self,
            "GuestbookApiFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(os.path.join(HERE, "lambda")),
            layers=[psycopg2_layer],
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(15),
            memory_size=256,
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": db_secret.secret_arn,
                "DB_HOST": onprem_db_host,
                "DB_NAME": db_name,
            },
        )
        db_secret.grant_read(api_fn)

        # ------------------------------------------------------------------
        # REST API in front of the Lambda.
        # ------------------------------------------------------------------
        api = apigw.LambdaRestApi(
            self,
            "GuestbookApi",
            handler=api_fn,
            proxy=False,
            deploy_options=apigw.StageOptions(stage_name="prod"),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=["GET", "POST", "OPTIONS"],
            ),
        )
        guestbook = api.root.add_resource("guestbook")
        guestbook.add_method("GET")
        guestbook.add_method("POST")

        # ------------------------------------------------------------------
        # Static frontend: private S3 bucket served through CloudFront (OAC).
        # NOTE (intentional gate finding): no WAF and no CloudFront access
        # logging are configured here — the risk engine should flag these.
        # ------------------------------------------------------------------
        site_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
        )

        # The frontend is uploaded out-of-band (see the walkthrough:
        # `aws s3 sync ../frontend s3://<FrontendBucketName>` then a CloudFront
        # invalidation). Keeping it out of the stack avoids bundling a
        # custom-resource Lambda into this security-gated template.

        # --- Outputs ---
        CfnOutput(self, "SiteUrl", value=f"https://{distribution.domain_name}")
        CfnOutput(self, "DistributionId", value=distribution.distribution_id)
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "FrontendBucketName", value=site_bucket.bucket_name)
        CfnOutput(self, "DbSecretArn", value=db_secret.secret_arn)
        CfnOutput(self, "TailscaleRouterInstanceId", value=tailscale_router.instance_id)
        CfnOutput(self, "VpcCidr", value=vpc.vpc_cidr_block)


app = cdk.App()
HybridWebappStack(app, "HybridWebappStack")
app.synth()
