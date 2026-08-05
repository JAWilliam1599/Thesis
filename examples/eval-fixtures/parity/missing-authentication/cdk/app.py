"""Coverage fixture: a state-changing endpoint with no authentication (cloud side).

Paired with ../ansible, which permits password-less login to the same class of
administrative function on a host.  Everything else in this stack is
deliberately unremarkable so that any difference in the gate's verdict is
attributable to the one weakness.

Weakness class: missing-authentication (CWE-306)
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_apigateway as apigw
from constructs import Construct


class CoverageMissingAuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        api = apigw.RestApi(
            self,
            "AdminApi",
            rest_api_name="administrative-operations",
            deploy_options=apigw.StageOptions(stage_name="prod"),
        )

        # WEAKNESS (CWE-306): a credential-rotation operation callable by anyone
        # who can reach the endpoint -- no authorizer, no API key, no IAM.
        api.root.add_resource("rotate-keys").add_method(
            "POST",
            apigw.MockIntegration(
                request_templates={"application/json": '{"statusCode": 200}'},
                integration_responses=[apigw.IntegrationResponse(status_code="200")],
            ),
            method_responses=[apigw.MethodResponse(status_code="200")],
            authorization_type=apigw.AuthorizationType.NONE,
        )


app = cdk.App()
CoverageMissingAuthStack(app, "CoverageMissingAuthStack")
app.synth()
