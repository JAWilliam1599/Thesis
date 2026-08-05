"""Coverage fixture: work accepted without any ceiling (cloud side).

Paired with ../ansible, which lifts the equivalent limits from a host service.
Everything else in this stack is deliberately unremarkable so that any
difference in the gate's verdict is attributable to the one weakness.

Weakness class: unbounded-resources (CWE-770)
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_apigateway as apigw, aws_lambda as lambda_
from constructs import Construct


class CoverageUnboundedResourcesStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # WEAKNESS (CWE-770): no reserved concurrency, so a caller can consume
        # the whole account's execution capacity through this one function.
        handler = lambda_.Function(
            self,
            "ReportBuilder",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.InlineCode("def handler(event, context):\n    return {}\n"),
            timeout=cdk.Duration.minutes(15),
        )

        # WEAKNESS (CWE-770): the stage sets no throttle and carries no usage
        # plan, so request volume is bounded only by what the caller can send.
        api = apigw.RestApi(
            self,
            "ReportApi",
            deploy_options=apigw.StageOptions(stage_name="prod"),
        )
        api.root.add_resource("reports").add_method(
            "POST", apigw.LambdaIntegration(handler)
        )


app = cdk.App()
CoverageUnboundedResourcesStack(app, "CoverageUnboundedResourcesStack")
app.synth()
