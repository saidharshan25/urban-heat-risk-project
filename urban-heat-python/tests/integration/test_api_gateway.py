import os
import boto3
import pytest
import requests


class TestApiGateway:

    @pytest.fixture()
    def api_gateway_url(self):
        """Get the configured API URL or resolve it from CloudFormation."""
        configured_url = os.environ.get("CLIMATEGUARD_API_URL")

        if configured_url:
            return configured_url.rstrip("/")

        stack_name = os.environ.get(
            "AWS_SAM_STACK_NAME",
            "urban-heat-python"
        )

        client = boto3.client("cloudformation")

        try:
            response = client.describe_stacks(StackName=stack_name)
        except Exception as exc:
            pytest.skip(
                f"Could not inspect CloudFormation stack '{stack_name}': "
                f"{exc}"
            )

        stacks = response.get("Stacks", [])

        if not stacks:
            pytest.skip(f"Stack '{stack_name}' was not found.")

        outputs = stacks[0].get("Outputs", [])
        api_outputs = [
            output["OutputValue"]
            for output in outputs
            if output["OutputKey"] == "RiskApiUrl"
        ]

        if not api_outputs:
            pytest.skip("RiskApiUrl output was not found in the stack.")

        return api_outputs[0].rstrip("/")

    def test_api_gateway(self, api_gateway_url):
        """Verify that POST /risk returns a valid prediction."""
        response = requests.post(
            api_gateway_url,
            json={
                "location_id": "integration_test",
                "temperature": 36,
                "humidity": 40
            },
            timeout=20
        )

        assert response.status_code == 200, response.text

        data = response.json()

        assert data["location_id"] == "integration_test"
        assert data["temperature"] == 36
        assert data["humidity"] == 40
        assert data["risk_level"] == "MODERATE"
