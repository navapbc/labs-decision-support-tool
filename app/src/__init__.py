import os

# Affects boto3 and libraries that use it like smart_open
# Breaking change: https://github.com/boto/boto3/issues/4392
# https://github.com/boto/boto3/issues/4435#issuecomment-2648819900
if "AWS_REQUEST_CHECKSUM_CALCULATION" not in os.environ:
    os.environ["AWS_REQUEST_CHECKSUM_CALCULATION"] = "when_required"
if "AWS_RESPONSE_CHECKSUM_VALIDATION" not in os.environ:
    os.environ["AWS_RESPONSE_CHECKSUM_VALIDATION"] = "when_required"
