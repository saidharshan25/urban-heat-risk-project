import json
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from hello_world import app


@pytest.fixture
def mock_table(monkeypatch):
    table = MagicMock()
    monkeypatch.setattr(app, "table", table)
    return table


def make_event(body):
    return {
        "httpMethod": "POST",
        "body": json.dumps(body),
    }


def test_lambda_handler_valid_request(mock_table):
    event = make_event({
        "location_id": "chennai-001",
        "temperature": 42,
        "humidity": 65,
    })

    response = app.lambda_handler(event, None)
    data = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert data["location_id"] == "chennai-001"
    assert data["temperature"] == 42.0
    assert data["humidity"] == 65.0
    assert data["risk_level"] == "SEVERE"
    assert data["message"] == "Saved to DynamoDB"

    mock_table.put_item.assert_called_once_with(
        Item={
            "location_id": "chennai-001",
            "temperature": Decimal("42.0"),
            "humidity": Decimal("65.0"),
            "risk_level": "SEVERE",
        }
    )


@pytest.mark.parametrize(
    "body",
    [
        {"temperature": 35, "humidity": 60},
        {"location_id": "chennai-001", "humidity": 60},
        {"location_id": "chennai-001", "temperature": 35},
        {"location_id": "chennai-001", "temperature": "invalid", "humidity": 60},
    ],
)
def test_lambda_handler_invalid_request(mock_table, body):
    response = app.lambda_handler(make_event(body), None)

    assert response["statusCode"] == 400
    mock_table.put_item.assert_not_called()


@pytest.mark.parametrize(
    "temperature,humidity",
    [
        (71, 50),
        (-51, 50),
        (30, 101),
        (30, -1),
    ],
)
def test_lambda_handler_out_of_range_values(
    mock_table, temperature, humidity
):
    event = make_event({
        "location_id": "chennai-001",
        "temperature": temperature,
        "humidity": humidity,
    })

    response = app.lambda_handler(event, None)

    assert response["statusCode"] == 400
    mock_table.put_item.assert_not_called()


def test_lambda_handler_invalid_json(mock_table):
    event = {"body": "{invalid json"}

    response = app.lambda_handler(event, None)

    assert response["statusCode"] == 400
    mock_table.put_item.assert_not_called()


def test_lambda_handler_missing_location_id(mock_table):
    event = make_event({
        "location_id": "   ",
        "temperature": 35,
        "humidity": 50,
    })

    response = app.lambda_handler(event, None)

    assert response["statusCode"] == 400
    mock_table.put_item.assert_not_called()


def test_get_risk_summary_reads_s3(monkeypatch):
    import io

    csv_data = (
        "risk_category,hexagons,mean_risk,vulnerable_population\n"
        "Low,2879,1.14,632023.3\n"
        "Moderate,959,8.0,437569.4\n"
        "High,21,15.87,14689.8\n"
        "Very High,0,,0.0\n"
    )

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        "Body": io.BytesIO(csv_data.encode("utf-8"))
    }
    monkeypatch.setattr(app, "s3", mock_s3)

    result = app.lambda_handler(
        {"httpMethod": "GET", "path": "/summary"},
        None
    )
    data = json.loads(result["body"])

    assert result["statusCode"] == 200
    assert data["count"] == 4
    assert data["summary"][0]["risk_category"] == "Low"
    assert data["summary"][0]["hexagons"] == 2879
    assert data["summary"][3]["mean_risk"] is None

    mock_s3.get_object.assert_called_once_with(
        Bucket=app.SUMMARY_BUCKET,
        Key=app.SUMMARY_KEY
    )


def test_summary_route_accepts_trailing_slash(monkeypatch):
    expected = {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": '{"test": "summary"}'
    }

    monkeypatch.setattr(
        app,
        "get_risk_summary",
        lambda: expected
    )

    result = app.lambda_handler(
        {"httpMethod": "GET", "path": "/summary/"},
        None
    )

    assert result == expected


def test_unrelated_get_does_not_read_s3(monkeypatch):
    mock_s3 = MagicMock()
    monkeypatch.setattr(app, "s3", mock_s3)

    result = app.lambda_handler(
        {"httpMethod": "GET", "path": "/unrelated"},
        None
    )

    assert result["statusCode"] == 400
    mock_s3.get_object.assert_not_called()



def test_get_risk_summary_s3_error_returns_500(monkeypatch):
    mock_s3 = MagicMock()
    mock_s3.get_object.side_effect = RuntimeError("S3 unavailable")
    monkeypatch.setattr(app, "s3", mock_s3)

    result = app.lambda_handler(
        {"httpMethod": "GET", "path": "/summary"},
        None
    )
    data = json.loads(result["body"])

    assert result["statusCode"] == 500
    assert data["error"] == "Failed to retrieve risk summary"
    mock_s3.get_object.assert_called_once_with(
        Bucket=app.SUMMARY_BUCKET,
        Key=app.SUMMARY_KEY
    )
