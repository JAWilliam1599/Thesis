import boto3
from botocore.exceptions import ClientError


def list_s3_buckets(region_name: str | None = None) -> list[str]:
    s3 = boto3.client("s3", region_name=region_name)
    response = s3.list_buckets()
    return [bucket["Name"] for bucket in response.get("Buckets", [])]


def main() -> None:
    try:
        buckets = list_s3_buckets()
        if not buckets:
            print("No S3 buckets found.")
            return

        print("S3 buckets:")
        for name in buckets:
            print(f"- {name}")
    except ClientError as exc:
        print(f"AWS request failed: {exc}")


if __name__ == "__main__":
    main()
